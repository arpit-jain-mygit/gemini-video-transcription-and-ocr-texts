# -*- coding: utf-8 -*-

import os
import sys
import time
import io
import requests                       # >>> GITHUB ADDITION >>>
from urllib.parse import urlparse     # >>> GITHUB ADDITION >>>
from datetime import datetime
from pdf2image import convert_from_path
from PIL import Image

from google.cloud import aiplatform
from vertexai.preview.generative_models import (
    GenerativeModel,
    Part,
    Image as VertexImage,
)

# =========================================================
# UTF-8 SAFE OUTPUT
# =========================================================
sys.stdout.reconfigure(encoding="utf-8")

# =========================================================
# CONFIG
# =========================================================
PROJECT_ID = "transcribe-serverless"
LOCATION = "us-central1"
MODEL_NAME = "gemini-2.5-flash"

INPUT_DIR = "input_docs"
OUTPUT_DIR = "output_texts"
DPI = 300

# >>> GITHUB ADDITION >>>
GITHUB_OWNER = "arpit-jain-mygit"
GITHUB_REPO = "jain-scanned-docs"
GITHUB_BRANCH = "main"
# <<< GITHUB ADDITION <<<

PROMPT_TEMPLATE = """
Role: You are an expert Indic-language archivist specializing in Hindi manuscripts and mixed-script texts.

Task:
Transcribe every visible word from the attached page image with 100% accuracy.

Important Context:
The document may contain a mix of languages and scripts, including:
- Hindi (Devanagari)
- Sanskrit (Devanagari)
- Prakrit (Devanagari)
- English (Latin script)

All languages must be transcribed exactly as they appear.

Rules (STRICT):
1. Do NOT translate, summarize, explain, normalize, or correct any text.
2. Preserve exact characters from all scripts (Devanagari and Latin), including:
   - Matras, conjuncts, punctuation, numerals, and diacritics
   - Honorifics and abbreviations (e.g., ब्र०)
3. Preserve special symbols exactly as seen (ॐ, 卐, ॥, ।, etc.).
4. Maintain original casing for English text (upper/lower case).
5. Maintain original line breaks, spacing, and paragraph structure.
6. If a word, glyph, or character is unclear or partially visible, reproduce it exactly as seen without guessing or substitution.
7. Begin the output with: "=== Page {page} ==="
8. Output ONLY the verbatim transcription text. No commentary or metadata.

Failure to follow these rules is unacceptable.
"""

# =========================================================
# INIT VERTEX AI
# =========================================================
aiplatform.init(project=PROJECT_ID, location=LOCATION)
model = GenerativeModel(MODEL_NAME)

# =========================================================
# IMAGE → PNG BYTES (REQUIRED)
# =========================================================
def pil_to_png_bytes(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()

# =========================================================
# LOGGING
# =========================================================
def ts():
    return datetime.now().strftime("%H:%M:%S")

def log_parent(msg):
    print(f"\n📁 [{ts()}] {msg}", flush=True)

def log_child(msg):
    print(f"   ├─ [{ts()}] {msg}", flush=True)

def log_leaf(msg):
    print(f"   │   └─ [{ts()}] {msg}", flush=True)

# =========================================================
# >>> GITHUB ADDITION >>>
# =========================================================
def list_github_pdfs(path=""):
    api_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{path}"
    r = requests.get(api_url, timeout=30)
    r.raise_for_status()

    pdfs = []
    for item in r.json():
        if item["type"] == "file" and item["name"].lower().endswith(".pdf"):
            pdfs.append(item["download_url"])
        elif item["type"] == "dir":
            pdfs.extend(list_github_pdfs(item["path"]))
    return pdfs


def download_pdfs_from_github():
    log_child("Fetching PDFs from GitHub repository")

    pdf_urls = list_github_pdfs()
    if not pdf_urls:
        raise RuntimeError("No PDFs found in GitHub repo")

    os.makedirs(INPUT_DIR, exist_ok=True)

    for url in pdf_urls:
        filename = os.path.basename(urlparse(url).path)
        local_path = os.path.join(INPUT_DIR, filename)

        if os.path.exists(local_path):
            log_leaf(f"♻️ {filename} already exists → skipping")
            continue

        log_leaf(f"⬇️ Downloading {filename}")
        r = requests.get(url, timeout=60)
        r.raise_for_status()

        with open(local_path, "wb") as f:
            f.write(r.content)
# <<< GITHUB ADDITION <<<

# =========================================================
# GEMINI SAFE CALL (VERTEX – STABLE)
# =========================================================
def gemini_generate_with_retry(prompt: str, image: Image.Image, page_num: int):
    attempt = 1
    while True:
        try:
            log_leaf(f"Page {page_num}: Gemini call (attempt {attempt})")

            png_bytes = pil_to_png_bytes(image)
            vertex_image = VertexImage.from_bytes(png_bytes)

            return model.generate_content(
                [
                    Part.from_text(prompt),
                    Part.from_image(vertex_image),
                ],
                generation_config={
                    "temperature": 0,
                    "top_p": 1,
                    "max_output_tokens": 8192,
                },
            )

        except Exception as e:
            wait = min(60, 5 * attempt)
            log_leaf(f"⚠️ Gemini error: {e}. Retrying in {wait}s…")
            time.sleep(wait)
            attempt += 1

# =========================================================
# PIPELINE
# =========================================================
def process_pdf(pdf_path):
    pdf_start = time.perf_counter()

    pdf_name = os.path.basename(pdf_path)
    base_name = os.path.splitext(pdf_name)[0]

    pdf_cache_dir = os.path.join(OUTPUT_DIR, base_name)
    os.makedirs(pdf_cache_dir, exist_ok=True)

    final_output_path = os.path.join(OUTPUT_DIR, f"{base_name}.txt")

    log_parent(f"Processing PDF: {pdf_name}")
    log_child(f"Using cache directory: {pdf_cache_dir}")

    log_child("Starting PDF → image conversion...")
    start = time.perf_counter()
    pages = convert_from_path(pdf_path, dpi=DPI)
    log_child(f"Converted {len(pages)} pages in {time.perf_counter() - start:.2f}s")

    for page_num, page in enumerate(pages, start=1):
        page_file = os.path.join(pdf_cache_dir, f"page_{page_num:03d}.txt")

        if os.path.exists(page_file):
            log_leaf(f"♻️ Page {page_num} cached → skipping Gemini call")
            continue

        log_leaf(f"Page {page_num}: OCR started")
        prompt = PROMPT_TEMPLATE.format(page=page_num)

        response = gemini_generate_with_retry(prompt, page, page_num)
        text = (response.text or "").strip()

        if not text:
            raise RuntimeError(f"Empty OCR output on page {page_num}")

        with open(page_file, "w", encoding="utf-8") as f:
            f.write(text)

        log_leaf(f"Page {page_num}: Cached successfully")

    log_child("Rebuilding final output from cached pages (single header per page)")

    with open(final_output_path, "w", encoding="utf-8") as out:
        for page_num in range(1, len(pages) + 1):
            page_file = os.path.join(pdf_cache_dir, f"page_{page_num:03d}.txt")

            out.write(f"=== Page {page_num} ===\n")

            with open(page_file, "r", encoding="utf-8") as f:
                page_text = f.read().lstrip()
                header = f"=== Page {page_num} ==="

                if page_text.startswith(header):
                    page_text = page_text[len(header):].lstrip()

                out.write(page_text.rstrip())

            out.write("\n\n")

    log_child(
        f"PDF completed → {final_output_path} "
        f"in {time.perf_counter() - pdf_start:.2f}s"
    )

# =========================================================
# MAIN
# =========================================================
def main():
    pipeline_start = time.perf_counter()
    log_parent("Jain PDF Verbatim OCR Pipeline Started")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # >>> GITHUB ADDITION >>>
    download_pdfs_from_github()
    # <<< GITHUB ADDITION <<<

    pdf_files = sorted(
        f for f in os.listdir(INPUT_DIR)
        if f.lower().endswith(".pdf")
    )

    if not pdf_files:
        print("⚠️ No PDF files found.")
        return

    log_child(f"Found {len(pdf_files)} PDF(s)")

    for idx, pdf in enumerate(pdf_files, start=1):
        log_child(f"[{idx}/{len(pdf_files)}] Processing next PDF")
        process_pdf(os.path.join(INPUT_DIR, pdf))

    log_parent(
        f"✅ All PDFs processed successfully "
        f"in {time.perf_counter() - pipeline_start:.2f}s"
    )

if __name__ == "__main__":
    main()
