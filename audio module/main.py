import os
import re
import torch
import whisperx
from transformers import pipeline
from pydub import AudioSegment
from pydub.generators import Sine

# ================= CONFIG ================= #

INPUT_DIR = "input"
OUTPUT_DIR = "output"

WHISPER_MODEL = "medium"
NER_MODEL = "dslim/bert-base-NER"

NER_LABELS = {"PER", "ORG", "LOC"}
BEEP_FREQ = 1000
MIN_BEEP_MS = 300

# ========================================= #

os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

device = 0 if torch.cuda.is_available() else -1
torch_device = "cuda" if device == 0 else "cpu"

print(f"🔥 Device: {torch_device}")

# ================= LOAD MODELS ================= #

print("📥 Loading WhisperX model...")
whisper_model = whisperx.load_model(
    WHISPER_MODEL,
    device=torch_device,
    compute_type="float16" if device == 0 else "float32"
)

print("📥 Loading NER model...")
ner = pipeline(
    "ner",
    model=NER_MODEL,
    aggregation_strategy="simple",
    device=device
)

# ================= CORE ================= #

def run_audio_redaction(input_path: str, output_path: str,mode: str = "beep"):
    print(f"\n🎧 Processing audio...")

    audio = AudioSegment.from_file(input_path).set_channels(1)
    print("Redaction level: ", mode)

    print("📝 Transcribing...")
    result = whisper_model.transcribe(input_path)

    language = result.get("language", "en")
    print(f"🌍 Language: {language}")

    if not result.get("segments"):
        raise ValueError("Whisper returned no segments — audio may be silent or too short")

    print("⏱️ Aligning words...")
    align_model, metadata = whisperx.load_align_model(
        language_code=language,
        device=torch_device
    )

    aligned = whisperx.align(
        result["segments"],
        align_model,
        metadata,
        input_path,
        device=torch_device
    )

    words = aligned.get("word_segments", [])
    words = [w for w in words if "start" in w and "end" in w]

    if not words:
        raise ValueError("Alignment returned no words with timing data")

    print(f"✅ Words detected: {len(words)}")

    transcript = ""
    word_meta = []

    for w in words:
        start_char = len(transcript)
        token = w["word"]
        transcript += token + " "
        end_char = len(transcript)
        word_meta.append({
            "word": token,
            "start_char": start_char,
            "end_char": end_char,
            "start_time": w["start"],
            "end_time": w["end"],
        })

    transcript = transcript.strip()
    print(f"📄 Transcript: {transcript}")

    print("\n🔍 NER-based PII detection...")
    ner_results = ner(transcript)

    redacted_word_indices = set()
    redaction_intervals = []

    for ent in ner_results:
        if ent["entity_group"] not in NER_LABELS:
            continue
        print(f"❌ {ent['word']} | {ent['entity_group']}")
        for i, w in enumerate(word_meta):
            if not (w["end_char"] <= ent["start"] or w["start_char"] >= ent["end"]):
                redacted_word_indices.add(i)
                redaction_intervals.append((w["start_time"], w["end_time"]))

    print("\n🔍 Regex-based PII detection...")
    for match in re.finditer(r"\d{3}[-\s]?\d{3}[-\s]?\d{4}", transcript):
        print(f"❌ {match.group()} | PHONE")
        for i, w in enumerate(word_meta):
            if not (w["end_char"] <= match.start() or w["start_char"] >= match.end()):
                redacted_word_indices.add(i)
                redaction_intervals.append((w["start_time"], w["end_time"]))

    redaction_intervals = sorted(redaction_intervals)
    merged_intervals = []
    for start, end in redaction_intervals:
        if not merged_intervals or start > merged_intervals[-1][1]:
            merged_intervals.append([start, end])
        else:
            merged_intervals[-1][1] = max(merged_intervals[-1][1], end)

    print("\n🔊 Applying audio redaction...")
    beep = Sine(BEEP_FREQ).to_audio_segment(duration=MIN_BEEP_MS, volume=-18)

    redacted_audio = AudioSegment.empty()
    last_end_ms = 0

    for start, end in merged_intervals:
        start_ms = int(start * 1000)
        end_ms = int(end * 1000)
        redacted_audio += audio[last_end_ms:start_ms]
        duration = max(MIN_BEEP_MS, end_ms - start_ms)
        # redacted_audio += beep[:duration].fade_in(10).fade_out(10)
        if mode == "silence":
            redacted_audio += AudioSegment.silent(duration=duration)
        else:
            redacted_audio += beep[:duration].fade_in(10).fade_out(10)
        last_end_ms = end_ms

    redacted_audio += audio[last_end_ms:]
    redacted_audio.export(output_path, format="wav")
    print("✅ Redaction complete")

# ================= ENTRY ================= #

if __name__ == "__main__":
    audio_files = [
        f for f in os.listdir(INPUT_DIR)
        if f.lower().endswith((".wav", ".mp3", ".m4a", ".flac", ".ogg"))
    ]

    if not audio_files:
        raise RuntimeError("❌ No audio file found in input/")

    run_audio_redaction(os.path.join(INPUT_DIR, audio_files[0]))