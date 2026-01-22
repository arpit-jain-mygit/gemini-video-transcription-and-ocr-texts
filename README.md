python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py urls.txt# transcription-projects

GEMINI_API_KEI need to be set before running this program.


flowchart TD
    A[Input URLs<br/>Video / Playlist / urls.txt] --> B[Playlist Expansion<br/>yt-dlp]
    B --> C[Video Metadata Resolver<br/>Title · ID · Duration]
    C --> D[Audio Download<br/>MP3 via FFmpeg]
    D -->|Cached?| E[Audio Cache<br/>.cache/audio]
    E --> F[Prompt Loader<br/>Named Prompt]
    F --> G[Gemini Transcription Engine<br/>Low Temperature]
    G --> H[Post Processing<br/>Speaker Extraction · Sanitization]
    H --> I[Structured Transcript Output<br/>Metadata + Text]
    I --> J[Transcripts Folder]
    J --> K[Archival System<br/>Timestamped Runs]
    
    subgraph Observability
        L[UTF-8 Logs<br/>Per Run File]
    end

    B --> L
    D --> L
    G --> L
    I --> L
