# Dan's Comedy Clip Studio

A phone-first web app for turning long stand-up recordings into vertical, captioned clips.

## Features in this MVP
- Upload a video from an Android phone or desktop
- Background transcription with timestamps using faster-whisper
- Heuristic candidate-moment suggestions based on transcript cues and pauses
- Review and edit clip start/end times
- Render selected moments as 9:16 MP4s with burned-in subtitles
- Download finished clips

Candidate detection is an assistant, not a comedy judge: always review the suggested moments.

## Run with Docker
```bash
docker compose up --build
```
Then open `http://localhost:8000`.

## Cloud deployment
Deploy this repository as a Docker web service on a host that supports background processing, persistent disk, and large uploads. Attach a persistent volume at `/data`. Set `MAX_UPLOAD_MB` and choose a Whisper model via `WHISPER_MODEL`. The free tiers of hosting providers may not have enough RAM, CPU time, or persistent storage for long videos; check costs before enabling paid compute.

## Important
This MVP has no user accounts. Do not put private or sensitive footage on a public deployment until authentication and access controls have been added. Files are stored on the server's `UPLOAD_DIR`.
