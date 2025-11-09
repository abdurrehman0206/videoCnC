# Video to Audio Converter API

A simple Python API built with FastAPI to convert video files to MP3 audio format.

## Features

- Convert video files (mp4, avi, mov, etc.) to MP3 audio
- Clip videos at multiple start/end points and get all clips in a ZIP file
- RESTful API with FastAPI
- Automatic cleanup of temporary files
- Ready for Railway deployment

## Local Development

### Prerequisites

- Python 3.11+
- FFmpeg (required by moviepy)

### Installation

1. Install FFmpeg:
   - **Windows**: Download from [FFmpeg website](https://ffmpeg.org/download.html) or use `choco install ffmpeg`
   - **macOS**: `brew install ffmpeg`
   - **Linux**: `sudo apt-get install ffmpeg` or `sudo yum install ffmpeg`

2. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the API:
   ```bash
   python main.py
   ```

   Or using uvicorn directly:
   ```bash
   uvicorn main:app --reload
   ```

The API will be available at `http://localhost:8000`

## API Endpoints

### GET `/`
Returns API information and available endpoints.

### GET `/health`
Health check endpoint.

### POST `/convert`
Convert a video file to MP3 audio.

**Request:**
- Method: POST
- Content-Type: multipart/form-data
- Body: video file (form field: `file`)

**Response:**
- Content-Type: audio/mpeg
- Body: MP3 audio file

**Example using curl:**
```bash
curl -X POST "http://localhost:8000/convert" \
  -F "file=@your_video.mp4" \
  -o output.mp3
```

**Example using Python requests:**
```python
import requests

with open('video.mp4', 'rb') as f:
    response = requests.post('http://localhost:8000/convert', files={'file': f})
    with open('output.mp3', 'wb') as out:
        out.write(response.content)
```

### POST `/clip`
Clip a video at multiple start/end points and return all clips as a ZIP file.

**Request:**
- Method: POST
- Content-Type: multipart/form-data
- Body:
  - `file`: video file (form field)
  - `clips`: JSON string with array of clip definitions (form field)
    - Format: `[{"start": 10, "end": 20}, {"start": 30, "end": 40}]`
    - Times are in seconds
    - `start`: start time in seconds (must be >= 0)
    - `end`: end time in seconds (must be > start)

**Response:**
- Content-Type: application/zip
- Body: ZIP file containing all video clips

**Example using curl:**
```bash
curl -X POST "http://localhost:8000/clip" \
  -F "file=@your_video.mp4" \
  -F 'clips=[{"start": 10, "end": 20}, {"start": 30, "end": 40}]' \
  -o clips.zip
```

**Example using Python requests:**
```python
import requests
import json

clips = [
    {"start": 10, "end": 20},
    {"start": 30, "end": 40},
    {"start": 60, "end": 75}
]

with open('video.mp4', 'rb') as f:
    response = requests.post(
        'http://localhost:8000/clip',
        files={'file': f},
        data={'clips': json.dumps(clips)}
    )
    if response.status_code == 200:
        with open('clips.zip', 'wb') as out:
            out.write(response.content)
        print("✅ Clips created successfully!")
    else:
        print(f"❌ Error: {response.status_code} - {response.text}")
```

**Notes:**
- All clip times must be within the video duration
- Clips are returned as MP4 files in a ZIP archive
- Clip filenames follow the pattern `originalfilename_clip.mp4` when only one clip is requested, otherwise `originalfilename_clip_<number>.mp4`

## Railway Deployment

This project is ready for Railway deployment with multiple configuration options:

### Option 1: Using Nixpacks (Recommended)

The project includes a `nixpacks.toml` file that tells Railway to install FFmpeg automatically:

1. Create a new project on [Railway](https://railway.app)
2. Connect your GitHub repository or deploy directly from the CLI
3. Railway will automatically detect the `nixpacks.toml` and install FFmpeg
4. The server will start using the configuration in `nixpacks.toml`

### Option 2: Using Dockerfile

The project includes a `Dockerfile` for Docker-based deployment:

1. Create a new project on Railway
2. Connect your repository
3. Railway will detect the `Dockerfile` and build the Docker image
4. FFmpeg will be included in the Docker image

### Option 3: Standard Python Buildpack

If you want to use Railway's standard Python buildpack:

1. Ensure the `Procfile` is present (it is)
2. Railway will install Python dependencies from `requirements.txt`
3. **You'll need to add FFmpeg installation** via a build command or use a custom buildpack

### Deployment Steps

1. **Install Railway CLI** (optional):
   ```bash
   npm i -g @railway/cli
   ```

2. **Login to Railway**:
   ```bash
   railway login
   ```

3. **Initialize and deploy**:
   ```bash
   railway init
   railway up
   ```

   Or deploy directly from GitHub:
   - Go to [Railway Dashboard](https://railway.app/dashboard)
   - Click "New Project"
   - Select "Deploy from GitHub repo"
   - Choose your repository
   - Railway will automatically deploy

4. **Get your deployment URL**:
   - Railway will provide a public URL for your API
   - You can also set up a custom domain in the Railway dashboard

### Environment Variables

Railway automatically sets:
- `PORT`: The port your app should listen on (defaults to 8000 if not set)

No additional environment variables are required for basic functionality.

## Limitations

- File size limits depend on Railway's memory and timeout settings
- Large video files may require more processing time
- Temporary files are cleaned up after conversion

## License

MIT

