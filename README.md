# Worship Chord API

A production-ready FastAPI service that downloads a YouTube worship song, extracts chords via chromagram analysis, transcribes lyrics with Whisper, and returns a structured JSON payload ready for downstream chord-sheet or PDF generation.

---

## What It Does

1. Accepts a YouTube URL (or a direct audio file upload).
2. Downloads the audio with **yt-dlp**.
3. Converts it to a 16 kHz mono WAV with **ffmpeg**.
4. Runs a **librosa CQT chromagram** through a chord-template matcher to produce timed chord events.
5. Transcribes the audio with **faster-whisper** (CPU / int8 by default).
6. Aligns chord events to lyric segments by timestamp overlap, inserting inline chord markers (`[G]Amazing grace [C]how sweet`).
7. Returns a single structured JSON response: metadata, audio info, chord timeline, transcription, alignment blocks, and processing diagnostics.

---

## Local Setup

### Prerequisites

- Python 3.11+
- `ffmpeg` installed and on PATH (`ffmpeg -version` should work)
- `yt-dlp` (installed via pip as part of requirements)

### Steps

```bash
# 1. Clone / enter the project directory
cd worship-chord-api

# 2. Create and activate a virtual environment
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy environment variables
cp .env.example .env
# Edit .env as needed (defaults work out of the box)

# 5. Run the server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 6. Check the health endpoint
curl http://localhost:8000/health
```

The interactive API docs are available at `http://localhost:8000/docs`.

### Running Tests

```bash
pytest tests/ -v
```

The test suite covers chord normalization, alignment logic, model validation, and the health endpoint. Tests do not require ffmpeg or yt-dlp — they operate on pure Python logic and the FastAPI test client.

---

## Docker Setup

### Build and Run

```bash
# Build the image
docker build -t worship-chord-api .

# Run with default settings
docker run -p 8000:8000 worship-chord-api

# Run with custom environment variables
docker run -p 8000:8000 \
  -e WHISPER_MODEL_SIZE=small \
  -e LOG_LEVEL=DEBUG \
  -e MAX_AUDIO_DURATION_SECONDS=900 \
  worship-chord-api
```

### Docker Compose (optional)

```yaml
version: "3.9"
services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - WHISPER_MODEL_SIZE=base
      - WHISPER_DEVICE=cpu
      - WHISPER_COMPUTE_TYPE=int8
      - CHORD_ENGINE=librosa
      - MAX_AUDIO_DURATION_SECONDS=600
      - LOG_LEVEL=INFO
    volumes:
      - /tmp/worship_chords:/tmp/worship_chords
    restart: unless-stopped
```

---

## Railway Deployment

Railway is the recommended cloud host. The Docker image runs directly.

### Steps

1. Push this repository to GitHub.
2. In Railway, create a new project and select "Deploy from GitHub repo".
3. Railway detects the `Dockerfile` automatically.
4. Add environment variables in the Railway dashboard (see table below).
5. Set the exposed port to `8000` (Railway maps it via `$PORT` automatically — the app reads `PORT` from the environment).

### Recommended Railway Variables

| Variable | Recommended Value |
|---|---|
| `PORT` | `8000` |
| `WHISPER_MODEL_SIZE` | `base` (use `small` for better accuracy if memory allows) |
| `WHISPER_DEVICE` | `cpu` |
| `WHISPER_COMPUTE_TYPE` | `int8` |
| `CHORD_ENGINE` | `librosa` |
| `MAX_AUDIO_DURATION_SECONDS` | `600` |
| `LOG_LEVEL` | `INFO` |
| `ENVIRONMENT` | `production` |
| `TEMP_DIR` | `/tmp/worship_chords` |

Railway's free tier has limited RAM. Use `WHISPER_MODEL_SIZE=base` or `tiny` to stay within limits. The `base` model uses approximately 300 MB of RAM during inference.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `PORT` | `8000` | TCP port the server binds to |
| `LOG_LEVEL` | `INFO` | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `ENVIRONMENT` | `production` | Enables hot-reload when set to `development` |
| `MAX_AUDIO_DURATION_SECONDS` | `600` | Maximum allowed audio length in seconds (10 min) |
| `TEMP_DIR` | `/tmp/worship_chords` | Directory for temporary audio files |
| `WHISPER_MODEL_SIZE` | `base` | Whisper model: `tiny`, `base`, `small`, `medium`, `large-v2`, `large-v3` |
| `WHISPER_DEVICE` | `cpu` | Inference device: `cpu` or `cuda` |
| `WHISPER_COMPUTE_TYPE` | `int8` | Quantization: `int8`, `float16`, `float32` |
| `CHORD_ENGINE` | `librosa` | Chord extraction engine (currently only `librosa`) |
| `ENABLE_LLM_CLEANUP` | `false` | Reserved for future LLM-based lyric cleanup |
| `DEFAULT_LANGUAGE` | `en` | Fallback language hint for Whisper |

---

## API Endpoints

### `GET /health`

Returns server status and configuration summary.

**Response:**
```json
{
  "status": "ok",
  "version": "1.0.0",
  "app": "Worship Chord API",
  "environment": "production",
  "chord_engine": "librosa",
  "whisper_model": "base"
}
```

---

### `POST /process-youtube`

The primary endpoint. Downloads a YouTube video, extracts chords and transcription, and returns fully aligned data.

**Request body (JSON):**

| Field | Type | Required | Description |
|---|---|---|---|
| `youtube_url` | string | Yes | Full YouTube URL |
| `transcription` | string | No | Pre-written lyrics (skips Whisper if provided) |
| `language` | string | No | Language hint for Whisper (e.g. `"en"`, `"es"`) |
| `title` | string | No | Override song title |
| `artist` | string | No | Override artist name |
| `prefer_sharp_keys` | bool | No | Use sharps over flats (default: `true`) |
| `cleanup_lyrics` | bool | No | Apply rule-based ASR cleanup (default: `true`) |

**Example curl:**
```bash
curl -X POST http://localhost:8000/process-youtube \
  -H "Content-Type: application/json" \
  -d '{
    "youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "language": "en",
    "prefer_sharp_keys": true
  }'
```

**Example with provided transcription:**
```bash
curl -X POST http://localhost:8000/process-youtube \
  -H "Content-Type: application/json" \
  -d '{
    "youtube_url": "https://youtu.be/abc123",
    "transcription": "Amazing grace how sweet the sound\nThat saved a wretch like me",
    "title": "Amazing Grace",
    "artist": "John Newton"
  }'
```

---

### `POST /process-audio`

Same as `/process-youtube` but accepts a direct audio file upload instead of a YouTube URL. Accepts multipart/form-data.

**Form fields:**

| Field | Type | Required | Description |
|---|---|---|---|
| `file` | file | Yes | Audio file (.mp3, .wav, .flac, .m4a, .ogg, .opus, .webm, .aac) |
| `language` | string | No | Language hint |
| `transcription` | string | No | Pre-written lyrics |
| `title` | string | No | Song title |
| `artist` | string | No | Artist name |
| `prefer_sharp_keys` | bool | No | Default: `true` |
| `cleanup_lyrics` | bool | No | Default: `true` |

**Example curl:**
```bash
curl -X POST http://localhost:8000/process-audio \
  -F "file=@/path/to/song.mp3" \
  -F "language=en" \
  -F "title=How Great Is Our God" \
  -F "artist=Chris Tomlin"
```

---

### `POST /extract-chords`

Extracts chords only from an uploaded audio file. Faster than the full pipeline — no transcription.

**Form fields:** `file` (required), `prefer_sharp_keys` (optional, default: `true`)

**Example curl:**
```bash
curl -X POST http://localhost:8000/extract-chords \
  -F "file=@/path/to/song.wav" \
  -F "prefer_sharp_keys=true"
```

**Response:**
```json
{
  "success": true,
  "chord_engine": "librosa",
  "duration_seconds": 245.3,
  "chords": [
    {"start": 0.0, "end": 4.2, "label": "G", "raw_label": "G"},
    {"start": 4.2, "end": 8.5, "label": "C", "raw_label": "C"}
  ],
  "processing_seconds": 12.4
}
```

---

### `POST /transcribe`

Transcribes only an uploaded audio file using Whisper. No chord extraction.

**Form fields:** `file` (required), `language` (optional), `cleanup` (optional, default: `true`)

**Example curl:**
```bash
curl -X POST http://localhost:8000/transcribe \
  -F "file=@/path/to/song.mp3" \
  -F "language=en" \
  -F "cleanup=true"
```

---

## Full Response Structure (`/process-youtube` and `/process-audio`)

```json
{
  "success": true,
  "input": {
    "youtube_url": "https://...",
    "used_provided_transcription": false,
    "language": "en"
  },
  "metadata": {
    "title": "How Great Is Our God",
    "artist": "Chris Tomlin",
    "duration_seconds": 245.3
  },
  "audio": {
    "sample_rate": 16000,
    "channels": 1,
    "format": "wav"
  },
  "chords": [
    {"start": 0.0, "end": 4.2, "label": "G", "raw_label": "G", "confidence": null},
    {"start": 4.2, "end": 8.5, "label": "C", "raw_label": "C", "confidence": null}
  ],
  "transcription": {
    "source": "generated",
    "raw_text": "The splendor of the King clothed in majesty",
    "cleaned_text": "The splendor of the King clothed in majesty",
    "segments": [
      {"start": 0.5, "end": 4.1, "text": "The splendor of the King clothed in majesty"}
    ]
  },
  "alignment": {
    "method": "timestamp_overlap_v1",
    "blocks": [
      {
        "start": 0.5,
        "end": 4.1,
        "lyric": "The splendor of the King clothed in majesty",
        "active_chords": [
          {"position_hint": 0, "label": "G"}
        ],
        "display_line": "[G]The splendor of the King clothed in majesty"
      }
    ]
  },
  "diagnostics": {
    "warnings": [],
    "processing_seconds": 38.7,
    "download_engine": "yt-dlp",
    "chord_engine": "librosa",
    "transcription_engine": "faster-whisper(base)"
  }
}
```

---

## Error Responses

All errors follow a consistent structure:

```json
{
  "success": false,
  "error": {
    "code": "DOWNLOAD_FAILED",
    "message": "Video duration 720s exceeds maximum 600s"
  }
}
```

**Error codes:**

| Code | HTTP Status | Cause |
|---|---|---|
| `DOWNLOAD_FAILED` | 422 | yt-dlp could not download the video |
| `DOWNLOAD_ERROR` | 500 | Unexpected error during download |
| `AUDIO_CONVERSION_FAILED` | 422 | ffmpeg conversion failed |
| `AUDIO_ERROR` | 500 | Unexpected audio processing error |
| `PROCESSING_ERROR` | 500 | Unexpected error during chord/transcription pipeline |
| `UNSUPPORTED_FORMAT` | 422 | Uploaded file has an unsupported extension |
| `EMPTY_FILE` | 422 | Uploaded file is empty |
| `DURATION_EXCEEDED` | 422 | Audio is longer than `MAX_AUDIO_DURATION_SECONDS` |
| `CHORD_EXTRACTION_FAILED` | 500 | Chord engine error |
| `TRANSCRIPTION_FAILED` | 500 | Whisper engine error |
| `INTERNAL_ERROR` | 500 | Unhandled exception (see server logs) |

---

## n8n Usage Notes

This API is designed to integrate cleanly with n8n workflows.

### Recommended n8n Pattern

1. **HTTP Request node** — POST to `/process-youtube` with a JSON body containing `youtube_url`.
2. **Set node** — Extract `alignment.blocks` from the response for further processing.
3. **Loop Over Items** — Iterate over blocks to build a per-line chord sheet.
4. **HTTP Request node** — POST the structured data to your PDF generation service or Google Docs API.

### Tips for n8n

- Set the HTTP Request node timeout to at least **120 seconds**. Processing a 4-minute worship song with Whisper `base` typically takes 30-60 seconds on CPU.
- Use the `transcription` field in the request body to skip Whisper entirely if you already have the lyrics — this reduces response time to under 15 seconds.
- The `alignment.blocks[].display_line` field contains the final formatted line (e.g. `[G]Amazing grace [C]how sweet the sound`) and can be written directly to a document.
- Set `prefer_sharp_keys: false` if your worship team prefers flat notation (Bb, Eb, etc.).
- The `diagnostics.warnings` array surfaces non-fatal issues (e.g. chord extraction fallback) without causing a request failure.

### Example n8n HTTP Request Body (Expression)

```json
{
  "youtube_url": "{{ $json.youtube_url }}",
  "language": "en",
  "prefer_sharp_keys": true,
  "cleanup_lyrics": true
}
```

---

## Known Limitations

- **Chord accuracy**: The librosa chromagram approach works well for clearly harmonic, guitar-driven worship music. Dense orchestral arrangements or songs with heavy reverb/FX produce less accurate results. There is no confidence score in the current implementation.
- **Whisper hallucinations**: The `base` model occasionally hallucinates words, especially during instrumental sections. The VAD filter (`vad_filter=True`) mitigates this but does not eliminate it. Use a larger model (`small` or `medium`) for better accuracy.
- **Provided transcription alignment**: When `transcription` is provided by the caller, timestamps are not available. The alignment module assigns synthetic 1-second intervals per line, so `position_hint` values will not reflect real song timing. Chord-to-lyric placement is best-effort only.
- **YouTube availability**: yt-dlp depends on YouTube's current page structure. Age-restricted, region-locked, or premium-only videos will fail to download.
- **No GPU support in Docker by default**: The Dockerfile targets CPU inference. To use CUDA, change the base image to `nvidia/cuda:12.1.0-runtime-ubuntu22.04`, install the CUDA-compatible version of `ctranslate2`, and set `WHISPER_DEVICE=cuda`.
- **Temp file cleanup**: Temporary workspaces are cleaned after each request using the `temp_workspace` context manager. If the server crashes mid-request, orphaned files may accumulate in `TEMP_DIR`. A periodic cron to purge old subdirectories is recommended in production.
- **No authentication**: The API has no built-in authentication. Deploy behind a reverse proxy (Nginx, Caddy, Railway's private networking) or add an API key middleware before exposing publicly.
- **Memory**: The Whisper `base` model loads approximately 300 MB into RAM on first use and stays resident. The `large-v3` model requires approximately 3 GB RAM. Size your deployment accordingly.
- **Audio duration limit**: The default `MAX_AUDIO_DURATION_SECONDS=600` (10 minutes) covers most worship songs. Live recordings or extended sets will be rejected.
