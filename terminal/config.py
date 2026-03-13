"""
AJS Terminal — config.py
Configuration constants for the Anki Japanese Sensei terminal pipeline.

All paths are resolved relative to ~/.ajs/ so they work on both Windows and macOS.
Edit this file to change model, voice, or server settings.
"""

import json
import sys
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
_FALLBACK_AUDIO_DIR: Path = Path.home() / ".ajs" / "Clipped Audio"


def _resolve_default_audio_dir() -> Path:
    """Prefer Music/Anki AJS on Windows; otherwise fallback to ~/.ajs/Clipped Audio."""
    if sys.platform == "win32":
        music_dir = Path.home() / "Music"
        preferred = music_dir / "Anki AJS"
        if music_dir.exists():
            return preferred
        return _FALLBACK_AUDIO_DIR
    return _FALLBACK_AUDIO_DIR


AUDIO_DIR: Path = _resolve_default_audio_dir()

USER_CONFIG_PATH: Path = Path.home() / ".ajs" / "user_config.json"

# ---------------------------------------------------------------------------
# Audio clip settings (video-derived audio, not TTS)
# ---------------------------------------------------------------------------
# Clip window is centered on (timestamp - AUDIO_CLIP_OFFSET_S).
# Default window: 5s before to 5s after, centered on 1s before hotkey press.
AUDIO_CLIP_PRE_S: float = 5.0
AUDIO_CLIP_POST_S: float = 5.0
AUDIO_CLIP_OFFSET_S: float = 1.0
AUDIO_CLIP_ENABLED: bool = True
AUDIO_CLIP_FALLBACK_TO_TTS: bool = False


def _coerce_bool(value, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        s = value.strip().lower()
        if s in ("1", "true", "yes", "y", "on"):
            return True
        if s in ("0", "false", "no", "n", "off"):
            return False
    return default


def _coerce_float(value, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _apply_user_config() -> None:
    """Load overrides from ~/.ajs/user_config.json if present."""
    global AUDIO_DIR
    global AUDIO_CLIP_PRE_S, AUDIO_CLIP_POST_S, AUDIO_CLIP_OFFSET_S
    global AUDIO_CLIP_ENABLED, AUDIO_CLIP_FALLBACK_TO_TTS

    try:
        if not USER_CONFIG_PATH.exists():
            return
        data = json.loads(USER_CONFIG_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return
    except Exception:
        return

    audio_dir_val = data.get("audio_dir")
    if isinstance(audio_dir_val, str) and audio_dir_val.strip():
        AUDIO_DIR = Path(audio_dir_val).expanduser()

    AUDIO_CLIP_PRE_S = _coerce_float(data.get("audio_clip_pre_s"), AUDIO_CLIP_PRE_S)
    AUDIO_CLIP_POST_S = _coerce_float(data.get("audio_clip_post_s"), AUDIO_CLIP_POST_S)
    AUDIO_CLIP_OFFSET_S = _coerce_float(data.get("audio_clip_offset_s"), AUDIO_CLIP_OFFSET_S)
    AUDIO_CLIP_ENABLED = _coerce_bool(data.get("audio_clip_enabled"), AUDIO_CLIP_ENABLED)
    AUDIO_CLIP_FALLBACK_TO_TTS = _coerce_bool(
        data.get("audio_clip_fallback_to_tts"), AUDIO_CLIP_FALLBACK_TO_TTS
    )


_apply_user_config()

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
