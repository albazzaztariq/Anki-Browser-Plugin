"""
AJS Terminal — tts.py
Text-to-Speech synthesis using Microsoft Edge TTS via the edge-tts package.

Converts a Japanese text string into an MP3 audio file saved at a specified path.
Audio files are stored under ~/.ajs/Clipped Audio/ with filename <word>.mp3 only.

Inputs:
  text        (str)  — Japanese text to synthesise
  output_path (Path) — where to write the .mp3 file

Outputs:
  Path — the path where the MP3 was saved

Error handling:
  - E-5: If edge-tts fails or times out (TTS_TIMEOUT seconds), raises RuntimeError.
    The caller (ajs.py) catches this, logs it, and continues without audio.

Packages used:
  - edge_tts (third-party) — Microsoft Edge TTS WebSocket client
      edge_tts.Communicate(text, voice).save(path) — async method
  - asyncio (stdlib) — wraps the async edge_tts call in a synchronous interface
  - pathlib (stdlib) — path handling
"""

import asyncio
import sys
from pathlib import Path


from config import TTS_VOICE, TTS_TIMEOUT, AUDIO_DIR
from logger import get_logger

log = get_logger("tts")

try:
    import edge_tts  # type: ignore
except ImportError:
    log.error("edge_tts not installed. Install with: pip install edge-tts")
    edge_tts = None  # type: ignore


# ---------------------------------------------------------------------------
# Internal async helper
# ---------------------------------------------------------------------------

async def _synthesize_async(text: str, output_path: Path, voice: str) -> None:
    """
    Async core: create an edge_tts.Communicate object and save the MP3.

    Args:
        text:        Japanese text to speak.
        output_path: Destination .mp3 file path.
        voice:       Edge TTS voice name (e.g. "ja-JP-NanamiNeural").

    Raises:
        RuntimeError on edge_tts errors.
    """
    log.debug("Synthesising TTS: voice=%s text='%s'", voice, text[:60])

    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(output_path))

    log.info("TTS MP3 saved to: %s", output_path)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def synthesize(text: str, output_path: Path) -> Path:
    """
    Synthesise Japanese TTS audio and save it as an MP3.

    Wraps the async edge_tts call with asyncio.run() so callers can use this
    function synchronously from the terminal pipeline.

    Args:
        text:        Japanese text to synthesise (e.g. an example sentence).
        output_path: Full path (including filename) where the MP3 will be saved.
                     Parent directories are created automatically.

    Returns:
        Path — the path to the saved MP3 file.

    Raises:
        RuntimeError — if edge_tts is not installed, the network is unavailable,
                       or synthesis times out (E-5).
    """
    log.info("TTS synthesize called: output=%s", output_path)

    if edge_tts is None:
        raise RuntimeError(
            "edge-tts is not installed. Install with: pip install edge-tts\n"
            "Audio generation failed — card will be added without audio."
        )

    if not text or not text.strip():
        raise RuntimeError("TTS called with empty text — nothing to synthesise.")

    # Ensure the output directory exists.
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        # Run async synthesis with a timeout.
        asyncio.run(
            asyncio.wait_for(
                _synthesize_async(text, output_path, TTS_VOICE),
                timeout=TTS_TIMEOUT,
            )
        )
    except asyncio.TimeoutError as exc:
        log.error("TTS timed out after %ds for text='%s'", TTS_TIMEOUT, text[:60])
        raise RuntimeError(
            f"Audio generation failed — edge-tts timed out after {TTS_TIMEOUT}s.\n"
            "Check your internet connection. Card will be added without audio."
        ) from exc
    except Exception as exc:
        log.exception("TTS synthesis error: %s", exc)
        raise RuntimeError(
            f"Audio generation failed — {exc}\n"
            "Card will be added without audio."
        ) from exc

    if not output_path.exists():
        raise RuntimeError(
            f"TTS did not produce a file at {output_path}. "
            "Card will be added without audio."
        )

    size_kb = output_path.stat().st_size / 1024
    log.info("TTS complete: %s (%.1f KB)", output_path.name, size_kb)

    return output_path


def make_audio_path(word: str) -> Path:
    """
    Build the audio file path for the given word.

    Format: ~/.ajs/Clipped Audio/<word>.mp3
    Filename is the word only (no hash). Same word overwrites the same file.

    Args:
        word: Japanese word (used in filename).

    Returns:
        Path to the (not yet created) MP3 file.
    """
    # Sanitise the word for use in a filename (keep alphanumeric and CJK).
    safe_word = "".join(c for c in word if c.isalnum() or "\u3000" <= c <= "\u9fff").strip()
    if not safe_word:
        import hashlib
        safe_word = hashlib.sha1(word.encode("utf-8")).hexdigest()[:8]
    filename = f"{safe_word}.mp3"
    path = AUDIO_DIR / filename
    log.debug("Audio path for '%s': %s", word, path)
    return path
