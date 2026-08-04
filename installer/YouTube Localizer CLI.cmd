@echo off
setlocal
set "YOUTUBE_LOCALIZER_HOME=%~dp0"
set "YOUTUBE_LOCALIZER_MODELS=%~dp0models"
set "FFMPEG_PATH=%~dp0runtime\ffmpeg\bin\ffmpeg.exe"
set "FFPROBE_PATH=%~dp0runtime\ffmpeg\bin\ffprobe.exe"
set "OLLAMA_PATH=%~dp0runtime\ollama\ollama.exe"
set "PATH=%~dp0runtime\ffmpeg\bin;%~dp0runtime\ollama;%PATH%"
"%~dp0runtime\python\python.exe" "%~dp0app\main.py" %*
