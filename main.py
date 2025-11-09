import os
import tempfile
import zipfile
import json
import shutil
import logging
import subprocess
from pathlib import Path
from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, Form
from fastapi.responses import FileResponse
from moviepy.editor import VideoFileClip
from moviepy.video.io.ffmpeg_tools import ffmpeg_extract_subclip
import uvicorn

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Video to Audio Converter API", version="1.0.0")

# Create temp directory if it doesn't exist
TEMP_DIR = Path("temp")
TEMP_DIR.mkdir(exist_ok=True)


@app.on_event("startup")
async def startup_event():
    """Initialize application and verify dependencies on startup"""
    logger.info("🚀 Starting Video to Audio Converter API...")
    logger.info(f"📁 TEMP_DIR: {TEMP_DIR.absolute()}")
    
    # Ensure temp directory exists with proper permissions
    TEMP_DIR.mkdir(exist_ok=True)
    try:
        os.chmod(TEMP_DIR, 0o777)
        logger.info("✅ Temp directory created with proper permissions")
    except Exception as e:
        logger.warning(f"⚠️ Could not set temp directory permissions: {e}")
    
    # Verify FFmpeg installation
    try:
        result = subprocess.run(
            ['ffmpeg', '-version'], 
            capture_output=True, 
            text=True, 
            timeout=5
        )
        if result.returncode == 0:
            version_line = result.stdout.split('\n')[0]
            logger.info(f"✅ FFmpeg is installed: {version_line}")
        else:
            logger.error("❌ FFmpeg check failed - return code non-zero")
    except FileNotFoundError:
        logger.error("❌ FFmpeg not found in PATH - video processing will fail!")
    except subprocess.TimeoutExpired:
        logger.error("❌ FFmpeg check timed out")
    except Exception as e:
        logger.error(f"❌ Error checking FFmpeg: {e}")
    
    port = os.getenv("PORT", "8000")
    logger.info(f"🌐 Server will start on port: {port}")
    logger.info("✅ API ready to accept requests")


@app.get("/")
async def root():
    return {
        "message": "Video to Audio Converter API",
        "endpoints": {
            "POST /convert": "Upload a video file and convert it to MP3",
            "POST /clip": "Upload a video file and clip it at specified start/end points",
            "GET /health": "Check API health status"
        }
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/convert")
async def convert_video_to_audio(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """
    Convert uploaded video file to MP3 audio.
    
    Accepts various video formats (mp4, avi, mov, etc.) and returns MP3 audio file.
    """
    # Validate file type
    if not file.content_type or not file.content_type.startswith("video/"):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Please upload a video file."
        )
    
    # Create temporary files
    video_ext = Path(file.filename).suffix if file.filename else ".mp4"
    temp_video_path = None
    temp_audio_path = None
    
    try:
        # Save uploaded video to temporary file
        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=video_ext,
            dir=TEMP_DIR
        ) as temp_video:
            content = await file.read()
            temp_video.write(content)
            temp_video_path = temp_video.name
        
        # Generate output audio filename
        audio_filename = Path(file.filename).stem + ".mp3" if file.filename else "output.mp3"
        temp_audio_path = TEMP_DIR / audio_filename
        
        # Convert video to audio using moviepy
        video = VideoFileClip(temp_video_path)
        video.audio.write_audiofile(
            str(temp_audio_path),
            codec='mp3',
            bitrate='192k',
            verbose=False,
            logger=None
        )
        video.close()
        
        # Check if audio file was created
        if not temp_audio_path.exists():
            cleanup_files([temp_video_path])
            raise HTTPException(
                status_code=500,
                detail="Failed to convert video to audio"
            )
        
        # Schedule cleanup after response is sent
        background_tasks.add_task(cleanup_files, [temp_video_path, str(temp_audio_path)])
        
        # Return the audio file
        return FileResponse(
            path=str(temp_audio_path),
            filename=audio_filename,
            media_type="audio/mpeg"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        # Cleanup on error
        cleanup_files([temp_video_path, str(temp_audio_path) if temp_audio_path else None])
        raise HTTPException(
            status_code=500,
            detail=f"Error converting video: {str(e)}"
        )


@app.post("/clip")
async def clip_video(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    clips: str = Form(...)
):
    """
    Clip a video at multiple start/end points and return all clips as a ZIP file.
    
    Args:
        file: Video file to clip
        clips: JSON string with array of clip definitions.
               Format: [{"start": 10, "end": 20}, {"start": 30, "end": 40}]
               Times are in seconds.
    
    Returns:
        ZIP file containing all video clips
    """
    # Validate file type
    if not file.content_type or not file.content_type.startswith("video/"):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Please upload a video file."
        )
    
    # Parse clips JSON
    try:
        clips_data = json.loads(clips)
        if not isinstance(clips_data, list):
            raise ValueError("Clips must be a list")
        
        # Validate clip format
        for i, clip in enumerate(clips_data):
            if not isinstance(clip, dict):
                raise ValueError(f"Clip {i} must be a dictionary")
            if "start" not in clip or "end" not in clip:
                raise ValueError(f"Clip {i} must have 'start' and 'end' keys")
            if not isinstance(clip["start"], (int, float)) or not isinstance(clip["end"], (int, float)):
                raise ValueError(f"Clip {i} start and end must be numbers")
            if clip["start"] < 0 or clip["end"] < 0:
                raise ValueError(f"Clip {i} start and end must be non-negative")
            if clip["end"] <= clip["start"]:
                raise ValueError(f"Clip {i} end must be greater than start")
        
        if len(clips_data) == 0:
            raise ValueError("At least one clip must be specified")
            
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid JSON format for clips: {str(e)}"
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
    
    # Create temporary files
    video_ext = Path(file.filename).suffix if file.filename else ".mp4"
    temp_video_path = None
    temp_zip_path = None
    clip_paths = []
    
    try:
        # Save uploaded video to temporary file
        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=video_ext,
            dir=TEMP_DIR
        ) as temp_video:
            content = await file.read()
            temp_video.write(content)
            temp_video_path = temp_video.name
        
        # Load video to get metadata
        video = VideoFileClip(temp_video_path)
        video_duration = video.duration
        video.close()
        logger.info("🎞️ Video loaded: duration %.2f seconds", video_duration)
        
        # Validate clip times don't exceed video duration
        for i, clip in enumerate(clips_data):
            if clip["end"] > video_duration:
                video.close()
                raise HTTPException(
                    status_code=400,
                    detail=f"Clip {i} end time ({clip['end']}s) exceeds video duration ({video_duration:.2f}s)"
                )
        
        # Generate output filenames
        base_filename = Path(file.filename).stem if file.filename else "video"
        total_clips = len(clips_data)
        zip_filename = f"{base_filename}_clips.zip"
        temp_zip_path = TEMP_DIR / zip_filename
        
        # Create clips and add to zip
        with zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for i, clip in enumerate(clips_data):
                start_time = clip["start"]
                end_time = clip["end"]
                
                logger.info(
                    "✂️ Creating clip %s: start=%.2fs end=%.2fs",
                    i + 1,
                    start_time,
                    end_time
                )
                
                # Generate clip filename
                clip_suffix = "" if total_clips == 1 else f"_{i+1}"
                clip_filename = f"{base_filename}_clip{clip_suffix}.mp4"
                clip_path = TEMP_DIR / clip_filename
                
                # Extract clip using ffmpeg for reliability
                try:
                    ffmpeg_extract_subclip(
                        temp_video_path,
                        start_time,
                        end_time,
                        targetname=str(clip_path)
                    )
                except Exception as clip_error:
                    logger.exception(
                        "❌ Failed to create clip %s (start=%.2fs, end=%.2fs)",
                        i + 1,
                        start_time,
                        end_time
                    )
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to create clip {i + 1}: {clip_error}"
                    ) from clip_error
                
                if not clip_path.exists():
                    logger.error(
                        "❌ Clip file not created for clip %s (start=%.2fs, end=%.2fs)",
                        i + 1,
                        start_time,
                        end_time
                    )
                    raise HTTPException(
                        status_code=500,
                        detail=f"Clip {i + 1} was not created successfully"
                    )
                
                # Add to zip
                zipf.write(clip_path, clip_filename)
                clip_paths.append(clip_path)
                logger.info(
                    "✅ Clip %s created and added to ZIP (%s)",
                    i + 1,
                    clip_filename
                )
        
        # Check if zip file was created
        if not temp_zip_path.exists():
            cleanup_files([temp_video_path] + clip_paths)
            raise HTTPException(
                status_code=500,
                detail="Failed to create clips zip file"
            )
        
        # Schedule cleanup after response is sent
        files_to_cleanup = [temp_video_path, str(temp_zip_path)] + [str(p) for p in clip_paths]
        background_tasks.add_task(cleanup_files, files_to_cleanup)
        
        # Return the zip file
        return FileResponse(
            path=str(temp_zip_path),
            filename=zip_filename,
            media_type="application/zip"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        # Cleanup on error
        cleanup_files([temp_video_path, str(temp_zip_path) if temp_zip_path else None] + [str(p) for p in clip_paths])
        raise HTTPException(
            status_code=500,
            detail=f"Error clipping video: {str(e)}"
        )


def cleanup_files(file_paths):
    """Remove temporary files"""
    for file_path in file_paths:
        if file_path and os.path.exists(file_path):
            try:
                if os.path.isdir(file_path):
                    shutil.rmtree(file_path)
                else:
                    os.remove(file_path)
            except Exception:
                pass


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

