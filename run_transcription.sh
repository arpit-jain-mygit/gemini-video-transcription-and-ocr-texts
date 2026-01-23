#!/bin/bash

set -o pipefail

# -----------------------------------
# CONFIG
# -----------------------------------
BASE_DIR="/Users/arpitjain/PycharmProjects/gemini-video-transcription-and-ocr-texts"
VENV_DIR="$BASE_DIR/.venv"
LOG_DIR="$BASE_DIR/logs"
ENV_FILE="$BASE_DIR/.env"

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

mkdir -p "$LOG_DIR"

LOG_FILE="$LOG_DIR/run_transcription_$(date +'%Y-%m-%d_%H-%M-%S').log"

# -----------------------------------
# LOG TO TERMINAL + FILE
# -----------------------------------
exec > >(tee -a "$LOG_FILE") 2>&1

echo "==== Job started at $(date) ===="
echo "BASE_DIR=$BASE_DIR"
echo "LOG_FILE=$LOG_FILE"

# -----------------------------------
# ENV
# -----------------------------------
if [ -f "$ENV_FILE" ]; then
  set -a
  source "$ENV_FILE"
  set +a
else
  echo "❌ .env file not found: $ENV_FILE"
  exit 1
fi

# -----------------------------------
# SANITY
# -----------------------------------
which ffmpeg
which ffprobe

source "$VENV_DIR/bin/activate"
which python

python -c "import yt_dlp; print('yt_dlp OK')"

# -----------------------------------
# RUN
# -----------------------------------
echo "🚀 Starting transcription job"

python \
  "$BASE_DIR/transcribe.py" \
  "$BASE_DIR/youtube_video_urls.txt"

EXIT_CODE=$?
echo "Exit code: $EXIT_CODE"
echo "==== Job finished at $(date) ===="

exit $EXIT_CODE
