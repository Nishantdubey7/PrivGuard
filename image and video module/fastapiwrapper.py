import uuid
import shutil
import asyncio
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from fastapi import FastAPI, File, Form, UploadFile, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# ── your existing pipeline imports ──────────────────────────────────────────
from pipeline.video_pipeline import VideoPipeline
from pipeline.image_processor import ImageProcessor

from config.settings import RedactionMode
# ────────────────────────────────────────────────────────────────────────────

app = FastAPI(title="RE-DACT API")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ⚠️ for dev only
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Directories
UPLOAD_DIR  = Path("video_input")
OUTPUT_DIR  = Path("video_output")
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

IMAGE_UPLOAD_DIR = Path("image_input")
IMAGE_OUTPUT_DIR = Path("image_output")

IMAGE_UPLOAD_DIR.mkdir(exist_ok=True)
IMAGE_OUTPUT_DIR.mkdir(exist_ok=True)

# In-memory job store  {job_id: {"status": ..., "output": ..., "report": ..., "error": ...}}
jobs: dict[str, dict] = {}

# Thread pool so the blocking pipeline doesn't freeze the event loop
executor = ThreadPoolExecutor(max_workers=2)


# ── helpers ──────────────────────────────────────────────────────────────────

def _run_pipeline(job_id: str, video_path: Path, mode: int, identity_path: Optional[Path]):
    """Blocking pipeline call — runs in the thread pool."""
    try:
        jobs[job_id]["status"] = "processing"
        pipeline = VideoPipeline(
            mode=mode,
            identity_image_path=str(identity_path) if identity_path else None,
        )
        final_video, report_path = pipeline.process_video(str(video_path))
        jobs[job_id].update(
            status="done",
            output=final_video,
            report=report_path,
        )
    except Exception as exc:
        jobs[job_id].update(status="failed", error=str(exc))
    finally:
        # Clean up the uploaded source file
        video_path.unlink(missing_ok=True)
        if identity_path:
            identity_path.unlink(missing_ok=True)

def _run_image_pipeline(job_id: str, image_path: Path, mode: int, identity_path: Optional[Path]):
    try:
        jobs[job_id]["status"] = "processing"

        import cv2

        image = cv2.imread(str(image_path))
        if image is None:
            raise Exception("Failed to read image")

        processor = ImageProcessor(
            mode=mode,
            identity_image_path=str(identity_path) if identity_path else None
        )

        processed_image, stats = processor.process_image(image)

        # Save output
        filename = image_path.name
        output_path = IMAGE_OUTPUT_DIR / f"privguarded_{filename}"

        cv2.imwrite(str(output_path), processed_image)

        jobs[job_id].update(
            status="done",
            output=str(output_path),
        )

    except Exception as exc:
        jobs[job_id].update(status="failed", error=str(exc))

    finally:
        image_path.unlink(missing_ok=True)
        if identity_path:
            identity_path.unlink(missing_ok=True)

# ── routes ───────────────────────────────────────────────────────────────────
@app.get("/", summary="Landing page")
async def root():
    return {"message": "Welcome to the RE-DACT Video Redaction API. Use /video to submit videos."}


@app.post("/video", summary="Submit a video for redaction")
async def submit_redaction(
    video: UploadFile = File(..., description="Input video file"),
    mode: int = Form(..., ge=1, le=4, description="Redaction mode 1-4"),
    identity: Optional[UploadFile] = File(None, description="Identity reference image (mode 4 only)"),
):
    # ── validate mode 4 requirement ──
    if mode == RedactionMode.IDENTITY_PROTECT and identity is None:
        raise HTTPException(
            status_code=422,
            detail="An identity reference image is required for mode 4 (Identity Protection).",
        )

    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "queued", "output": None, "report": None, "error": None}

    # ── save uploaded files ──
    video_suffix = Path(video.filename).suffix or ".mp4"
    video_path   = UPLOAD_DIR / f"{job_id}_input{video_suffix}"
    with video_path.open("wb") as f:
        shutil.copyfileobj(video.file, f)

    identity_path = None
    if identity:
        id_suffix     = Path(identity.filename).suffix or ".jpg"
        identity_path = UPLOAD_DIR / f"{job_id}_identity{id_suffix}"
        with identity_path.open("wb") as f:
            shutil.copyfileobj(identity.file, f)

    # ── kick off pipeline in background thread ──
    loop = asyncio.get_event_loop()
    loop.run_in_executor(executor, _run_pipeline, job_id, video_path, mode, identity_path)

    return JSONResponse(
        status_code=202,
        content={"job_id": job_id, "status": "queued"},
    )


@app.post("/image", summary="Submit an image for redaction")
async def submit_image_redaction(
    image: UploadFile = File(...),
    mode: int = Form(..., ge=1, le=4),
    identity: Optional[UploadFile] = File(None),
):
    if mode == RedactionMode.IDENTITY_PROTECT and identity is None:
        raise HTTPException(
            status_code=422,
            detail="Identity image required for mode 4",
        )

    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "queued", "output": None, "error": None}

    # Save image
    suffix = Path(image.filename).suffix or ".jpg"
    image_path = IMAGE_UPLOAD_DIR / f"{job_id}_input{suffix}"

    with image_path.open("wb") as f:
        shutil.copyfileobj(image.file, f)

    # Save identity (optional)
    identity_path = None
    if identity:
        id_suffix = Path(identity.filename).suffix or ".jpg"
        identity_path = IMAGE_UPLOAD_DIR / f"{job_id}_identity{id_suffix}"

        with identity_path.open("wb") as f:
            shutil.copyfileobj(identity.file, f)

    # Run in background
    loop = asyncio.get_event_loop()
    loop.run_in_executor(
        executor,
        _run_image_pipeline,
        job_id,
        image_path,
        mode,
        identity_path
    )

    return JSONResponse(
        status_code=202,
        content={"job_id": job_id, "status": "queued"},
    )

@app.get("/status/{job_id}", summary="Poll job status")
def get_status(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")

    response = {"job_id": job_id, "status": job["status"]}
    if job["status"] == "failed":
        response["error"] = job["error"]
    return response


@app.get("/download/{job_id}", summary="Download the redacted video")
def download_video(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job["status"] != "done":
        raise HTTPException(
            status_code=409,
            detail=f"Video is not ready yet. Current status: {job['status']}",
        )

    output_path = Path(job["output"])
    if not output_path.exists():
        raise HTTPException(status_code=500, detail="Output file missing on server.")

    return FileResponse(
        path=str(output_path),
        media_type="video/mp4",
        filename=output_path.name,
        headers={"Content-Disposition": f'inline; filename="{output_path.name}"'},
    )

@app.get("/download-image/{job_id}", summary="Download redacted image")
def download_image(job_id: str):
    job = jobs.get(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"] != "done":
        raise HTTPException(
            status_code=409,
            detail=f"Image not ready. Status: {job['status']}"
        )

    output_path = Path(job["output"])

    if not output_path.exists():
        raise HTTPException(status_code=500, detail="Output missing")

    return FileResponse(
        path=str(output_path),
        media_type="image/jpeg",
        filename=output_path.name,
    )

@app.get("/report/{job_id}", summary="Download the privacy report")
def download_report(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job["status"] != "done":
        raise HTTPException(status_code=409, detail="Report not ready yet.")

    report_path = Path(job["report"])
    if not report_path.exists():
        raise HTTPException(status_code=500, detail="Report file missing on server.")

    return FileResponse(
        path=str(report_path),
        media_type="application/json",
        filename=report_path.name,
    )


# ── run directly ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("fastapiwrapper:app", host="127.0.0.1", port=7000, reload=True)