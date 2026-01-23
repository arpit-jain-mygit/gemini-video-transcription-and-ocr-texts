# -*- coding: utf-8 -*-
import shutil

import os
import sys
import re
import unicodedata
import time
from datetime import datetime
from typing import List

import yt_dlp
from google import genai
from dotenv import load_dotenv

# =========================================================
# UTF-8 SAFE OUTPUT
# =========================================================
sys.stdout.reconfigure(encoding="utf-8")

PIPELINE_START_TS = datetime.now()
PIPELINE_START = time.perf_counter()

# =========================================================
# LOG FILE SETUP
# =========================================================
LOG_DIR = "transcription_logs"
os.makedirs(LOG_DIR, exist_ok=True)

LOG_FILE_PATH = os.path.join(
    LOG_DIR,
    f"run_{PIPELINE_START_TS.strftime('%Y-%m-%d_%H-%M-%S')}.log"
)

LOG_FILE = open(LOG_FILE_PATH, "w", encoding="utf-8")

print(f"🧾 Logging to file: {LOG_FILE_PATH}")
LOG_FILE.write(f"🧾 Logging to file: {LOG_FILE_PATH}\n")
LOG_FILE.write("=" * 80 + "\n")
LOG_FILE.flush()

# =========================================================
# GLOBAL LOG INDENTATION
# =========================================================
LOG_LEVEL = 0
INDENT = "  "

def log(msg: str):
    line = f"{INDENT * LOG_LEVEL}{msg}"
    print(line)
    LOG_FILE.write(line + "\n")
    LOG_FILE.flush()

def log_parent(msg: str):
    global LOG_LEVEL
    log(msg)
    LOG_LEVEL += 1

def log_child(msg: str):
    log(msg)

def log_done():
    global LOG_LEVEL
    LOG_LEVEL = max(LOG_LEVEL - 1, 0)

def log_step(name: str, start_ts, start_perf):
    end_ts = datetime.now()
    duration = time.perf_counter() - start_perf
    log_child(f"🕒 {name} started: {start_ts.strftime('%Y-%m-%d %H:%M:%S')}")
    log_child(
        f"🕒 {name} ended:   {end_ts.strftime('%Y-%m-%d %H:%M:%S')} ({duration:.2f}s)\n"
    )

# =========================================================
# LOAD ENV
# =========================================================
load_dotenv()

# =========================================================
# CONFIG
# =========================================================
MODEL_NAME = "gemini-2.5-flash"

CACHE_DIR = ".cache"
AUDIO_CACHE_DIR = os.path.join(CACHE_DIR, "audio")
META_CACHE_DIR = os.path.join(CACHE_DIR, "meta")

TRANSCRIPTS_DIR = "transcripts"

os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)
os.makedirs(META_CACHE_DIR, exist_ok=True)
os.makedirs(TRANSCRIPTS_DIR, exist_ok=True)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
PROMPT_FILE = os.environ.get("PROMPT_FILE")
PROMPT_NAME = os.environ.get("PROMPT_NAME")

if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY not set")
if not PROMPT_FILE or not PROMPT_NAME:
    raise RuntimeError("PROMPT_FILE or PROMPT_NAME not set")
if not os.path.exists(PROMPT_FILE):
    raise RuntimeError(f"Prompt file not found: {PROMPT_FILE}")

# =========================================================
# yt-dlp QUIET LOGGER
# =========================================================
class YTDLPQuietLogger:
    def debug(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): log(f"yt-dlp error: {msg}")

# =========================================================
# PROMPT LOADER
# =========================================================
def load_named_prompt(prompt_file: str, prompt_name: str) -> str:
    log_parent("📜 Loading prompt")
    start_ts = datetime.now()
    start_perf = time.perf_counter()

    with open(prompt_file, "r", encoding="utf-8") as f:
        content = f.read()

    start = f"### PROMPT: {prompt_name}"
    end = "=== END PROMPT ==="

    if start not in content:
        raise RuntimeError(f"Prompt '{prompt_name}' not found")

    prompt = content.split(start, 1)[1].split(end, 1)[0].strip()
    if not prompt:
        raise RuntimeError(f"Prompt '{prompt_name}' is empty")

    log_step("Prompt load", start_ts, start_perf)
    log_done()
    return prompt

AUDIO_PROMPT = load_named_prompt(PROMPT_FILE, PROMPT_NAME)
log(f"🧾 Using prompt: {PROMPT_NAME}\n")

# =========================================================
# GEMINI CLIENT
# =========================================================
client = genai.Client(api_key=GEMINI_API_KEY)

# =========================================================
# UTILITIES
# =========================================================
def sanitize_filename(name: str, max_len: int = 180) -> str:
    name = unicodedata.normalize("NFKC", name)
    name = re.sub(r"[\\/:*?\"<>|]", "_", name)
    name = re.sub(r"\s+", "_", name).strip("_")
    return name[:max_len]

def get_video_id_from_mp3(mp3_path: str) -> str:
    return os.path.splitext(os.path.basename(mp3_path))[0]

def get_output_path(video_id: str, title: str) -> str:
    safe_title = sanitize_filename(title)
    filename = f"{video_id}__{safe_title}_{PROMPT_NAME}.txt"
    return os.path.join(TRANSCRIPTS_DIR, filename)

def parse_urls(args) -> List[str]:
    if len(args) == 1 and args[0].endswith(".txt"):
        with open(args[0], "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    return args

# =========================================================
# PLAYLIST EXPANSION (🔥 NEW)
# =========================================================
def expand_urls(urls: List[str]) -> List[str]:
    """
    Accepts a mix of video URLs and playlist URLs.
    Expands playlists into individual video URLs.
    Handles watch?v=...&list=... correctly.
    """
    expanded = []

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
        "logger": YTDLPQuietLogger(),
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        for url in urls:
            try:
                # 🔥 NORMALIZE playlist URLs
                if "list=" in url:
                    playlist_id = re.search(r"list=([^&]+)", url)
                    if playlist_id:
                        url = f"https://www.youtube.com/playlist?list={playlist_id.group(1)}"

                info = ydl.extract_info(url, download=False)

                if info.get("_type") == "playlist":
                    log_parent(f"📂 Expanding playlist: {info.get('title', 'Unknown')}")
                    entries = info.get("entries", [])
                    for entry in entries:
                        if entry and "id" in entry:
                            expanded.append(f"https://www.youtube.com/watch?v={entry['id']}")
                    log_child(f"📋 Found {len(entries)} videos\n")
                    log_done()
                else:
                    expanded.append(url)

            except Exception as e:
                log_child(f"❌ Failed to expand URL {url}: {e}")

    # Deduplicate while preserving order
    seen = set()
    result = []
    for u in expanded:
        if u not in seen:
            seen.add(u)
            result.append(u)

    return result


# =========================================================
# SPEAKER EXTRACTION
# =========================================================
def extract_speaker_from_title(title: str) -> str:
    title = unicodedata.normalize("NFKC", title)

    patterns = [
        r"(पूज्य\s+)?(मुनि|आचार्य|उपाध्याय)\s+श्री\s+([^\|,\-]+?)\s+महाराज",
        r"(पूज्य\s+)?श्री\s+([^\|,\-]+?)\s+महाराज\s+जी",
        r"(पूज्य\s+)?मुनि\s+श्री\s+([^\|,\-]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, title)
        if match:
            return match.group(match.lastindex).strip()

    return "अज्ञात"

# =========================================================
# YOUTUBE METADATA
# =========================================================
def get_video_info(url: str) -> dict:
    log_parent("🎥 Resolving metadata")
    start_ts = datetime.now()
    start_perf = time.perf_counter()

    with yt_dlp.YoutubeDL({
        "quiet": True,
        "no_warnings": True,
        "logger": YTDLPQuietLogger(),
    }) as ydl:
        info = ydl.extract_info(url, download=False)

    log_step("Metadata resolve", start_ts, start_perf)
    log_done()
    return info

# =========================================================
# YOUTUBE AUDIO
# =========================================================
def download_youtube_audio(url):
    info = get_video_info(url)
    video_id = info["id"]
    title = info.get("title", video_id)

    mp3_path = os.path.join(AUDIO_CACHE_DIR, f"{video_id}.mp3")

    if os.path.exists(mp3_path):
        log_child("♻️ Using cached audio\n")
        return mp3_path, title

    log_parent("⬇️ Downloading audio")
    start_ts = datetime.now()
    start_perf = time.perf_counter()

    ydl_opts = {
        "format": "bestaudio/best",
        "noplaylist": True,

        # 🔥 THIS IS THE IMPORTANT PART
        "outtmpl": os.path.join(AUDIO_CACHE_DIR, f"{video_id}.%(ext)s"),
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],

        "retries": 5,
        "fragment_retries": 5,
        "socket_timeout": 30,
        "ignoreerrors": False,
        "concurrent_fragment_downloads": 1,

        "quiet": True,
        "no_warnings": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    # ✅ KEEP THIS CHECK RIGHT HERE
    if not os.path.exists(mp3_path):
        raise RuntimeError("MP3 not generated")

    log_step("Audio download", start_ts, start_perf)
    log_done()
    return mp3_path, title

# =========================================================
# GEMINI TRANSCRIPTION
# =========================================================
def transcribe_audio(mp3_path):
    log_parent("🧠 Gemini transcription")

    start_ts = datetime.now()
    start_perf = time.perf_counter()
    with open(mp3_path, "rb") as f:
        uploaded = client.files.upload(file=f, config={"mime_type": "audio/mpeg"})
    log_step("Gemini upload", start_ts, start_perf)

    start_ts = datetime.now()
    start_perf = time.perf_counter()
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=[uploaded, AUDIO_PROMPT],
        config={"temperature": 0.1},
    )
    log_step("Gemini inference", start_ts, start_perf)

    log_done()

    text = (response.text or "").strip()
    if not text:
        raise RuntimeError("Gemini returned empty transcription")
    return text

# =========================================================
# ARCHIVE OLD TRANSCRIPTS
# =========================================================
def archive_old_transcripts():
    if not os.path.isdir(TRANSCRIPTS_DIR):
        return

    txt_files = [
        f for f in os.listdir(TRANSCRIPTS_DIR)
        if f.endswith(".txt")
        and os.path.isfile(os.path.join(TRANSCRIPTS_DIR, f))
    ]

    if not txt_files:
        return

    ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_archive_dir = os.path.join("archived_transcripts", ts)
    os.makedirs(run_archive_dir, exist_ok=True)

    log_parent(f"📦 Archiving {len(txt_files)} existing transcript(s)")
    for f in txt_files:
        shutil.move(
            os.path.join(TRANSCRIPTS_DIR, f),
            os.path.join(run_archive_dir, f)
        )
        log_child(f"→ {f}")
    log_done()
    log_child(f"📂 Archived to: {run_archive_dir}\n")

# =========================================================
# MAIN
# =========================================================
def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python transcribe.py URL1 URL2 ...")
        print("  python transcribe.py youtube_video_urls.txt")
        sys.exit(1)

    archive_old_transcripts()  # ← ADD THIS LINE
    raw_urls = parse_urls(sys.argv[1:])
    urls = expand_urls(raw_urls)

    log(f"📋 Processing {len(urls)} video(s)\n")

    for idx, url in enumerate(urls, start=1):
        log_parent(f"▶️ [{idx}/{len(urls)}] Processing: {url}\n")

        try:
            for attempt in range(1, 4):
                try:
                    mp3_path, title = download_youtube_audio(url)
                    break
                except Exception as e:
                    print(f"⚠️ Attempt {attempt} failed: {e}")
                    time.sleep(5)
            else:
                print("❌ Skipping video after retries")
                log_done()
                continue

            speaker = extract_speaker_from_title(title)
            video_id = get_video_id_from_mp3(mp3_path)
            out = get_output_path(video_id, title)

            if os.path.exists(out):
                log_child("♻️ Gemini already executed for this video + prompt")
                log_child(f"📄 Existing output found: {out}\n")
                log_done()
                continue

            text = transcribe_audio(mp3_path)

            log_parent("💾 Writing output")
            start_ts = datetime.now()
            start_perf = time.perf_counter()

            header = (
                f"वीडियो शीर्षक: {title}\n"
                f"वक्ता (महाराज जी): {speaker}\n"
                f"वीडियो URL: {url}\n"
                f"प्रॉम्प्ट: {PROMPT_NAME}\n"
                f"तिथि: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"\n{'-' * 50}\n\n"
            )

            with open(out, "w", encoding="utf-8") as f:
                f.write(header)
                f.write(text)

            log_step("File write", start_ts, start_perf)
            log_done()
            log_child(f"✅ Saved: {out}\n")

        except Exception as e:
            log_child(f"❌ Failed: {e}\n")

        log_done()

    log(f"⏱️ PIPELINE START: {PIPELINE_START_TS.strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"⏱️ TOTAL TIME: {time.perf_counter() - PIPELINE_START:.2f}s")
    log(f"🧾 Log file saved at: {LOG_FILE_PATH}")

    LOG_FILE.close()

if __name__ == "__main__":
    main()
