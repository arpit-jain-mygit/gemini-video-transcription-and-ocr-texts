#!/bin/bash

# ==========================================
# Jain PDF Verbatim OCR Runner
# (expects GEMINI_API_KEY in environment)
# ==========================================

set -e

echo "🕒 OCR run started at: $(date)"

# ------------------------------------------
# Project root (script location)
# ------------------------------------------
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_ROOT"

# ------------------------------------------
# Environment variable check
# ------------------------------------------
if [ -z "$GEMINI_API_KEY" ]; then
  echo "❌ GEMINI_API_KEY is not set."
  echo "👉 Run: export GEMINI_API_KEY=\"your_key_here\""
  exit 1
fi

echo "🔐 GEMINI_API_KEY detected"

# ------------------------------------------
# Python sanity check
# ------------------------------------------
echo "🐍 Using Python:"
python3 --version

# ------------------------------------------
# Required directories
# ------------------------------------------
mkdir -p input_docs
mkdir -p output_texts
mkdir -p logs

# ------------------------------------------
# Log file
# ------------------------------------------
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
LOG_FILE="logs/ocr_run_${TIMESTAMP}.log"

echo "📄 Logging to: $LOG_FILE"
echo "----------------------------------------" | tee -a "$LOG_FILE"

# ------------------------------------------
# Dependency check
# ------------------------------------------
echo "🔍 Checking required commands" | tee -a "$LOG_FILE"

for cmd in python3 brew; do
  if ! command -v $cmd &> /dev/null; then
    echo "❌ Required command not found: $cmd" | tee -a "$LOG_FILE"
    exit 1
  fi
done

# Poppler check (pdf2image dependency)
if ! command -v pdftoppm &> /dev/null; then
  echo "❌ Poppler not found. Install with: brew install poppler" | tee -a "$LOG_FILE"
  exit 1
fi

# ------------------------------------------
# Run OCR pipeline
# ------------------------------------------
echo "🚀 Starting OCR pipeline..." | tee -a "$LOG_FILE"
python3 ocr_pipeline.py 2>&1 | tee -a "$LOG_FILE"

echo "----------------------------------------" | tee -a "$LOG_FILE"
echo "✅ OCR run completed at: $(date)" | tee -a "$LOG_FILE"
