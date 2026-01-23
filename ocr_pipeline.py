import os
import sys
import time
import io
from datetime import datetime
from pdf2image import convert_from_path
from PIL import Image
from google import genai

# =========================================================
# UTF-8 SAFE OUTPUT
# =========================================================
sys.stdout.reconfigure(encoding="utf-8")

# =========================================================
# CONFIG
# =========================================================
INPUT_DIR = "input_docs"
OUTPUT_DIR = "output_texts"
MODEL_NAME = "gemini-2.5-flash"
DPI = 300

PROMPT_TEMPLATE = """
Role: You are an expert Hindi archivist.

Task:
Transcribe every visible word from the attached page image with 100% accuracy.

Rules (STRICT):
1. Do NOT translate, summarize, explain, or correct text.
2. Preserve exact Devanagari characters, matras, punctuation, and honorifics (e.g., ब्र०).
3. Preserve symbols exactly as seen (ॐ, 卐, ॥, ।).
4. If a word or character is unclear, reproduce it as-is without guessing.
5. Maintain original line breaks and paragraph structure.
6. Begin output with: "=== Page {page} ==="
7. Output ONLY the transcription text.

Failure to follow these rules is unacceptable.
"""

# =========================================================
# GEMINI CLIENT
# =========================================================
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY not set")

client = genai.Client(api_key=GEMINI_API_KEY)

# =========================================================
# IMAGE ENCODER
# =========================================================
def pil_image_to_png_bytes(image: Image.Image) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()

# =========================================================
# LOGGING HELPERS
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
# PIPELINE
# =========================================================
def process_pdf(pdf_path):
    pdf_start = time.perf_counter()

    pdf_name = os.path.basename(pdf_path)
    base_name = os.path.splitext(pdf_name)[0]
    output_path = os.path.join(OUTPUT_DIR, f"{base_name}.txt")

    log_parent(f"Processing PDF: {pdf_name}")

    # ---- PDF → IMAGE CONVERSION ----
    log_child("Starting PDF → image conversion (this may take time)...")
    start = time.perf_counter()
    pages = convert_from_path(pdf_path, dpi=DPI)
    log_child(
        f"PDF → image conversion completed: {len(pages)} pages "
        f"in {time.perf_counter() - start:.2f}s"
    )

    with open(output_path, "w", encoding="utf-8") as out:
        for page_num, page in enumerate(pages, start=1):
            page_start = time.perf_counter()
            log_leaf(f"Page {page_num}: OCR started")

            # ---- PROMPT ----
            try:
                prompt = PROMPT_TEMPLATE.format(page=page_num)
            except KeyError as e:
                raise RuntimeError(f"Prompt placeholder missing: {e}")

            # ---- IMAGE ENCODE ----
            log_leaf(f"Page {page_num}: Encoding image")
            img_bytes = pil_image_to_png_bytes(page)
            log_leaf(f"Page {page_num}: Image encoded ({len(img_bytes) // 1024} KB)")

            # ---- GEMINI CALL ----
            log_leaf(f"Page {page_num}: Gemini request started")
            gemini_start = time.perf_counter()

            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=[
                    {
                        "role": "user",
                        "parts": [
                            {"text": prompt},
                            {
                                "inline_data": {
                                    "mime_type": "image/png",
                                    "data": img_bytes
                                }
                            }
                        ],
                    }
                ],
                config={
                    "temperature": 0,
                    "top_p": 1,
                    "max_output_tokens": 8192,
                },
            )

            log_leaf(
                f"Page {page_num}: Gemini response received "
                f"in {time.perf_counter() - gemini_start:.2f}s"
            )

            text = (response.text or "").strip()
            if not text:
                raise RuntimeError(f"Empty OCR output on page {page_num}")

            out.write(text)
            out.write("\n\n")

            log_leaf(
                f"Page {page_num}: Written to file "
                f"({time.perf_counter() - page_start:.2f}s total)"
            )

    log_child(
        f"PDF completed → {output_path} "
        f"in {time.perf_counter() - pdf_start:.2f}s"
    )

# =========================================================
# MAIN
# =========================================================
def main():
    pipeline_start = time.perf_counter()
    log_parent("Jain PDF Verbatim OCR Pipeline Started")

    if not os.path.exists(INPUT_DIR):
        print(f"❌ Input directory not found: {INPUT_DIR}")
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    pdf_files = sorted(
        f for f in os.listdir(INPUT_DIR)
        if f.lower().endswith(".pdf")
    )

    if not pdf_files:
        print("⚠️ No PDF files found.")
        return

    log_child(f"Found {len(pdf_files)} PDF(s)")

    for idx, pdf in enumerate(pdf_files, start=1):
        log_child(f"[{idx}/{len(pdf_files)}] Starting next PDF")
        process_pdf(os.path.join(INPUT_DIR, pdf))

    log_parent(
        f"✅ All PDFs processed successfully "
        f"in {time.perf_counter() - pipeline_start:.2f}s"
    )

if __name__ == "__main__":
    main()
