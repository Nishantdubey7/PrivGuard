#!/usr/bin/env python3
"""
app1_fixed.py
Privacy-first PDF redactor — corrected for OCR bbox alignment and robust redaction.

Usage examples:
  python app1_fixed.py -i shriyashpassport.pdf -r mask --lang "eng+hin"
  python app1_fixed.py -i doc.pdf -r inpaint --lama-repo ./lama_repo --lama-ckpt ./lama_repo/checkpoints/ffhq_lama.ckpt

Notes:
  - Default redaction mode "mask" uses solid black boxes.
  - Use --use-easyocr to enable EasyOCR for improved bounding boxes on multilingual docs (pip install easyocr).
  - Keeps auto-fine-tune flow (anonymized examples + synthetic).
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
from typing import List, Dict, Any, Tuple
from collections import defaultdict

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps
import cv2
from pdf2image import convert_from_path
import pytesseract
from pytesseract import Output
import torch
from transformers import pipeline, AutoTokenizer, AutoModelForTokenClassification, AutoConfig
from transformers import TrainingArguments, Trainer, DataCollatorForTokenClassification
from datasets import Dataset
from fuzzywuzzy import fuzz
from faker import Faker

# Optional easyocr import (lazy)
try:
    import easyocr
    _EASYOCR_AVAILABLE = True
except Exception:
    _EASYOCR_AVAILABLE = False

# -------------------- Paths & config --------------------
BASE = Path(".").resolve()
MODELS_DIR = BASE / "models"
DATASETS_DIR = BASE / "datasets"
OUTPUTS_DIR = BASE / "outputs"
TMP_DIR = BASE / "tmp"
for d in (MODELS_DIR, DATASETS_DIR, OUTPUTS_DIR, TMP_DIR):
    d.mkdir(parents=True, exist_ok=True)

# Tunables
PDF_DPI = 400
AI_MODELS = ["xlm-roberta-large-finetuned-conll03-english", "dslim/bert-base-NER"]
BERT_FINETUNE_BASE = "dslim/bert-base-NER"
DEFAULT_LAMA_REPO = "./lama_repo"
DEFAULT_LAMA_CKPT = "./lama_repo/checkpoints/ffhq_lama.ckpt"
SELF_TRAIN_EPOCHS = 1
SELF_TRAIN_BATCH = 8
SELF_TRAIN_LR = 5e-5
SYNTH_COUNT = 200
PAD_PIXELS = 4
MIN_BOX_WH = 6
MAX_SYNTH_RATIO = 3
OCR_PSM = 3
OCR_OEM = 3

fake = Faker()
_NER_PIPELINES = []
_NER_LOADED = False

def now_ts(): return str(int(time.time()))

# -------------------- Deterministic anonymization --------------------
def deterministic_synthetic_for_token(token_text: str, salt="anon_salt"):
    if token_text is None:
        return ""
    t = str(token_text)
    if not any(c.isalnum() for c in t):
        return t
    h = sha256((salt + "|" + t).encode()).hexdigest()
    seed = int(h[:16], 16) % (2**31)
    f = Faker(); f.seed_instance(seed)
    if any(ch.isdigit() for ch in t):
        return re.sub(r'\d', '#', t)
    if len(t) <= 12 and t.isalpha():
        nm = f.first_name()
        if t.istitle():
            return nm
        if t.isupper():
            return nm.upper()
        return nm.lower()
    w = f.word()[:max(3, min(12, len(t)))]
    return w

# -------------------- Helpers --------------------
def expand_bbox(bbox, image_size, pad=6):
    x0,y0,x1,y1 = bbox
    x0 = max(0, int(x0) - pad)
    y0 = max(0, int(y0) - pad)
    x1 = min(image_size[0], int(x1) + pad)
    y1 = min(image_size[1], int(y1) + pad)
    return [x0,y0,x1,y1]

def area_intersection(a,b):
    ax0,ay0,ax1,ay1 = a; bx0,by0,bx1,by1 = b
    interW = max(0, min(ax1,bx1) - max(ax0,bx0))
    interH = max(0, min(ay1,by1) - max(ay0,by0))
    return interW * interH

# -------------------- OCR --------------------
def pdf_to_images(pdf_path: str, dpi:int = PDF_DPI) -> List[Image.Image]:
    pages = convert_from_path(pdf_path, dpi=dpi)
    if not pages:
        raise RuntimeError("Failed to rasterize PDF. Ensure poppler/pdftoppm is installed.")
    return [p.convert("RGB") for p in pages]

def preprocess_for_ocr(pil_img: Image.Image):
    img = pil_img.convert("RGB")
    max_dim = 4000
    if max(img.width, img.height) > max_dim:
        scale = max_dim / max(img.width, img.height)
        img = img.resize((int(img.width*scale), int(img.height*scale)), Image.LANCZOS)
    gray = ImageOps.grayscale(img)
    gray = ImageOps.autocontrast(gray)
    gray = gray.filter(ImageFilter.MedianFilter(size=3))
    return gray

def ocr_image_tokens_tesseract(pil_img: Image.Image, tesseract_lang: str = "eng"):
    img_proc = preprocess_for_ocr(pil_img)
    config = f"--oem {OCR_OEM} --psm {OCR_PSM}"
    if tesseract_lang:
        config = f"-l {tesseract_lang} " + config
    data = pytesseract.image_to_data(img_proc, output_type=Output.DICT, config=config)
    tokens = []
    for i, txt in enumerate(data.get("text", [])):
        if not txt or not str(txt).strip(): continue
        try:
            left = int(data["left"][i]); top = int(data["top"][i]); w = int(data["width"][i]); h = int(data["height"][i])
        except Exception:
            continue
        tokens.append({"text": txt, "left": left, "top": top, "width": w, "height": h})
    joined_text = " ".join(t["text"] for t in tokens)
    return joined_text, tokens

def ocr_image_tokens_easyocr(pil_img: Image.Image, langs: List[str]=["en"]):
    if not _EASYOCR_AVAILABLE:
        raise RuntimeError("easyocr not available - install with `pip install easyocr`")
    reader = easyocr.Reader(langs, gpu=torch.cuda.is_available())
    arr = np.array(pil_img)
    results = reader.readtext(arr)
    tokens = []
    for (bbox, text, conf) in results:
        # bbox is [[x0,y0],[x1,y1],[x2,y2],[x3,y3]]
        x0 = min(p[0] for p in bbox); y0 = min(p[1] for p in bbox)
        x2 = max(p[0] for p in bbox); y2 = max(p[1] for p in bbox)
        tokens.append({"text": text, "left": int(x0), "top": int(y0), "width": int(x2-x0), "height": int(y2-y0)})
    joined_text = " ".join(t["text"] for t in tokens)
    return joined_text, tokens

def normalize_ocr_boxes(tokens: List[Dict[str,int]], pil_img: Image.Image, original_dpi:int = PDF_DPI):
    # Some tesseract/image pipelines may produce boxes relative to a different DPI.
    # If PIL image has DPI info, use it to scale; otherwise assume identity.
    dpi_info = pil_img.info.get("dpi", (original_dpi, original_dpi))
    scale = dpi_info[0] / original_dpi if original_dpi else 1.0
    if abs(scale - 1.0) < 1e-6:
        return tokens
    normed = []
    for t in tokens:
        box = {**t}
        box['left'] = int(round(t['left'] * scale))
        box['top'] = int(round(t['top'] * scale))
        box['width'] = int(round(t['width'] * scale))
        box['height'] = int(round(t['height'] * scale))
        normed.append(box)
    return normed

# -------------------- NER --------------------
def load_ner_pipelines():
    global _NER_PIPELINES, _NER_LOADED
    if _NER_LOADED:
        return _NER_PIPELINES
    device = 0 if torch.cuda.is_available() else -1
    pipes = []
    for model_name in AI_MODELS:
        try:
            p = pipeline("ner", model=model_name, aggregation_strategy="simple", device=device)
            pipes.append(p)
        except Exception as e:
            print(f"[WARN] Could not load NER model '{model_name}': {e}")
    _NER_PIPELINES = pipes
    _NER_LOADED = True
    return _NER_PIPELINES

def run_dual_ner(text: str) -> List[Dict[str,Any]]:
    pipes = load_ner_pipelines()
    preds = []
    for p in pipes:
        try:
            out = p(text)
            for o in out:
                preds.append(o)
        except Exception as e:
            print("[WARN] NER pipeline failed:", e)
    return preds

# -------------------- Regex / heuristics --------------------
ID_PATTERNS = [
    (re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"), "B-DOC"),
    (re.compile(r"\b(?:\d{4}\s\d{4}\s\d{4}|\d{12})\b"), "B-DOC"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "B-DOC"),
    (re.compile(r"\b\d{9}\b"), "B-DOC"),
    (re.compile(r"\b[A-CEGHJ-PR-TW-Z]{2}\d{6}[A-D]?\b"), "B-DOC"),
    (re.compile(r"\b[A-Z]\d{7}\b"), "B-DOC"),
    (re.compile(r"\b\d{2}/\d{2}/\d{4}\b"), "B-DATE"),
    (re.compile(r"\b\d{2}-\d{2}-\d{4}\b"), "B-DATE"),
    (re.compile(r"\b\d{4}-\d{2}-\d{2}\b"), "B-DATE"),
    (re.compile(r"\b\d{5,7}\b"), "B-LOC"),
]

ADDRESS_KEYWORDS = [
    "road","rd","street","st","nagar","colony","sector","lane","plot","building","bldg",
    "flat","apartment","opp","near","behind","block","phase","society","village","town","city",
    "district","state","province","maharashtra","mumbai","pin","pincode","postcode","zip","zip code",
    "avenue","boulevard"
]

def canonicalize_label(label_str):
    s = str(label_str).upper()
    if s in ("O","0"): return "O"
    if "PAN" in s or "DOC" in s or "PASSPORT" in s or "ID" in s or "SSN" in s or "AADHAAR" in s:
        return "B-DOC"
    if "PER" in s or "NAME" in s or "PERSON" in s:
        return "B-PER"
    if "LOC" in s or "CITY" in s or "STATE" in s or "ADDRESS" in s or "POST" in s or "PIN" in s:
        return "B-LOC"
    if "ORG" in s:
        return "B-ORG"
    if "DATE" in s or "DOB" in s:
        return "B-DATE"
    return "B-MISC"

def merge_adjacent_on_line(sorted_tokens):
    merged = []
    cur = None
    for t in sorted_tokens:
        if cur is None:
            cur = t.copy()
        else:
            same_line = abs(t["top"] - cur["top"]) <= max(8, int(0.02 * t["height"]))
            gap = t["left"] - (cur["left"] + cur["width"])
            # Stricter: only merge small gaps and avoid merging when cur already has several words
            if same_line and 0 <= gap <= max(15, int(0.15 * t["width"])) and len(cur["text"].split()) < 5:
                cur["text"] = cur["text"] + " " + t["text"]
                new_right = t["left"] + t["width"]
                cur["width"] = new_right - cur["left"]
            else:
                merged.append(cur)
                cur = t.copy()
    if cur: merged.append(cur)
    return merged

def add_regex_based_detections(full_text: str, tokens: List[Dict[str,int]]):
    detections = []
    txt = full_text
    for pat,label in ID_PATTERNS:
        for m in pat.finditer(txt):
            match = m.group().strip()
            if not match: continue
            detections.append({"word": match, "label": label, "span": (m.start(), m.end())})
    low = txt.lower()
    for kw in ADDRESS_KEYWORDS:
        start = 0
        while True:
            idx = low.find(kw, start)
            if idx == -1: break
            span_start = max(0, idx - 40)
            span_end = min(len(txt), idx + len(kw) + 60)
            snippet = txt[span_start:span_end]
            detections.append({"word": snippet, "label": "B-LOC", "span": (span_start, span_end)})
            start = idx + 1

    mapped = []
    token_texts = [t["text"] for t in tokens]
    for r in detections:
        rw = r["word"].lower().strip()
        found = False
        for i,t in enumerate(tokens):
            if rw == t["text"].lower():
                bbox = [t["left"], t["top"], t["left"]+t["width"], t["top"]+t["height"]]
                mapped.append({"word": t["text"], "bbox": bbox, "label": canonicalize_label(r["label"])})
                found = True; break
        if found: continue
        for i in range(len(tokens)):
            for w in range(1,9):
                window = " ".join([tokens[j]["text"] for j in range(i, min(i+w, len(tokens)))])
                if fuzz.partial_ratio(rw, window.lower()) >= 70:
                    xs=[tokens[j]["left"] for j in range(i, min(i+w,len(tokens)))]
                    ys=[tokens[j]["top"] for j in range(i, min(i+w,len(tokens)))]
                    x2s=[tokens[j]["left"]+tokens[j]["width"] for j in range(i, min(i+w,len(tokens)))]
                    y2s=[tokens[j]["top"]+tokens[j]["height"] for j in range(i, min(i+w,len(tokens)))]
                    bbox=[min(xs), min(ys), max(x2s), max(y2s)]
                    mapped.append({"word": window, "bbox": bbox, "label": canonicalize_label(r["label"])})
                    found = True; break
            if found: break
    return mapped

# -------------------- Mapping NER to tokens --------------------
def map_ner_to_tokens(ner_preds, tokens, full_text, image_size=(2000,2000)):
    token_texts = [t["text"] for t in tokens]
    joined = " ".join(token_texts).lower()
    detections = []
    detected_names = set()

    ner_spans = []
    for n in ner_preds:
        word = n.get("word") or n.get("entity") or n.get("entity_group") or n.get("label") or ""
        if not word: continue
        label = n.get("entity_group") or n.get("entity") or n.get("label") or ""
        score = float(n.get("score", 0.0))
        ner_spans.append({"word": word.strip(), "label": label, "score": score})

    for span in ner_spans:
        s = span["word"].strip()
        s_low = s.lower()
        if s_low and s_low in joined:
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
                xs=[tokens[j]["left"] for j in range(start_idx,end_idx+1)]
                ys=[tokens[j]["top"] for j in range(start_idx,end_idx+1)]
                x2s=[tokens[j]["left"]+tokens[j]["width"] for j in range(start_idx,end_idx+1)]
                y2s=[tokens[j]["top"]+tokens[j]["height"] for j in range(start_idx,end_idx+1)]
                bbox=[min(xs), min(ys), max(x2s), max(y2s)]
                detections.append({"word":" ".join(token_texts[start_idx:end_idx+1]), "bbox":bbox, "label":canonicalize_label(span["label"]), "score":span["score"]})
                if "PER" in span["label"].upper() or "NAME" in span["label"].upper():
                    detected_names.add(" ".join(token_texts[start_idx:end_idx+1]).lower())
                continue
        best_i=None; best_score=0
        for i,t in enumerate(tokens):
            sc = fuzz.token_set_ratio(s_low, t["text"].lower())
            if sc > best_score:
                best_score=sc; best_i=i
        if best_score >= 75 and best_i is not None:
            t = tokens[best_i]
            bbox=[t["left"],t["top"],t["left"]+t["width"],t["top"]+t["height"]]
            detections.append({"word": t["text"], "bbox":bbox, "label": canonicalize_label(span["label"]), "score": span.get("score", 0.0)})
            if "PER" in span["label"].upper() or "NAME" in span["label"].upper():
                detected_names.add(t["text"].lower())
            continue
        for i in range(len(tokens)):
            window = " ".join([tokens[j]["text"] for j in range(i, min(i+4,len(tokens)))])
            if fuzz.partial_ratio(s_low, window.lower()) >= 70:
                xs=[tokens[j]["left"] for j in range(i, min(i+4,len(tokens)))]
                ys=[tokens[j]["top"] for j in range(i, min(i+4,len(tokens)))]
                x2s=[tokens[j]["left"]+tokens[j]["width"] for j in range(i, min(i+4,len(tokens)))]
                y2s=[tokens[j]["top"]+tokens[j]["height"] for j in range(i, min(i+4,len(tokens)))]
                bbox=[min(xs), min(ys), max(x2s), max(y2s)]
                detections.append({"word":window, "bbox":bbox, "label":canonicalize_label(span["label"]), "score": span.get("score", 0.0)})
                if "PER" in span["label"].upper() or "NAME" in span["label"].upper():
                    detected_names.add(window.lower())
                break

    regex_mapped = add_regex_based_detections(full_text, tokens)
    for r in regex_mapped:
        if not r.get("bbox"): continue
        r["bbox"] = [int(x) for x in r["bbox"]]
        r["label"] = canonicalize_label(r.get("label",""))
        detections.append(r)

    sorted_tokens = sorted(tokens, key=lambda t:(t["top"], t["left"]))
    merged_line_tokens = merge_adjacent_on_line(sorted_tokens)
    seen_boxes = set()
    final = []
    for d in detections:
        if not d.get("bbox"): continue
        bx0,by0,bx1,by1 = map(int, d["bbox"])
        bx0,by0,bx1,by1 = expand_bbox([bx0,by0,bx1,by1], image_size, pad=4)
        key = (bx0,by0,bx1,by1,d.get("label",""))
        if key in seen_boxes:
            continue
        seen_boxes.add(key)
        final.append({"word": d.get("word",""), "bbox":[bx0,by0,bx1,by1], "label": d.get("label","O"), "score": d.get("score", 0.0)})

    person_words = [d["word"].lower() for d in final if "PER" in d.get("label","")]
    for i,t in enumerate(tokens):
        tw_low = t["text"].lower()
        for pw in person_words:
            if tw_low == pw or fuzz.ratio(pw, tw_low) >= 88 or fuzz.partial_ratio(pw, tw_low) >= 85:
                bbox=[t["left"], t["top"], t["left"]+t["width"], t["top"]+t["height"]]
                key = tuple(map(int,bbox)) + ("B-PER",)
                if key not in seen_boxes:
                    final.append({"word": t["text"], "bbox": bbox, "label": "B-PER"})
                    seen_boxes.add(key)
                    break

    filtered = []
    for d in final:
        bx0,by0,bx1,by1 = map(int, d["bbox"])
        w = max(0, bx1 - bx0); h = max(0, by1 - by0)
        if w < MIN_BOX_WH or h < MIN_BOX_WH: continue
        filtered.append(d)

    filtered_sorted = sorted(filtered, key=lambda x:(x["bbox"][1], x["bbox"][0]))
    merged = []
    for d in filtered_sorted:
        if not merged:
            merged.append(d); continue
        last = merged[-1]
        inter = area_intersection(last["bbox"], d["bbox"])
        if inter > 0:
            x0 = min(last["bbox"][0], d["bbox"][0])
            y0 = min(last["bbox"][1], d["bbox"][1])
            x1 = max(last["bbox"][2], d["bbox"][2])
            y1 = max(last["bbox"][3], d["bbox"][3])
            merged[-1] = {"word": last["word"] + " " + d["word"], "bbox":[x0,y0,x1,y1], "label": last["label"] if last["label"]==d["label"] else last["label"]}
        else:
            merged.append(d)
    return merged

# -------------------- Redaction --------------------
def redact_image_flat(pil_img: Image.Image, detections: List[Dict[str,Any]], mode="mask", pad_px=PAD_PIXELS):
    img = pil_img.copy().convert("RGB")
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    for d in detections:
        if not d.get("bbox"): continue
        x0,y0,x1,y1 = d["bbox"]
        x0, x1 = sorted([int(round(x0)), int(round(x1))])
        y0, y1 = sorted([int(round(y0)), int(round(y1))])
        x0, y0, x1, y1 = expand_bbox([x0,y0,x1,y1], (img.width, img.height), pad=pad_px)
        if x1 <= x0 or y1 <= y0:
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
    kernel = np.ones((9,9), np.uint8)
    mask = cv2.dilate(mask, kernel, iterations=1)
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
    try:
        inpainted = cv2.inpaint(image_bgr, mask, 3, cv2.INPAINT_TELEA)
        return inpainted
    except Exception as e:
        print("[WARN] OpenCV inpaint failed:", e)
        return image_bgr.copy()

# -------------------- Privacy-first saving --------------------
def save_labeled_example(tokens: List[Dict[str,int]], labels: List[str]):
    ts = now_ts()
    jpath = DATASETS_DIR / f"example_{ts}_{random.randint(0,9999)}.jsonl"
    anon_words = [deterministic_synthetic_for_token(t["text"]) for t in tokens]
    boxes = [[t["left"], t["top"], t["left"]+t["width"], t["top"]+t["height"]] for t in tokens]
    rec = {"words": anon_words, "boxes": boxes, "labels": labels}
    with open(jpath, "w", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    print("[INFO] Saved anonymized labeled example:", jpath)
    return str(jpath)

# -------------------- Synthetic generation --------------------
FIRST = ["Shriyash","Vaishali","Santosh","Kamlakar","Ravi","Asha","Rahul","Priya","Anil","Sunita","Deepak","Sanjay","Pooja"]
LAST = ["Mhatre","Patil","Sharma","Kumar","Deshmukh","Joshi","Mehta","Bhandari","Ghosh","Khan","Reddy","Iyer"]

def gen_passport():
    return random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") + "".join(str(random.randint(0,9)) for _ in range(7))

def gen_dob():
    y = random.randint(1970,2010); m = random.randint(1,12); d = random.randint(1,28)
    return f"{d:02d}/{m:02d}/{y}"

def gen_pan():
    return "".join(random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ") for _ in range(5)) + \
           "".join(random.choice("0123456789") for _ in range(4)) + \
           random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")

def gen_aadhaar():
    s = "".join(random.choice("0123456789") for _ in range(12))
    if random.random() < 0.6:
        return f"{s[0:4]} {s[4:8]} {s[8:12]}"
    return s

def generate_pan_examples(n=200):
    exs = []
    templates = ["PAN: {pan}", "My PAN number is {pan}", "Permanent Account Number - {pan}", "PAN card {pan}", "{pan} is the PAN assigned"]
    for _ in range(n):
        pan = gen_pan(); t = random.choice(templates).format(pan=pan)
        words = t.split(); labels = ["O"] * len(words)
        for i,w in enumerate(words):
            if w == pan: labels[i] = "B-DOC"
        exs.append({"words": words, "labels": labels, "text": t})
    return exs

def generate_aadhaar_examples(n=200):
    exs = []
    templates = ["Aadhaar no {aad}", "Aadhaar: {aad}", "UIDAI number {aad}", "Aadhaar Card {aad}", "{aad} is the Aadhaar number"]
    for _ in range(n):
        aad = gen_aadhaar(); t = random.choice(templates).format(aad=aad)
        words = t.split(); labels = ["O"] * len(words)
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
        dob = gen_dob(); passport = gen_passport()
        city = random.choice(["Navi Mumbai","Pune","Mumbai","Alibag","Thane"])
        pincode = random.choice(["400070","400701","400707","400089","400089"])
        addr = f"{random.randint(1,300)} MG Road, {city}, Maharashtra, India - {pincode}"
        text = f"Name: {name} DOB: {dob} Passport: {passport} Address: {addr}"
        words = text.split(); labels = []
        for w in words:
            w_clean = w.strip(",:-")
            if w_clean in (fname, mid, lname): labels.append("B-PER")
            elif re.fullmatch(r'\d{2}/\d{2}/\d{4}', w_clean): labels.append("B-DATE")
            elif re.fullmatch(r'[A-Z]\d{7}', w_clean): labels.append("B-DOC")
            elif re.fullmatch(r'\d{6}', w_clean): labels.append("B-LOC")
            else: labels.append("O")
        exs.append({"words": words, "labels": labels, "text": text})
    exs.extend(generate_pan_examples(n // 4)); exs.extend(generate_aadhaar_examples(n // 4))
    return exs

# -------------------- Build + Fine-tune --------------------
def build_token_classification_dataset(jsonl_paths: List[Path], synthetic_examples: List[Dict[str,Any]], tokenizer):
    seqs = []
    for p in jsonl_paths:
        try:
            for line in open(p, "r", encoding="utf-8"):
                rec = json.loads(line); words = rec.get("words", []); labels = rec.get("labels", [])
                if words and labels: seqs.append({"words": words, "labels": labels})
        except Exception:
            continue
    real_count = max(1, len(seqs))
    max_allowed_synth = max(50, min(len(synthetic_examples), real_count * MAX_SYNTH_RATIO))
    sampled_synth = synthetic_examples[:max_allowed_synth]
    for s in sampled_synth:
        if any(l != "O" for l in s.get("labels", [])):
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

def fine_tune_bert_ner():
    jsonl_files = sorted(Path(DATASETS_DIR).glob("example_*.jsonl"))
    synth_pool = generate_synthetic_examples(n=SYNTH_COUNT)
    tokenizer = AutoTokenizer.from_pretrained(BERT_FINETUNE_BASE, use_fast=True)
    train_ds, label_list = build_token_classification_dataset(jsonl_files, synth_pool, tokenizer)
    if train_ds is None:
        print("[WARN] No training examples after tokenization. Skipping fine-tune.")
        return None
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
        model = AutoModelForTokenClassification.from_pretrained(BERT_FINETUNE_BASE, config=config, ignore_mismatched_sizes=True)
    except TypeError:
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
    print(f"[INFO] Fine-tuning on {len(train_ds)} examples (anonymized + synthetic).")
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
    ap.add_argument("--lang", default="eng", help="Tesseract languages (e.g. 'eng+hin')")
    ap.add_argument("--use-easyocr", action="store_true", help="Use easyocr instead of pytesseract (optional)")
    args = ap.parse_args()

    if args.use_easyocr and not _EASYOCR_AVAILABLE:
        print("[WARN] easyocr requested but not installed. Falling back to pytesseract.")
        args.use_easyocr = False

    pil_pages = pdf_to_images(args.input, dpi=PDF_DPI)
    print(f"[INFO] PDF contains {len(pil_pages)} pages. Processing at {PDF_DPI} DPI.")

    redacted_images = []
    for page_no, pil_img in enumerate(pil_pages):
        print(f"[INFO] Page {page_no+1}/{len(pil_pages)}: OCR ...")
        if args.use_easyocr:
            # pass language array to easyocr
            langs = [l for l in args.lang.split("+") if l]
            full_text, tokens = ocr_image_tokens_easyocr(pil_img, langs=langs)
        else:
            full_text, tokens = ocr_image_tokens_tesseract(pil_img, tesseract_lang=args.lang)
        tokens = normalize_ocr_boxes(tokens, pil_img, original_dpi=PDF_DPI)
        print(f"[INFO] OCR tokens: {len(tokens)} chars_text={len(full_text)}")

        ner_preds = run_dual_ner(full_text)
        detections = map_ner_to_tokens(ner_preds, tokens, full_text, image_size=(pil_img.width, pil_img.height))

        for pat,lab in ID_PATTERNS:
            for m in pat.finditer(full_text):
                match = m.group().strip()
                if not match: continue
                if any(match.replace(" ","") in d.get("word","").replace(" ","") for d in detections): continue
                for i,t in enumerate(tokens):
                    if match.replace(" ","").lower() == t["text"].replace(" ","").lower():
                        bbox=[t["left"], t["top"], t["left"]+t["width"], t["top"]+t["height"]]
                        detections.append({"word": match, "bbox": bbox, "label": canonicalize_label(lab)})
                        break

        keymap = {}
        for d in detections:
            if not d.get("bbox"): continue
            k = (int(d["bbox"][0]), int(d["bbox"][1]), int(d["bbox"][2]), int(d["bbox"][3]), d.get("label",""), d.get("word",""))
            if k not in keymap:
                keymap[k] = d
        detections = sorted(keymap.values(), key=lambda x: (x["bbox"][1], x["bbox"][0]))

        print(f"[INFO] Detected {len(detections)} sensitive spans on page {page_no+1}")
        for i,d in enumerate(detections, start=1):
            print(f"  DET {i}: {d['label']} '{d.get('word','')}' bbox={d.get('bbox')} score={d.get('score',0.0)}")

        token_labels = ["O"] * len(tokens)
        for d in detections:
            bx0,by0,bx1,by1 = map(int, d["bbox"])
            for idx,t in enumerate(tokens):
                tx0,ty0,tx1,ty1 = t["left"], t["top"], t["left"]+t["width"], t["top"]+t["height"]
                interW = max(0, min(bx1,tx1)-max(bx0,tx0))
                interH = max(0, min(by1,ty1)-max(by0,ty0))
                if interW*interH > 0:
                    token_labels[idx] = d["label"]

        save_labeled_example(tokens, token_labels)

        if args.redact_mode == "inpaint":
            regions = [(int(b["bbox"][0]), int(b["bbox"][1]), int(b["bbox"][2]-b["bbox"][0]), int(b["bbox"][3]-b["bbox"][1])) for b in detections]
            img_bgr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
            res_bgr = inpaint_regions_with_lama_or_opencv(img_bgr, regions, args.lama_repo, args.lama_ckpt)
            redacted_page = Image.fromarray(cv2.cvtColor(res_bgr, cv2.COLOR_BGR2RGB))
        else:
            redacted_page = redact_image_flat(pil_img, detections, mode=args.redact_mode)

        redacted_images.append(redacted_page)
        print(f"[INFO] Page {page_no+1} redacted.")

    out_pdf = OUTPUTS_DIR / f"redacted_{now_ts()}.pdf"
    if len(redacted_images) == 0:
        print("[ERROR] No pages processed."); return
    if len(redacted_images) == 1:
        redacted_images[0].save(out_pdf, "PDF")
    else:
        redacted_images[0].save(out_pdf, save_all=True, append_images=redacted_images[1:], format="PDF")
    print("[INFO] Final redacted PDF saved to:", out_pdf)

    try:
        model_out = fine_tune_bert_ner()
        if model_out: print("[INFO] Auto fine-tune completed:", model_out)
    except Exception as e:
        print("[WARN] Auto fine-tune failed:", e)

if __name__ == "__main__":
    main()
