#!/usr/bin/env python3
"""
Privacy-first AI-powered multi-page PDF redactor (single file).

Key changes vs previous:
- Aadhaar detection and stronger address heuristics.
- PAN/DOB/Passport/PIN detection preserved.
- ALWAYS auto-finetunes after run (no flag).
- Privacy-safe storage: no raw OCR text or document images saved.
  Only anonymized synthetic words + bounding boxes + labels are written to datasets/*.jsonl
- The anonymization is deterministic (hash-seeded Faker) so structure remains but PII can't be recovered.
"""

import os
import re
import json
import time
import tempfile
import subprocess
import sys
import argparse
import random
from pathlib import Path
from hashlib import sha256
from typing import List, Dict, Any
from collections import defaultdict

import numpy as np
from PIL import Image, ImageDraw, ImageFont
import cv2
from pdf2image import convert_from_path
import pytesseract
from pytesseract import Output
import torch
from transformers import (
    pipeline, AutoTokenizer, AutoModelForTokenClassification, AutoConfig,
    TrainingArguments, Trainer, DataCollatorForTokenClassification
)
from datasets import Dataset
from fuzzywuzzy import fuzz
from faker import Faker

# -------------------- Paths & config --------------------
BASE = Path(".").resolve()
MODELS_DIR = BASE / "models"
DATASETS_DIR = BASE / "datasets"   # will store anonymized JSONL examples only
OUTPUTS_DIR = BASE / "outputs"
TMP_DIR = BASE / "tmp"
for d in (MODELS_DIR, DATASETS_DIR, OUTPUTS_DIR, TMP_DIR):
    d.mkdir(parents=True, exist_ok=True)

# Defaults / tunables
PDF_DPI = 400
AI_MODELS = ["xlm-roberta-large-finetuned-conll03-english", "dslim/bert-base-NER"]
BERT_FINETUNE_BASE = "dslim/bert-base-NER"
DEFAULT_LAMA_REPO = "./lama_repo"
DEFAULT_LAMA_CKPT = "./lama_repo/checkpoints/ffhq_lama.ckpt"
SELF_TRAIN_EPOCHS = 1
SELF_TRAIN_BATCH = 8
SELF_TRAIN_LR = 5e-5
SYNTH_COUNT = 200
PAD_PIXELS = 4    # pad around bbox when redacting
MIN_BOX_WH = 6    # filter tiny boxes (px)
MAX_SYNTH_RATIO = 3  # at most this many synthetic examples per real saved example

fake = Faker()

# -------------------- Small utilities --------------------
def now_ts(): return str(int(time.time()))

def deterministic_synthetic_for_token(token_text: str, salt="anon_salt"):
    """
    Deterministic anonymization for a token. Keeps token-like form:
    - If token contains digits, replace digits with '#'
    - If token is short name-like, produce deterministic name
    - For longer tokens produce short synthetic phrase
    This function is irreversible (non-invertible).
    """
    if token_text is None:
        return ""
    t = str(token_text)
    # keep tiny tokens (punctuation) as-is if non-alphanumeric
    if not any(c.isalnum() for c in t):
        return t
    # create deterministic seed
    h = sha256((salt + "|" + t).encode()).hexdigest()
    seed = int(h[:16], 16) % (2**31)
    f = Faker(); f.seed_instance(seed)
    # numbers -> masked numeric pattern
    if any(ch.isdigit() for ch in t):
        # keep spacing shape: replace digits with '#'
        return re.sub(r'\d', '#', t)
    # short single-word tokens (likely names) -> deterministic name token
    if len(t) <= 12 and t.isalpha():
        nm = f.first_name()
        # keep capitalization pattern
        if t.istitle():
            return nm
        if t.isupper():
            return nm.upper()
        return nm.lower()
    # fallback: short synthetic word
    return f.word()[:max(3, min(12, len(t)))]

def canonicalize_label(label_str):
    s = str(label_str).upper()
    if s in ("O","0"): return "O"
    if "PAN" in s: return "B-DOC"
    if "AADHAAR" in s or "AADHAAR" in s or "AADHAR" in s: return "B-DOC"
    if "PER" in s or "NAME" in s: return "B-PER"
    if "LOC" in s or "CITY" in s or "STATE" in s or "ADDRESS" in s: return "B-LOC"
    if "ORG" in s: return "B-ORG"
    if "DOC" in s or "PASSPORT" in s or "ID" in s: return "B-DOC"
    if "DATE" in s or "DOB" in s: return "B-DATE"
    return "B-MISC"

# -------------------- OCR --------------------
def pdf_to_images(pdf_path: str, dpi:int = PDF_DPI) -> List[Image.Image]:
    pages = convert_from_path(pdf_path, dpi=dpi)
    if not pages:
        raise RuntimeError("Failed to rasterize PDF. Ensure poppler/pdftoppm is installed.")
    return [p.convert("RGB") for p in pages]

def ocr_image_tokens(pil_img: Image.Image):
    data = pytesseract.image_to_data(pil_img, output_type=Output.DICT)
    tokens = []
    for i, txt in enumerate(data["text"]):
        if not txt.strip(): continue
        tokens.append({
            "text": txt,
            "left": int(data["left"][i]),
            "top": int(data["top"][i]),
            "width": int(data["width"][i]),
            "height": int(data["height"][i])
        })
    joined_text = " ".join(t["text"] for t in tokens)
    return joined_text, tokens

# -------------------- Dual NER --------------------
def run_dual_ner(text: str) -> List[Dict[str,Any]]:
    preds = []
    for model_name in AI_MODELS:
        dev = 0 if torch.cuda.is_available() else -1
        try:
            pipe = pipeline("ner", model=model_name, aggregation_strategy="simple", device=dev)
            out = pipe(text)
            preds.extend(out)
        except Exception as e:
            print(f"[WARN] NER model '{model_name}' failed: {e}")
    return preds

# -------------------- Mapping + heuristics --------------------
def merge_adjacent_on_line(sorted_tokens):
    merged = []
    cur = None
    for t in sorted_tokens:
        if cur is None:
            cur = t.copy()
        else:
            same_line = abs(t["top"] - cur["top"]) <= max(8, int(0.02 * t["height"]))
            gap = t["left"] - (cur["left"] + cur["width"])
            if same_line and gap <= max(20, int(0.2 * t["width"])):
                cur["text"] = cur["text"] + " " + t["text"]
                new_right = t["left"] + t["width"]
                cur["width"] = new_right - cur["left"]
            else:
                merged.append(cur)
                cur = t.copy()
    if cur: merged.append(cur)
    return merged

def add_regex_based_detections(full_text: str, tokens: List[Dict[str,int]]):
    """
    Regex-based fallbacks to find structured sensitive patterns:
    - PAN: 5 letters + 4 digits + 1 letter
    - AADHAAR: 12 digits, optionally spaces every 4 digits
    - DOB dd/mm/yyyy
    - Passport-like A1234567
    - Pincode 400xxx (6-digit)
    - address keyword hits
    """
    detections = []
    txt = full_text
    # PAN
    for m in re.finditer(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", txt):
        detections.append({"word": m.group(), "label": "B-DOC"})
    # Aadhaar: 12 digits, allow spaces in 4-4-4 groups
    for m in re.finditer(r"\b(?:\d{4}\s\d{4}\s\d{4}|\d{12})\b", txt):
        # be cautious: many 12-digit numbers may not be Aadhaar, but it's a good fallback
        detections.append({"word": m.group(), "label": "B-DOC"})
    # DOB
    for m in re.finditer(r"\b\d{2}[/\-]\d{2}[/\-]\d{4}\b", txt):
        detections.append({"word": m.group(), "label": "B-DATE"})
    # Passport (one letter + 7 digits)
    for m in re.finditer(r"\b[A-Z]\d{7}\b", txt):
        detections.append({"word": m.group(), "label": "B-DOC"})
    # Pincode (6-digit)
    for m in re.finditer(r"\b[4-9]\d{5}\b", txt):
        detections.append({"word": m.group(), "label": "B-LOC"})
    # address keyword list (expanded)
    kwlist = [
        "road","rd","street","st","nagar","colony","sector","lane","plot","building","bldg",
        "flat","apartment","opp","near","behind","block","phase","society","mandir","temple",
        "village","village:","town","city","district","state","maharashtra","mumbai","thane",
        "navi mumbai","mumbai-","india","pin","pincode"
    ]
    # search for keywords and create detections for nearby token windows
    low = txt.lower()
    for kw in kwlist:
        start = 0
        while True:
            idx = low.find(kw, start)
            if idx == -1: break
            # create a substring window around keyword to map to tokens later
            span_start = max(0, idx - 40)
            span_end = min(len(txt), idx + len(kw) + 40)
            snippet = txt[span_start:span_end]
            detections.append({"word": snippet, "label": "B-LOC"})
            start = idx + 1
    # map regex detections to token bboxes
    mapped = []
    token_texts = [t["text"] for t in tokens]
    joined = " ".join(token_texts).lower()
    for r in detections:
        rw = r["word"].lower()
        matched = False
        # exact token match
        for i,t in enumerate(tokens):
            if rw.strip() == t["text"].lower():
                bbox = [t["left"], t["top"], t["left"]+t["width"], t["top"]+t["height"]]
                mapped.append({"word": t["text"], "bbox": bbox, "label": r["label"]})
                matched = True
                break
        if matched: continue
        # fuzzy window match across up to 6 tokens
        for i in range(len(tokens)):
            window = " ".join([tokens[j]["text"] for j in range(i, min(i+6, len(tokens)))])
            if fuzz.partial_ratio(rw, window.lower()) >= 70:
                xs = [tokens[j]["left"] for j in range(i, min(i+6, len(tokens)))]
                ys = [tokens[j]["top"] for j in range(i, min(i+6, len(tokens)))]
                x2s = [tokens[j]["left"]+tokens[j]["width"] for j in range(i, min(i+6, len(tokens)))]
                y2s = [tokens[j]["top"]+tokens[j]["height"] for j in range(i, min(i+6, len(tokens)))]
                bbox = [min(xs), min(ys), max(x2s), max(y2s)]
                mapped.append({"word": window, "bbox": bbox, "label": r["label"]})
                break
    return mapped

def map_ner_to_tokens(ner_preds, tokens, full_text):
    """
    Map NER model output to OCR tokens (bboxes) using substring, fuzzy, and window heuristics.
    Also includes regex-based fallbacks (PAN, Aadhaar, DOB, passport, PIN, address keywords).
    """
    token_texts = [t["text"] for t in tokens]
    joined = " ".join(token_texts).lower()
    detections = []
    mapped_indices = set()
    detected_names = set()

    ner_spans = []
    for n in ner_preds:
        w = n.get("word") or n.get("entity") or ""
        if not w: continue
        label = n.get("entity_group") or n.get("entity") or n.get("label") or ""
        score = float(n.get("score", 0.0))
        ner_spans.append({"word": w.strip(), "label": label, "score": score})

    # map spans using substring/fuzzy/window
    for span in ner_spans:
        s = span["word"].strip()
        s_low = s.lower()
        if s_low in joined:
            idx = joined.find(s_low)
            cum = 0; start_idx=None; end_idx=None
            for i,t in enumerate(token_texts):
                t_low = t.lower()
                if start_idx is None and cum + len(t_low) > idx:
                    start_idx = i
                if start_idx is not None:
                    if cum + len(" ".join(token_texts[start_idx:i+1]).lower()) >= idx + len(s_low):
                        end_idx = i; break
                cum += len(t_low) + 1
            if start_idx is not None and end_idx is not None:
                xs = [tokens[j]["left"] for j in range(start_idx, end_idx+1)]
                ys = [tokens[j]["top"] for j in range(start_idx, end_idx+1)]
                x2s = [tokens[j]["left"]+tokens[j]["width"] for j in range(start_idx, end_idx+1)]
                y2s = [tokens[j]["top"]+tokens[j]["height"] for j in range(start_idx, end_idx+1)]
                bbox = [min(xs), min(ys), max(x2s), max(y2s)]
                detections.append({"word":" ".join(token_texts[start_idx:end_idx+1]), "bbox":bbox, "label":canonicalize_label(span["label"]), "score": span.get("score", 0.0)})
                mapped_indices.update(range(start_idx, end_idx+1))
                if "PER" in span["label"].upper() or "NAME" in span["label"].upper():
                    detected_names.add(" ".join(token_texts[start_idx:end_idx+1]).lower())
                continue
        # fuzzy token-level
        best_i=None; best_score=0
        for i,t in enumerate(tokens):
            sc = fuzz.token_set_ratio(s_low, t["text"].lower())
            if sc > best_score: best_score=sc; best_i=i
        if best_score >= 72 and best_i is not None:
            t = tokens[best_i]
            bbox=[t["left"],t["top"],t["left"]+t["width"],t["top"]+t["height"]]
            detections.append({"word": t["text"], "bbox":bbox, "label": canonicalize_label(span["label"]), "score": span.get("score", 0.0)})
            mapped_indices.add(best_i)
            if "PER" in span["label"].upper() or "NAME" in span["label"].upper():
                detected_names.add(t["text"].lower())
            continue
        # window fuzzy
        for i in range(len(tokens)):
            window = " ".join([tokens[j]["text"] for j in range(i, min(i+4,len(tokens)))])
            if fuzz.partial_ratio(s_low, window.lower()) >= 70:
                xs=[tokens[j]["left"] for j in range(i, min(i+4,len(tokens)))]
                ys=[tokens[j]["top"] for j in range(i, min(i+4,len(tokens)))]
                x2s=[tokens[j]["left"]+tokens[j]["width"] for j in range(i, min(i+4,len(tokens)))]
                y2s=[tokens[j]["top"]+tokens[j]["height"] for j in range(i, min(i+4,len(tokens)))]
                bbox=[min(xs), min(ys), max(x2s), max(y2s)]
                detections.append({"word":window, "bbox":bbox, "label":canonicalize_label(span["label"]), "score": span.get("score", 0.0)})
                mapped_indices.update(range(i, min(i+4,len(tokens))))
                if "PER" in span["label"].upper() or "NAME" in span["label"].upper():
                    detected_names.add(window.lower())
                break

    # incorporate regex-based detections (PAN, Aadhaar, DOB, passport, pin, keywords)
    regex_mapped = add_regex_based_detections(full_text, tokens)
    # merge regex detections if not overlapping with existing detections
    for r in regex_mapped:
        if not r.get("bbox"): continue
        bx0,by0,bx1,by1 = map(int, r["bbox"])
        dupe = False
        for d in detections:
            dx0,dy0,dx1,dy1 = map(int, d["bbox"])
            interW = max(0, min(bx1,dx1)-max(bx0,dx0))
            interH = max(0, min(by1,dy1)-max(by0,dy0))
            if interW*interH > 0:
                dupe = True; break
        if not dupe:
            r["label"] = canonicalize_label(r.get("label",""))
            r["bbox"] = [int(round(x)) for x in r["bbox"]]
            detections.append(r)

    # expand names via merged line tokens
    sorted_tokens = sorted(tokens, key=lambda t:(t["top"], t["left"]))
    merged_line_tokens = merge_adjacent_on_line(sorted_tokens)

    final = []
    seen_boxes = set()
    for d in detections:
        if not d.get("bbox"): continue
        key = tuple(map(int, d["bbox"]))
        if key not in seen_boxes:
            d["label"] = canonicalize_label(d.get("label",""))
            d["bbox"] = [int(round(x)) for x in d["bbox"]]
            final.append(d); seen_boxes.add(key)

    detected_names = {d["word"].lower() for d in final if "PER" in d.get("label","") or "NAME" in d.get("label","")}
    for mt in merged_line_tokens:
        mt_low = mt["text"].lower()
        for dn in list(detected_names):
            if dn in mt_low or fuzz.partial_ratio(dn, mt_low) >= 75:
                bbox=[mt["left"], mt["top"], mt["left"]+mt["width"], mt["top"]+mt["height"]]
                key = tuple(map(int,bbox))
                if key not in seen_boxes:
                    final.append({"word": mt["text"], "bbox":bbox, "label":"B-PER"}); seen_boxes.add(key)

    # rescan repeated occurrences
    for i,t in enumerate(tokens):
        tw_low = t["text"].lower()
        for dn in list(detected_names):
            if tw_low == dn or fuzz.ratio(dn, tw_low) >= 88 or fuzz.partial_ratio(dn, tw_low) >= 85:
                bbox=[t["left"], t["top"], t["left"]+t["width"], t["top"]+t["height"]]
                key = tuple(map(int,bbox))
                if key not in seen_boxes:
                    final.append({"word": t["text"], "bbox":bbox, "label":"B-PER"}); seen_boxes.add(key)
                    break

    # filter tiny boxes
    filtered = []
    for d in final:
        bx0,by0,bx1,by1 = map(int, d["bbox"])
        w = max(0, bx1 - bx0); h = max(0, by1 - by0)
        if w < MIN_BOX_WH or h < MIN_BOX_WH:
            continue
        filtered.append(d)

    # dedupe final
    out = []
    sseen = set()
    for d in filtered:
        key = (int(d["bbox"][0]), int(d["bbox"][1]), int(d["bbox"][2]), int(d["bbox"][3]), d["label"])
        if key in sseen: continue
        sseen.add(key); out.append(d)
    return out

# -------------------- Redaction functions --------------------
def redact_image_flat(pil_img: Image.Image, detections: List[Dict[str,Any]], mode="mask", pad_px=PAD_PIXELS):
    img = pil_img.copy().convert("RGB")
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    for d in detections:
        if not d.get("bbox"): continue
        x0,y0,x1,y1 = d["bbox"]
        x0, x1 = sorted([int(round(x0)), int(round(x1))])
        y0, y1 = sorted([int(round(y0)), int(round(y1))])
        x0 = max(0, x0 - pad_px)
        y0 = max(0, y0 - pad_px)
        x1 = min(img.width, x1 + pad_px)
        y1 = min(img.height, y1 + pad_px)
        if x1 <= x0 or y1 <= y0:
            print(f"[WARN] Skipping invalid bbox: {d.get('bbox')}")
            continue
        if (x1 - x0 < MIN_BOX_WH) or (y1 - y0 < MIN_BOX_WH):
            continue
        if mode == "mask":
            draw.rectangle([x0, y0, x1, y1], fill="black")
        elif mode == "synth":
            draw.rectangle([x0, y0, x1, y1], fill="white")
            synth = deterministic_synthetic_for_token(d.get("word",""))
            draw.text((x0+2, y0+2), synth, fill="black", font=font)
    return img

def inpaint_regions_with_lama_or_opencv(image_bgr, regions, lama_repo=None, lama_ckpt=None):
    mask = np.zeros(image_bgr.shape[:2], dtype=np.uint8)
    for (x,y,w,h) in regions:
        cv2.rectangle(mask, (x,y), (x+w,y+h), 255, -1)
    if mask.sum() == 0: return image_bgr.copy()
    if lama_repo and lama_ckpt and os.path.exists(lama_repo) and os.path.exists(lama_ckpt):
        tmpd = tempfile.mkdtemp()
        inp, msk, outp = [os.path.join(tmpd,f) for f in ("img.png","mask.png","out.png")]
        cv2.imwrite(inp, image_bgr); cv2.imwrite(msk, mask)
        cmd = [sys.executable, "bin/predict.py", "--input", inp, "--mask", msk, "--checkpoint", lama_ckpt, "--output", outp]
        try:
            subprocess.check_call(cmd, cwd=lama_repo)
            if os.path.exists(outp):
                return cv2.imread(outp)
        except Exception as e:
            print("[WARN] LaMa failed:", e)
    return cv2.inpaint(image_bgr, mask, 3, cv2.INPAINT_TELEA)

# -------------------- Privacy-first labeled example saving --------------------
def save_labeled_example(tokens: List[Dict[str,int]], labels: List[str]):
    """
    IMPORTANT: privacy-preserving saver.
    - Does NOT save the original image or original OCR text.
    - Writes an anonymized example JSONL with:
        { "words": [anonymized tokens], "boxes": [[x0,y0,x1,y1], ...], "labels": [...] }
    - Anonymization is deterministic via hashing+Faker so the structure remains but PII can't be reconstructed.
    """
    ts = now_ts()
    jpath = DATASETS_DIR / f"example_{ts}.jsonl"
    anon_words = [deterministic_synthetic_for_token(t["text"]) for t in tokens]
    boxes = [[t["left"], t["top"], t["left"]+t["width"], t["top"]+t["height"]] for t in tokens]
    rec = {"words": anon_words, "boxes": boxes, "labels": labels}
    # write one-line JSONL
    with open(jpath, "w", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    print("[INFO] Saved anonymized labeled example (no PII):", jpath)
    return str(jpath)

# -------------------- Synthetic generation --------------------
FIRST = ["Shriyash","Vaishali","Santosh","Kamlakar","Ravi","Asha","Rahul","Priya","Anil","Sunita","Deepak","Sanjay","Pooja"]
LAST = ["Mhatre","Patil","Sharma","Kumar","Deshmukh","Joshi","Mehta","Bhandari","Ghosh","Khan","Reddy","Iyer"]

def gen_passport():
    return random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") + "".join(str(random.randint(0,9)) for _ in range(7))

def gen_dob():
    y = random.randint(1970,2010)
    m = random.randint(1,12)
    d = random.randint(1,28)
    return f"{d:02d}/{m:02d}/{y}"

def gen_pan():
    return "".join(random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") for _ in range(5)) + \
           "".join(random.choice("0123456789") for _ in range(4)) + \
           random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")

def gen_aadhaar():
    # produce 12-digit string; sometimes include spaces in 4-4-4 groups
    s = "".join(random.choice("0123456789") for _ in range(12))
    if random.random() < 0.6:
        return f"{s[0:4]} {s[4:8]} {s[8:12]}"
    return s

def generate_pan_examples(n=200):
    exs = []
    templates = [
        "PAN: {pan}",
        "My PAN number is {pan}",
        "Permanent Account Number - {pan}",
        "PAN card {pan}",
        "{pan} is the PAN assigned"
    ]
    for _ in range(n):
        pan = gen_pan()
        t = random.choice(templates).format(pan=pan)
        words = t.split()
        labels = ["O"] * len(words)
        for i,w in enumerate(words):
            if w == pan:
                labels[i] = "B-DOC"
        exs.append({"words": words, "labels": labels, "text": t})
    return exs

def generate_aadhaar_examples(n=200):
    exs = []
    templates = [
        "Aadhaar no {aad}",
        "Aadhaar: {aad}",
        "UIDAI number {aad}",
        "Aadhaar Card {aad}",
        "{aad} is the Aadhaar number"
    ]
    for _ in range(n):
        aad = gen_aadhaar()
        t = random.choice(templates).format(aad=aad)
        words = t.split()
        labels = ["O"] * len(words)
        for i,w in enumerate(words):
            if aad.replace(" ", "") in w.replace(" ", "") or w == aad:
                labels[i] = "B-DOC"
        exs.append({"words": words, "labels": labels, "text": t})
    return exs

def generate_synthetic_examples(n=200):
    exs = []
    for _ in range(n):
        fname = random.choice(FIRST)
        mid = random.choice(FIRST) if random.random() < 0.4 else ""
        lname = random.choice(LAST)
        name = " ".join(x for x in (fname, mid, lname) if x)
        dob = gen_dob()
        passport = gen_passport()
        city = random.choice(["Navi Mumbai","Pune","Mumbai","Alibag","Thane"])
        pincode = random.choice(["400070","400701","400707","400089","400089"])
        addr = f"{random.randint(1,300)} MG Road, {city}, Maharashtra, India - {pincode}"
        text = f"Name: {name} DOB: {dob} Passport: {passport} Address: {addr}"
        words = text.split()
        labels = []
        for w in words:
            w_clean = w.strip(",:-")
            if w_clean in (fname, mid, lname):
                labels.append("B-PER")
            elif re.fullmatch(r'\d{2}/\d{2}/\d{4}', w_clean):
                labels.append("B-DATE")
            elif re.fullmatch(r'[A-Z]\d{7}', w_clean):
                labels.append("B-DOC")
            elif re.fullmatch(r'\d{6}', w_clean):
                labels.append("B-LOC")
            else:
                labels.append("O")
        exs.append({"words": words, "labels": labels, "text": text})
    # add PAN + Aadhaar examples for pattern learning
    exs.extend(generate_pan_examples(n // 4))
    exs.extend(generate_aadhaar_examples(n // 4))
    return exs

# -------------------- Build HF dataset for token classification --------------------
def build_token_classification_dataset(jsonl_paths: List[Path], synthetic_examples: List[Dict[str,Any]], tokenizer):
    seqs = []
    # read anonymized saved examples (these do NOT contain PII)
    for p in jsonl_paths:
        try:
            for line in open(p, "r", encoding="utf-8"):
                rec = json.loads(line)
                words = rec.get("words", [])
                labels = rec.get("labels", [])
                if words and labels:
                    seqs.append({"words": words, "labels": labels})
        except Exception:
            continue

    # cap synthetic examples relative to real examples to avoid synthetic domination
    real_count = max(1, len(seqs))
    max_allowed_synth = max(50, min(len(synthetic_examples), real_count * MAX_SYNTH_RATIO))
    sampled_synth = synthetic_examples[:max_allowed_synth]
    for s in sampled_synth:
        if any(l != "O" for l in s.get("labels", [])):
            # anonymize synthetic words as well (so training never sees real raw text)
            anon_words = [deterministic_synthetic_for_token(w) for w in s["words"]]
            seqs.append({"words": anon_words, "labels": s["labels"]})

    if not seqs:
        return None, None

    unique_labels = list(sorted({l for ex in seqs for l in ex["labels"]}))
    if "O" not in unique_labels:
        unique_labels.insert(0, "O")
    else:
        unique_labels = [l for l in unique_labels if l != "O"]
        unique_labels = ["O"] + sorted(unique_labels)

    label_to_id = {l:i for i,l in enumerate(unique_labels)}
    id_to_label = {i:l for l,i in label_to_id.items()}

    tokenized_inputs = {"input_ids": [], "attention_mask": [], "labels": []}

    for ex in seqs:
        words, labs = ex["words"], ex["labels"]
        enc = tokenizer(words, is_split_into_words=True, truncation=True, padding="max_length", max_length=128)
        word_ids = enc.word_ids()
        aligned_labels = []
        for wid in word_ids:
            if wid is None:
                aligned_labels.append(-100)
            else:
                lbl = labs[wid] if wid < len(labs) else "O"
                aligned_labels.append(label_to_id.get(lbl, label_to_id.get("O", 0)))
        tokenized_inputs["input_ids"].append(enc["input_ids"])
        tokenized_inputs["attention_mask"].append(enc["attention_mask"])
        tokenized_inputs["labels"].append(aligned_labels)

    ds = Dataset.from_dict(tokenized_inputs)
    return ds, unique_labels

# -------------------- Fine-tune BERT NER --------------------
def fine_tune_bert_ner():
    jsonl_files = sorted(Path(DATASETS_DIR).glob("example_*.jsonl"))
    # generate synthetic pool; will be capped inside build function
    synth_pool = generate_synthetic_examples(n=SYNTH_COUNT)
    tokenizer = AutoTokenizer.from_pretrained(BERT_FINETUNE_BASE, use_fast=True)
    train_ds, label_list = build_token_classification_dataset(jsonl_files, synth_pool, tokenizer)
    if train_ds is None:
        print("[WARN] No training examples after tokenization.")
        return None

    # ensure label ordering
    if "O" in label_list:
        lab_no_o = [l for l in label_list if l != "O"]
        label_list = ["O"] + sorted(lab_no_o)
    else:
        label_list = sorted(label_list)
        if "O" not in label_list:
            label_list.insert(0, "O")
    num_labels = len(label_list)
    print("[INFO] Label list:", label_list, "num_labels:", num_labels)

    config = AutoConfig.from_pretrained(BERT_FINETUNE_BASE, num_labels=num_labels)
    id2label = {i: l for i, l in enumerate(label_list)}
    label2id = {l: i for i, l in id2label.items()}
    config.id2label = id2label
    config.label2id = label2id

    try:
        model = AutoModelForTokenClassification.from_pretrained(
            BERT_FINETUNE_BASE,
            config=config,
            ignore_mismatched_sizes=True
        )
    except TypeError:
        print("[WARN] transformers does not support ignore_mismatched_sizes: resizing head manually")
        model = AutoModelForTokenClassification.from_pretrained(BERT_FINETUNE_BASE, config=config)
        try:
            hidden_size = model.config.hidden_size
        except Exception:
            hidden_size = getattr(model, "roberta", None).config.hidden_size if hasattr(model, "roberta") else 768
        model.classifier = torch.nn.Linear(hidden_size, num_labels)

    data_collator = DataCollatorForTokenClassification(tokenizer)
    outdir = MODELS_DIR / f"bert_finetuned_{now_ts()}"
    training_args = TrainingArguments(
        output_dir=str(outdir),
        num_train_epochs=SELF_TRAIN_EPOCHS,
        per_device_train_batch_size=SELF_TRAIN_BATCH,
        learning_rate=SELF_TRAIN_LR,
        logging_steps=10,
        save_strategy="epoch",
        remove_unused_columns=False
    )
    trainer = Trainer(model=model, args=training_args, train_dataset=train_ds, tokenizer=tokenizer, data_collator=data_collator)
    print(f"[INFO] Fine-tuning on {len(train_ds)} examples (including anonymized + synthetic). This may take a while.")
    try:
        trainer.train()
        trainer.save_model(str(outdir))
        print("[INFO] Fine-tuned model saved to:", outdir)
        return str(outdir)
    except Exception as e:
        print("[WARN] Trainer failed during training:", e)
        try:
            trainer.save_model(str(outdir))
            print("[INFO] Partial model saved to:", outdir)
            return str(outdir)
        except Exception:
            return None

# -------------------- Main flow --------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input","-i", required=True, help="Input PDF file")
    ap.add_argument("--redact-mode","-r", default="mask", choices=["mask","synth","inpaint"], help="Redaction mode")
    ap.add_argument("--lama-repo", default=DEFAULT_LAMA_REPO, help="LaMa repo path (optional)")
    ap.add_argument("--lama-ckpt", default=DEFAULT_LAMA_CKPT, help="LaMa ckpt path (optional)")
    args = ap.parse_args()

    pil_pages = pdf_to_images(args.input, dpi=PDF_DPI)
    print(f"[INFO] PDF contains {len(pil_pages)} pages. Processing at {PDF_DPI} DPI.")

    redacted_images = []
    for page_no, pil_img in enumerate(pil_pages):
        print(f"[INFO] Page {page_no+1}/{len(pil_pages)}: OCR ...")
        full_text, tokens = ocr_image_tokens(pil_img)
        print(f"[INFO] OCR tokens: {len(tokens)} chars_text={len(full_text)}")

        ner_preds = run_dual_ner(full_text)
        detections = map_ner_to_tokens(ner_preds, tokens, full_text)

        # extra safety: explicit regex mapping for PAN/Aadhaar if missed
        pan_matches = re.findall(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", full_text)
        for pan in pan_matches:
            if not any(pan in d.get("word","") for d in detections):
                for i,t in enumerate(tokens):
                    if t["text"].strip() == pan:
                        bbox=[t["left"], t["top"], t["left"]+t["width"], t["top"]+t["height"]]
                        detections.append({"word": pan, "bbox": bbox, "label": "B-DOC"})
                        break
        aad_matches = re.findall(r"\b(?:\d{4}\s\d{4}\s\d{4}|\d{12})\b", full_text)
        for aad in aad_matches:
            if not any(aad.replace(" ","") in d.get("word","").replace(" ","") for d in detections):
                for i,t in enumerate(tokens):
                    if aad.replace(" ","") == t["text"].replace(" ",""):
                        bbox=[t["left"], t["top"], t["left"]+t["width"], t["top"]+t["height"]]
                        detections.append({"word": aad, "bbox": bbox, "label": "B-DOC"})
                        break

        # deterministic dedupe and sort
        keymap = {}
        for d in detections:
            if not d.get("bbox"): continue
            k = (int(d["bbox"][0]), int(d["bbox"][1]), int(d["bbox"][2]), int(d["bbox"][3]), d.get("label",""), d.get("word",""))
            if k not in keymap:
                keymap[k] = d
        detections = sorted(keymap.values(), key=lambda x: (x["bbox"][1], x["bbox"][0]))

        print(f"[INFO] Detected {len(detections)} sensitive spans on page {page_no+1}")
        for i,d in enumerate(detections, start=1):
            print(f"  DET {i}: {d['label']} '{d['word']}' bbox={d['bbox']}")

        # build token-level labels for saving (these labels are safe metadata)
        token_labels = ["O"] * len(tokens)
        for d in detections:
            bx0,by0,bx1,by1 = map(int, d["bbox"])
            for idx,t in enumerate(tokens):
                tx0,ty0,tx1,ty1 = t["left"], t["top"], t["left"]+t["width"], t["top"]+t["height"]
                interW = max(0, min(bx1,tx1)-max(bx0,tx0))
                interH = max(0, min(by1,ty1)-max(by0,ty0))
                if interW*interH > 0:
                    token_labels[idx] = d["label"]

        # SAVE ANONYMIZED EXAMPLE (privacy-first)
        save_labeled_example(tokens, token_labels)

        # redact page in memory
        if args.redact_mode == "inpaint":
            regions = [(int(b["bbox"][0]), int(b["bbox"][1]), int(b["bbox"][2]-b["bbox"][0]), int(b["bbox"][3]-b["bbox"][1])) for b in detections]
            img_bgr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
            res_bgr = inpaint_regions_with_lama_or_opencv(img_bgr, regions, args.lama_repo, args.lama_ckpt)
            redacted_page = Image.fromarray(cv2.cvtColor(res_bgr, cv2.COLOR_BGR2RGB))
        else:
            redacted_page = redact_image_flat(pil_img, detections, mode=args.redact_mode)

        redacted_images.append(redacted_page)
        print(f"[INFO] Page {page_no+1} redacted.")

    # combine pages into single PDF (image-only)
    out_pdf = OUTPUTS_DIR / f"redacted_{now_ts()}.pdf"
    if len(redacted_images) == 0:
        print("[ERROR] No pages processed.")
        return
    if len(redacted_images) == 1:
        redacted_images[0].save(out_pdf, "PDF")
    else:
        redacted_images[0].save(out_pdf, save_all=True, append_images=redacted_images[1:], format="PDF")
    print("[INFO] Final redacted PDF saved to:", out_pdf)

    # ALWAYS auto fine-tune on anonymized saved examples + synthetic pool
    try:
        model_out = fine_tune_bert_ner()
        if model_out:
            print("[INFO] Auto fine-tune completed:", model_out)
    except Exception as e:
        print("[WARN] Auto fine-tune failed:", e)

if __name__ == "__main__":
    main()
