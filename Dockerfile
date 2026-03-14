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

# Try to install chord-extractor (Chordino VAMP plugin, Linux 64-bit only).
# Requires Python <3.12. If it fails for any reason, the app falls back to
# the librosa engine at runtime (see ChordinoEngine in chords.py).
RUN pip install --no-cache-dir chord-extractor || echo "chord-extractor unavailable, librosa fallback will be used"

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
