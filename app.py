import json
import os
import re
import subprocess
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE = Path(__file__).parent
DATA = Path(os.getenv("UPLOAD_DIR", "/data"))
DATA.mkdir(parents=True, exist_ok=True)
MAX_BYTES = int(os.getenv("MAX_UPLOAD_MB", "2048")) * 1024 * 1024
MODEL_NAME = os.getenv("WHISPER_MODEL", "small")
JOBS = {}
LOCK = threading.Lock()
app = FastAPI(title="Dan's Comedy Clip Studio")
app.mount("/static", StaticFiles(directory=str(BASE / "static")), name="static")


def save_job(job_id):
    (DATA / job_id).mkdir(parents=True, exist_ok=True)


def run_transcription(job_id, video_path):
    try:
        with LOCK:
            JOBS[job_id]["status"] = "transcribing"
        from faster_whisper import WhisperModel
        model = WhisperModel(MODEL_NAME, device="cpu", compute_type="int8")
        segments, info = model.transcribe(str(video_path), word_timestamps=True, vad_filter=True)
        transcript = []
        for seg in segments:
            transcript.append({"start": round(seg.start, 2), "end": round(seg.end, 2), "text": seg.text.strip()})
        (DATA / job_id / "transcript.json").write_text(json.dumps(transcript, ensure_ascii=False, indent=2))
        suggestions = suggest_moments(transcript, info.duration or 0)
        (DATA / job_id / "clips.json").write_text(json.dumps(suggestions, indent=2))
        with LOCK:
            JOBS[job_id].update(status="ready", transcript=transcript, clips=suggestions,
                                duration=round(info.duration or 0, 2), progress=100)
    except Exception as exc:
        with LOCK:
            JOBS[job_id].update(status="error", error=str(exc))


def suggest_moments(segments, duration):
    # Lightweight first-pass ranking: punchy language, laughter cues, and nearby pauses.
    cues = re.compile(r"\b(why|because|literally|apparently|obviously|ridiculous|imagine|sorry|fuck|shit|hell|what\?)\b", re.I)
    candidates = []
    for i, seg in enumerate(segments):
        text = seg["text"]
        score = len(cues.findall(text)) * 2 + min(len(text) / 90, 2)
        if i + 1 < len(segments):
            gap = segments[i + 1]["start"] - seg["end"]
            if 0.35 < gap < 2.8:
                score += 1.2
        if score >= 1.5:
            start = max(0, seg["start"] - 9)
            end = min(duration, seg["end"] + 7)
            if end - start >= 8:
                candidates.append({"id": str(uuid.uuid4())[:8], "start": round(start, 2),
                                   "end": round(end, 2), "score": round(score, 2),
                                   "title": text[:90] or "Suggested moment", "selected": False})
    candidates.sort(key=lambda x: x["score"], reverse=True)
    # De-duplicate overlapping suggestions and keep the strongest 20.
    chosen = []
    for c in candidates:
        if all(c["end"] <= x["start"] or c["start"] >= x["end"] for x in chosen):
            chosen.append(c)
        if len(chosen) == 20:
            break
    return sorted(chosen, key=lambda x: x["start"])


@app.get("/", response_class=HTMLResponse)
def home():
    return (BASE / "static" / "index.html").read_text()


@app.post("/api/upload")
async def upload_video(file: UploadFile = File(...)):
    suffix = Path(file.filename or "video.mp4").suffix.lower()
    if suffix not in {".mp4", ".mov", ".mkv", ".webm", ".m4v"}:
        raise HTTPException(400, "Please upload an MP4, MOV, MKV, WEBM or M4V video.")
    job_id = str(uuid.uuid4())
    save_job(job_id)
    target = DATA / job_id / ("source" + suffix)
    size = 0
    try:
        with target.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_BYTES:
                    out.close()
                    target.unlink(missing_ok=True)
                    raise HTTPException(413, f"Video exceeds the {MAX_BYTES // (1024*1024)} MB upload limit.")
                out.write(chunk)
    finally:
        await file.close()
    JOBS[job_id] = {"id": job_id, "status": "queued", "filename": file.filename, "progress": 0}
    threading.Thread(target=run_transcription, args=(job_id, target), daemon=True).start()
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        # Recover job data after process restart if the output exists.
        p = DATA / job_id
        if (p / "clips.json").exists() and (p / "transcript.json").exists():
            return {"id": job_id, "status": "ready",
                    "clips": json.loads((p / "clips.json").read_text()),
                    "transcript": json.loads((p / "transcript.json").read_text())}
        raise HTTPException(404, "Job not found. Jobs are held in memory until the server restarts.")
    return job


class ClipRequest(BaseModel):
    start: float
    end: float
    title: str = "Comedy clip"


@app.post("/api/jobs/{job_id}/clips")
def update_clips(job_id: str, clips: list[dict]):
    if not (DATA / job_id).exists():
        raise HTTPException(404, "Job not found")
    clean = []
    for c in clips[:20]:
        start, end = float(c["start"]), float(c["end"])
        if start < 0 or end <= start:
            raise HTTPException(400, "Clip end must be after its start.")
        clean.append({"id": str(c.get("id", uuid.uuid4().hex[:8])), "start": start,
                      "end": end, "title": str(c.get("title", "Comedy clip"))[:100],
                      "selected": bool(c.get("selected", False))})
    (DATA / job_id / "clips.json").write_text(json.dumps(clean, indent=2))
    if job_id in JOBS:
        JOBS[job_id]["clips"] = clean
    return {"saved": len(clean)}


@app.post("/api/jobs/{job_id}/export")
def export_clips(job_id: str):
    folder = DATA / job_id
    source_files = list(folder.glob("source.*"))
    if not source_files:
        raise HTTPException(404, "Original video not found")
    clips_path = folder / "clips.json"
    if not clips_path.exists():
        raise HTTPException(400, "No clips have been saved")
    clips = [c for c in json.loads(clips_path.read_text()) if c.get("selected")]
    if not clips:
        raise HTTPException(400, "Select at least one clip before exporting")
    transcript_path = folder / "transcript.json"
    transcript = json.loads(transcript_path.read_text()) if transcript_path.exists() else []
    outputs = []
    for index, clip in enumerate(clips, 1):
        start, end = float(clip["start"]), float(clip["end"])
        out = folder / f"clip-{index:02d}.mp4"
        caption_lines = [s["text"] for s in transcript if s["end"] >= start and s["start"] <= end]
        subtitle = folder / f"clip-{index:02d}.srt"
        def stamp(seconds):
            ms = int(seconds * 1000)
            h, ms = divmod(ms, 3600000); m, ms = divmod(ms, 60000); sec, ms = divmod(ms, 1000)
            return f"{h:02}:{m:02}:{sec:02},{ms:03}"
        entries = []
        for s in transcript:
            a, b = max(s["start"], start), min(s["end"], end)
            if b > a:
                entries.append(f"{len(entries)+1}\n{stamp(a-start)} --> {stamp(b-start)}\n{s['text']}\n")
        subtitle.write_text("\n".join(entries), encoding="utf-8")
        escaped = str(subtitle).replace("\\", "/").replace(":", "\\:")
        cmd = ["ffmpeg", "-y", "-ss", str(start), "-i", str(source_files[0]), "-t", str(end-start),
               "-vf", f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,subtitles='{escaped}':force_style='FontSize=18,Outline=2,Shadow=1,Alignment=2,MarginV=150'",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "aac", "-b:a", "128k", str(out)]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode:
            raise HTTPException(500, "FFmpeg export failed: " + proc.stderr[-1200:])
        outputs.append({"name": out.name, "url": f"/api/jobs/{job_id}/download/{out.name}"})
    return {"exports": outputs}


@app.get("/api/jobs/{job_id}/download/{filename}")
def download(job_id: str, filename: str):
    if not re.fullmatch(r"clip-\d{2}\.mp4", filename):
        raise HTTPException(400, "Invalid filename")
    path = DATA / job_id / filename
    if not path.exists():
        raise HTTPException(404, "Clip not found")
    return FileResponse(path, media_type="video/mp4", filename=filename)
