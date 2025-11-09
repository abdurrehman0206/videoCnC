FROM python:3.11-slim

# Install FFmpeg and MoviePy dependencies
RUN apt-get update && \
    apt-get install -y \
    ffmpeg \
    imagemagick \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY main.py .

# Create temp directory with proper permissions
# Use sh to expand PORT environment variable from Railway
CMD sh -c "mkdir -p temp && chmod 777 temp && uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"

