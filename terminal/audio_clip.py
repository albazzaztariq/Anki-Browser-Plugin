"""
AJS Terminal — audio_clip.py
Extract a short audio clip around the hotkey timestamp using yt-dlp.

Default window:
  - 5 seconds before
  - 5 seconds after
  - centered on (timestamp - 1s) to account for reaction delay
"""

import glob
import io
import runpy
import subprocess
import sys
from pathlib import Path

from config import (
    AUDIO_CLIP_PRE_S,
    AUDIO_CLIP_POST_S,
    AUDIO_CLIP_OFFSET_S,
)
from logger import get_logger

log = get_logger("audio_clip")


def _is_frozen() -> bool:
    """True when running as a PyInstaller bundle (ajs.exe)."""
    return getattr(sys, "frozen", False)


def _run_ytdlp_inprocess(args: list[str]) -> tuple[int, str, str]:
    """
    Run yt_dlp in the current process (for PyInstaller bundle).
    Returns (returncode, stdout, stderr). Caller passes only yt-dlp args.
    """
    old_argv = sys.argv
    old_stdout, old_stderr = sys.stdout, sys.stderr
    out_buf, err_buf = io.StringIO(), io.StringIO()
    sys.argv = ["yt-dlp"] + args
    sys.stdout, sys.stderr = out_buf, err_buf
    exit_code = 0
    try:
        runpy.run_module("yt_dlp", run_name="__main__")
    except SystemExit as e:
        exit_code = int(e.code) if e.code is not None else 0
    finally:
        sys.argv = old_argv
        sys.stdout, sys.stderr = old_stdout, old_stderr
    return exit_code, out_buf.getvalue(), err_buf.getvalue()


def clip_from_video(url: str, timestamp: float, output_path: Path) -> Path:
    """
    Clip a short audio segment from the video around the hotkey timestamp.
    Saves to output_path (mp3). Returns the actual saved file path.
    """
    # Center on (timestamp - 1s) to cover reaction delay.
    center = max(0.0, float(timestamp) - AUDIO_CLIP_OFFSET_S)
    start = max(0.0, center - AUDIO_CLIP_PRE_S)
    end = max(start, center + AUDIO_CLIP_POST_S)

    # yt-dlp expects a template; use .%(ext)s so mp3 lands at output_path.
    output_template = str(output_path.with_suffix(".%(ext)s"))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    section = f"*{start:.3f}-{end:.3f}"
    yt_dlp_args = [
        "--extract-audio",
        "--audio-format", "mp3",
        "--audio-quality", "0",
        "--download-sections", section,
        "--force-keyframes-at-cuts",
        "--output", output_template,
        "--js-runtimes", "node",
        url,
    ]

    log.info("Audio clip window: %.3fs–%.3fs (center=%.3fs)", start, end, center)
    log.debug("yt-dlp clip args: %s", " ".join(yt_dlp_args))

    if _is_frozen():
        returncode, stdout, stderr = _run_ytdlp_inprocess(yt_dlp_args)
    else:
        result = subprocess.run(
            [sys.executable, "-m", "yt_dlp"] + yt_dlp_args,
            capture_output=True,
            text=True,
            timeout=300,
        )
        returncode, stdout, stderr = result.returncode, result.stdout, result.stderr

    log.debug("yt-dlp rc=%d stdout=%s", returncode, (stdout or "")[:200])
    if returncode != 0:
        log.warning("yt-dlp clip failed: %s", (stderr or "")[:300])
        raise RuntimeError("Audio clip failed — yt-dlp returned non-zero.")

    if output_path.exists():
        return output_path

    # Fallback: locate any output with the same base name.
    matches = glob.glob(str(output_path.with_suffix(".*")))
    if matches:
        return Path(matches[0])

    raise RuntimeError(f"Audio clip did not produce a file at {output_path}")
