from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
import os
import uuid
import shutil
import traceback
from pathlib import Path
from types import SimpleNamespace
from contextlib import asynccontextmanager
# import your existing script
import app3  # <-- your uploaded file name (rename if needed)


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Preloading NER models at startup...")
    app3.load_ner_pipelines()
    print("✅ NER models preloaded")

    print("🚀 Preloading EasyOCR model at startup...")
    from app3 import ocr_easyocr
    # Trigger reader creation with dummy image
    from PIL import Image
    dummy = Image.new("RGB", (10, 10), color="white")
    ocr_easyocr(dummy, ["en"])
    print("✅ EasyOCR preloaded")

    yield
    
app = FastAPI(
    title="PrivGuard PDF Redaction API",
    version="1.0.0",
    lifespan=lifespan
)

INPUT_DIR = Path("pdf_input")
OUTPUT_DIR = Path("pdf_output")

INPUT_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

@app.get("/")
def root():
    return "PDF Module is running on port 4000, use /health to check status and /api/pdf/redact to redact PDFs."


@app.get("/health")
def health():
    return {"status": "ok", "service": "pdf-redaction"}


@app.post("/api/pdf/redact")
async def redact_pdf(
    file: UploadFile = File(...),
    redact_level: int = Form(2),   # rl from Node.js
    lang: str = Form("eng")
):
    """
    Redact PDF with configurable redaction level
    Level 1 → Blur
    Level 2 → Mask
    Level 3 → Synth
    Level 4 → Inpaint
    """

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files allowed")

    job_id = str(uuid.uuid4())
    input_pdf_path = INPUT_DIR / f"{job_id}_{file.filename}"
    output_pdf_path = OUTPUT_DIR / f"{job_id}_redacted.pdf"

    # Save uploaded file
    with open(input_pdf_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        # Convert args similar to argparse
        args = SimpleNamespace(
            lang=lang,
            redact_level=redact_level
        )

        # Convert PDF → images
        pages = app3.pdf_to_images(str(input_pdf_path))

        redacted_pages = []
        all_detections = []

        for i, page in enumerate(pages, 1):
            redacted_page, detections = app3.process_page(page, i, args)
            redacted_pages.append(redacted_page)
            all_detections.append(detections)

        # Save PDF
        redacted_pages[0].save(
            output_pdf_path,
            save_all=True,
            append_images=redacted_pages[1:]
        )

    except Exception as e:
        print("🔥 FASTAPI ERROR:")
        traceback.print_exc()  # <-- THIS is critical
        raise HTTPException(status_code=500, detail=str(e))

    return FileResponse(
        path=output_pdf_path,
        media_type="application/pdf",
        filename="redacted.pdf"
    )
