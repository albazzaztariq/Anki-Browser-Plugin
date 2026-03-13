"""
AJS Terminal — config.py
Configuration constants for the Anki Japanese Sensei terminal pipeline.

All paths are resolved relative to ~/.ajs/ so they work on both Windows and macOS.
Edit this file to change model, voice, or server settings.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# IPC
# ---------------------------------------------------------------------------
# The JSON file written by the terminal pipeline and consumed by the Anki add-on.
PENDING_CARD_PATH: Path = Path.home() / ".ajs" / "pending_card.json"

# ---------------------------------------------------------------------------
# Ollama / LLM
# ---------------------------------------------------------------------------
OLLAMA_URL: str = "http://localhost:11434"
OLLAMA_MODEL: str = "qwen2.5:3b"

# Request timeout in seconds for Ollama HTTP calls.
OLLAMA_TIMEOUT: int = 60

# How many times to retry a malformed LLM response before giving up (FR-10 / E-6).
LLM_MAX_RETRIES: int = 3

# ---------------------------------------------------------------------------
# Text-to-Speech
# ---------------------------------------------------------------------------
TTS_VOICE: str = "ja-JP-NanamiNeural"

# TTS network timeout in seconds (E-5).
TTS_TIMEOUT: int = 10

# ---------------------------------------------------------------------------
# Audio storage
# ---------------------------------------------------------------------------
AUDIO_DIR: Path = Path.home() / ".ajs" / "Clipped Audio"

# ---------------------------------------------------------------------------
# Transcript download temp directory
# ---------------------------------------------------------------------------
TRANSCRIPT_TMP_DIR: Path = Path.home() / ".ajs" / "tmp"

# ---------------------------------------------------------------------------
# Whisper ASR fallback (used when no subtitle track is available)
# ---------------------------------------------------------------------------
# Model size: "tiny", "base", "small", "medium", "large-v3"
# "small" gives good Japanese accuracy and runs in ~30s on CPU.
WHISPER_MODEL_SIZE: str = "small"

# "cpu" or "cuda" (cuda requires a compatible GPU + CUDA toolkit)
WHISPER_DEVICE: str = "cpu"

# CTranslate2 compute type: "int8" (fast, low RAM) or "float16" (GPU only)
WHISPER_COMPUTE_TYPE: str = "int8"

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_DIR: Path = Path.home() / ".ajs"
LOG_FILE: Path = LOG_DIR / "ajs.log"
LOG_MAX_BYTES: int = 5 * 1024 * 1024   # 5 MB per log file
LOG_BACKUP_COUNT: int = 3

# ---------------------------------------------------------------------------
# Crash reporting
# ---------------------------------------------------------------------------
GITHUB_REPO: str = "albazzaztariq/Anki-Browser-Plugin"

# Google Form URL for user bug reports (set after creating the form — see feedback/SETUP.md).
FEEDBACK_FORM_URL: str = ""


def _load_token() -> str:
    """Load the GitHub issue token from ~/.ajs/.token if it exists."""
    try:
        p = Path.home() / ".ajs" / ".token"
        return p.read_text(encoding="utf-8").strip() if p.exists() else ""
    except Exception:
        return ""


# Fine-grained PAT with Issues: Read+Write on the above repo only.
# Written by installer (setup_token.py) to ~/.ajs/.token
# Falls back to gh CLI (dev machines) or local-file-only mode when empty.
GITHUB_ISSUE_TOKEN: str = _load_token()
