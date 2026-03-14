FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    curl \
    libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install core Python dependencies (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Install chord-extractor (Chordino VAMP plugin, Linux 64-bit only).
# chord-extractor bundles nnls-chroma.so and auto-sets VAMP_PATH on Linux.
# Requires Python <3.12 — this image uses 3.11 so it installs fine.
# Falls back to librosa if unavailable (see ChordinoEngine in chords.py).
RUN pip install --no-cache-dir chord-extractor vamp

# Copy application code
COPY . .

# Create temp directory
RUN mkdir -p /tmp/worship_chords

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
