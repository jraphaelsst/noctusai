# knowledge-extractor

Ingests recorded course classes from a Google Drive shared link, transcribes the
audio with OpenAI, and writes a summary of each video. Step 1 of turning a social-
media course's content into an automated media-creation platform.

This repo is structured as a **NoctusAI product in waiting** — see [`CLAUDE.md`](./CLAUDE.md)
for the methodology it follows and the absorption seam map.

## Quickstart

```bash
# 1. install (ffmpeg must already be on PATH — `brew install ffmpeg`)
python3 -m venv backend/.venv && source backend/.venv/bin/activate
pip install -r backend/requirements.txt

# 2. configure
cp .env.example .env          # then set OPENAI_API_KEY

# 3. verify (no keys/network needed — runs against fakes)
cd backend && pytest

# 4. run
cd backend
python -m app.cli run --fake                                  # demo, sample data
python -m app.cli run --video /path/to/class.mp4              # one local file
python -m app.cli run --drive-url "<drive-folder-share-link>" # the real flow
```

Outputs:

```
data/
  downloads/    raw videos pulled from Drive
  audio/        extracted + chunked audio
  transcripts/  <video>.md   full transcript
  summaries/    <video>.md   summary
  manifest.json index of everything processed
```

## How it works

`download (gdown) → extract audio (ffmpeg) → chunk → transcribe (OpenAI) →
summarize (OpenAI) → write files`. Each stage is a swappable seam wired by
dependency injection in `backend/app/pipeline.py`. See `CLAUDE.md` §3.

## Requirements

- Python 3.x, `ffmpeg` on PATH
- An OpenAI API key (for real transcription/summaries)
- A Google Drive folder shared as "anyone with the link can view"
