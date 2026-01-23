#!/bin/bash

set -o pipefail

# -----------------------------------
# CONFIG (ABSOLUTE PATHS)
# -----------------------------------
BASE_DIR="/Users/arpitjain/PycharmProjects/gemini-transcriber"
VENV_DIR="$BASE_DIR/venv"
LOG_DIR="$BASE_DIR/logs"
ENV_FILE="$BASE_DIR/export.env"

# Fix PATH for cron (Homebrew + system)
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

mkdir -p "$LOG_DIR"

LOG_FILE="$LOG_DIR/run_main_$(date +'%Y-%m-%d_%H-%M-%S').log"

# -----------------------------------
# START
# -----------------------------------
echo "==== Job started at $(date) ====" >> "$LOG_FILE"

# Load environment variables (🔥 THIS FIXES GEMINI_API_KEY)
if [ -f "$ENV_FILE" ]; then
  set -a
  source "$ENV_FILE"
  set +a
else
  echo "❌ .env file not found at $ENV_FILE" >> "$LOG_FILE"
  exit 1
fi

# Sanity checks
which ffmpeg >> "$LOG_FILE" 2>&1
which ffprobe >> "$LOG_FILE" 2>&1

source "$VENV_DIR/bin/activate"
which python >> "$LOG_FILE"

python -c "import yt_dlp; print('yt_dlp OK')" >> "$LOG_FILE" 2>&1

# -----------------------------------
# RUN JOB
# -----------------------------------
python \
"$BASE_DIR/transcribe.py" \
"$BASE_DIR/urls.txt" \
>> "$LOG_FILE" 2>&1

EXIT_CODE=$?
echo "Exit code: $EXIT_CODE" >> "$LOG_FILE"
echo "==== Job finished at $(date) ====" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"
