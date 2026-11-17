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


## Free phone test (Google Colab)

A no-hosting-cost test route is included in `colab_test.ipynb`. Open it in Google Colab using:

https://colab.research.google.com/github/danjonesmeta-dot/dans-comedy-clip-studio/blob/main/colab_test.ipynb

Run all cells from top to bottom. The notebook uses Colab's own upload control, transcribes the video, displays candidate moments, and exports selected clips as a ZIP. This uses Colab's free temporary runtime; GPU access is not guaranteed, sessions can disconnect, and files are temporary. Download exports before the session ends.

The hosted Docker version remains a separate deployment target; current Hugging Face Spaces documentation says free CPU hardware is not available for creating new Docker/Gradio compute Spaces on ordinary free personal accounts, so I am not relying on that route for a guaranteed-free test.
