"""
AJS Terminal — transcript.py
Fetches and parses Japanese-language transcripts (subtitle tracks) from YouTube videos.

Method:
  Uses yt-dlp as a subprocess to download the subtitle file in json3 format to a
  temporary directory, then parses the resulting JSON into a flat list of timed segments.

  Priority:
    1. Manual Japanese subtitles  (--sub-lang ja)
    2. Auto-generated Japanese captions (--write-auto-sub --sub-lang ja)
    3. Returns empty list if neither is available (caller handles E-3 fallback)

Inputs:
  url (str) — YouTube or other yt-dlp-compatible video URL

Outputs:
  list[dict] — each dict has keys:
      start    (float)  — segment start time in seconds
      duration (float)  — segment duration in seconds
      text     (str)    — subtitle text for this segment

Packages used:
  - subprocess (stdlib) — invokes yt-dlp CLI
  - json       (stdlib) — parses json3 subtitle format
  - pathlib    (stdlib) — temporary file paths
  - glob       (stdlib) — locates downloaded subtitle file
"""

import glob
import io
import json
import re
import runpy
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

def _is_frozen() -> bool:
    """True when running as a PyInstaller bundle (ajs.exe)."""
    return getattr(sys, "frozen", False)

# Japanese sentence-final punctuation (full-width and ASCII variants)
_SENT_END = re.compile(r'[。！？…!?]')


from config import TRANSCRIPT_TMP_DIR, WHISPER_MODEL_SIZE, WHISPER_DEVICE, WHISPER_COMPUTE_TYPE
from logger import get_logger
import normalizer

log = get_logger("transcript")


def _run_ytdlp_inprocess(args: list[str], timeout: float = 120) -> tuple[int, str, str]:
    """
    Run yt_dlp in the current process (for PyInstaller bundle where sys.executable is ajs.exe).
    Returns (returncode, stdout, stderr). Caller must not pass executable; args are CLI args for yt-dlp.
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


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _run_ytdlp(url: str, tmp_dir: Path, auto: bool) -> Optional[Path]:
    """
    Run yt-dlp to download the subtitle file into tmp_dir.

    Args:
        url     : Video URL.
        tmp_dir : Directory to write the subtitle file into.
        auto    : If True, request auto-generated captions; otherwise manual only.

    Returns:
        Path to the downloaded .json3 file, or None on failure.
    """
    output_template = str(tmp_dir / "ajs_transcript")

    yt_dlp_args = [
        "--skip-download",
        "--sub-lang", "ja",
        "--sub-format", "json3",
        "--output", output_template,
        "--js-runtimes", "node",
    ]
    if auto:
        yt_dlp_args.append("--write-auto-sub")
        log.debug("Requesting auto-generated Japanese captions for: %s", url)
    else:
        yt_dlp_args.append("--write-sub")
        log.debug("Requesting manual Japanese subtitles for: %s", url)
    yt_dlp_args.append(url)

    if _is_frozen():
        log.debug("yt-dlp (in-process): %s", " ".join(yt_dlp_args))
        try:
            returncode, stdout, stderr = _run_ytdlp_inprocess(yt_dlp_args)
        except Exception as e:
            log.error("yt-dlp in-process failed: %s", e)
            return None
        log.debug("yt-dlp rc=%d stdout=%s", returncode, (stdout or "")[:200])
        if returncode != 0:
            log.warning("yt-dlp returned non-zero: %s", (stderr or "")[:300])
    else:
        cmd = [sys.executable, "-m", "yt_dlp"] + yt_dlp_args
        log.debug("yt-dlp command: %s", " ".join(cmd))
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )
            returncode, stdout, stderr = result.returncode, result.stdout, result.stderr
            log.debug("yt-dlp rc=%d stdout=%s", result.returncode, result.stdout[:200])
            if result.returncode != 0:
                log.warning("yt-dlp returned non-zero: %s", result.stderr[:300])
        except FileNotFoundError:
            log.error("yt-dlp not found — install it with: pip install yt-dlp")
            return None
        except subprocess.TimeoutExpired:
            log.error("yt-dlp timed out fetching %s", url)
            return None

    # Locate the downloaded file (yt-dlp appends language code to the filename).
    pattern = str(tmp_dir / "ajs_transcript*.json3")
    matches = glob.glob(pattern)

    if matches:
        return Path(matches[0])

    log.debug("No .json3 file found in %s after yt-dlp run", tmp_dir)
    return None


def _parse_json3(path: Path, video_offset: float = 0.0) -> list[dict]:
    """
    Parse a yt-dlp json3 subtitle file into a list of segment dicts.

    json3 format structure:
    {
      "events": [
        {
          "tStartMs": 1234,
          "dDurationMs": 5000,
          "segs": [{"utf8": "some text"}, ...]
        },
        ...
      ]
    }

    Args:
        path: Path to the .json3 file.

    Returns:
        list[dict] with keys: start (float), duration (float), text (str).
    """
    log.debug("Parsing json3 subtitle file: %s", path)

    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        log.error("Failed to parse json3 file %s: %s", path, exc)
        return []

    segments: list[dict] = []
    events = data.get("events", [])

    for event in events:
        segs = event.get("segs", [])
        text_parts = [s.get("utf8", "") for s in segs]
        text = "".join(text_parts)
        # Strip all newline/carriage-return variants (Windows \r\n, old Mac \r, Unix \n)
        text = text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
        # Collapse runs of whitespace to a single space
        text = re.sub(r" +", " ", text).strip()

        if not text:
            continue

        start_ms = event.get("tStartMs", 0)
        duration_ms = event.get("dDurationMs", 0)

        # Apply video offset to align with actual playback time
        adjusted_start = (start_ms / 1000.0) - video_offset
        segments.append({
            "start": max(adjusted_start, 0.0),  # don't allow negative start times
            "duration": duration_ms / 1000.0,
            "text": text,
        })

    log.debug("Parsed %d subtitle segments", len(segments))
    return segments


# ---------------------------------------------------------------------------
# Sentence merger
# ---------------------------------------------------------------------------

def _merge_into_sentences(
    segments: list[dict],
    max_gap_s: float = 1.5,
    max_segment_duration_s: float = 30.0,
    target_segment_duration_s: float = 10.0,
) -> list[dict]:
    """
    Merge raw subtitle segments into timed chunks, keeping entries short.

    Subtitle tracks break at display timing, not linguistic boundaries.
    This function reassembles text at sentence ends and on pauses, but
    caps the length of each entry so the transcript stays granular.

    Strategy:
      1. Walk segments in order, accumulating text into a buffer.
      2. Flush the buffer (emit one transcript entry) when:
         - sentence-final punctuation (。！？…!?) is found, or
         - silence gap > max_gap_s seconds, or
         - buffer duration would exceed max_segment_duration_s (hard cap 30s), or
         - buffer duration has reached target_segment_duration_s (~5–10s preferred).
      3. Fall back to raw segments if merging produces no output.

    Args:
        segments:  Raw parsed segments from _parse_json3.
        max_gap_s: Silence gap (seconds) that forces a boundary.
        max_segment_duration_s: No entry longer than this (default 30s).
        target_segment_duration_s: Prefer flushing when duration reaches this (default 10s).

    Returns:
        list[dict] with same keys as input: start, duration, text.
    """
    if not segments:
        return []

    sentences: list[dict] = []
    buf: list[tuple[str, float, float]] = []  # (text, start, end)

    def _buf_duration() -> float:
        if not buf:
            return 0.0
        return buf[-1][2] - buf[0][1]

    def _flush():
        if not buf:
            return
        merged = "".join(p[0] for p in buf).strip()
        if merged:
            sentences.append({
                "start":    buf[0][1],
                "duration": buf[-1][2] - buf[0][1],
                "text":     merged,
            })
        buf.clear()

    for seg in segments:
        text = seg["text"].strip()
        if not text:
            continue

        seg_start = seg["start"]
        seg_end   = seg_start + max(seg["duration"], 0.1)

        # Force split on silence gap
        if buf and (seg_start - buf[-1][2]) > max_gap_s:
            _flush()

        # Split within this segment at sentence-final punctuation
        parts   = _SENT_END.split(text)
        markers = _SENT_END.findall(text)

        for i, part in enumerate(parts):
            chunk = (part + markers[i]) if i < len(markers) else part
            chunk = chunk.strip()
            if not chunk:
                continue

            # Hard cap: adding this chunk would exceed max duration → flush first
            if buf and (seg_end - buf[0][1]) > max_segment_duration_s:
                _flush()

            buf.append((chunk, seg_start, seg_end))

            if i < len(markers):
                _flush()  # sentence end
            elif _buf_duration() >= target_segment_duration_s:
                _flush()  # reached target length (~5–10s)

    _flush()

    if not sentences:
        log.warning("_merge_into_sentences produced no output — returning raw segments")
        return segments

    log.debug("Merged %d raw segments → %d entries (max %.0fs)", len(segments), len(sentences), max_segment_duration_s)
    return sentences


# ---------------------------------------------------------------------------
# Whisper ASR fallback
# ---------------------------------------------------------------------------

def _download_audio(url: str, tmp_dir: Path) -> Optional[Path]:
    """
    Download the audio track of a video into tmp_dir using yt-dlp.

    Returns the path to the downloaded WAV file, or None on failure.
    """
    output_template = str(tmp_dir / "ajs_audio.%(ext)s")
    yt_dlp_args = [
        "--extract-audio",
        "--audio-format", "wav",
        "--audio-quality", "0",
        "--output", output_template,
        "--js-runtimes", "node",
        url,
    ]
    log.debug("Downloading audio for Whisper: %s", url)
    if _is_frozen():
        try:
            returncode, _stdout, stderr = _run_ytdlp_inprocess(yt_dlp_args)
        except Exception as e:
            log.error("yt-dlp in-process failed: %s", e)
            return None
        if returncode != 0:
            log.warning("yt-dlp audio download failed: %s", (stderr or "")[:300])
            return None
    else:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "yt_dlp"] + yt_dlp_args,
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode != 0:
                log.warning("yt-dlp audio download failed: %s", result.stderr[:300])
                return None
        except FileNotFoundError:
            log.error("yt-dlp not found — cannot download audio for Whisper")
            return None
        except subprocess.TimeoutExpired:
            log.error("yt-dlp audio download timed out")
            return None

    matches = glob.glob(str(tmp_dir / "ajs_audio.*"))
    return Path(matches[0]) if matches else None


def _transcribe_with_whisper(audio_path: Path) -> list[dict]:
    """
    Transcribe a local audio file using faster-whisper with Japanese language.

    Returns a list of segment dicts (start, duration, text), same format as
    _parse_json3, or an empty list on failure.
    """
    log.info("Transcribing audio with Whisper model '%s'", WHISPER_MODEL_SIZE)
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        log.error("faster-whisper not installed — run: pip install faster-whisper")
        return []

    try:
        model = WhisperModel(WHISPER_MODEL_SIZE, device=WHISPER_DEVICE, compute_type=WHISPER_COMPUTE_TYPE)
        segments, info = model.transcribe(str(audio_path), language="ja", beam_size=5)
        log.debug("Whisper detected language=%s (p=%.2f)", info.language, info.language_probability)

        result = []
        for seg in segments:
            text = seg.text.strip()
            if not text:
                continue
            result.append({
                "start":    seg.start,
                "duration": seg.end - seg.start,
                "text":     text,
            })

        log.info("Whisper produced %d segments", len(result))
        return result

    except Exception as exc:
        log.error("Whisper transcription failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_transcript(url: str, video_offset: float = 0.0) -> list[dict]:
    """
    Fetch the Japanese subtitle/transcript for the given video URL.

    Args:
        url: YouTube (or compatible) video URL.
        video_offset: Optional timestamp offset from video player to align transcripts

    Returns:
        list[dict] — each entry: {start: float, duration: float, text: str}
    """
    log.info("Fetching transcript for URL: %s", url)

    TRANSCRIPT_TMP_DIR.mkdir(parents=True, exist_ok=True)

    # Use a fresh temp dir for this run to avoid stale files.
    with tempfile.TemporaryDirectory(dir=str(TRANSCRIPT_TMP_DIR), prefix="ajs_run_") as tmp_str:
        tmp_dir = Path(tmp_str)

        # 1. Try manual subtitles.
        sub_file = _run_ytdlp(url, tmp_dir, auto=False)

        if not sub_file:
            log.info("No manual subtitles found — trying auto-generated captions")
            sub_file = _run_ytdlp(url, tmp_dir, auto=True)

        if sub_file:
            raw_segments = _parse_json3(sub_file, video_offset=video_offset)
            segments     = _merge_into_sentences(raw_segments)
            segments     = normalizer.annotate_segments(segments)
            log.info("Returning %d sentences (merged from %d raw segments)", len(segments), len(raw_segments))
            return segments

        # 3. No subtitle track found — fall back to local Whisper ASR.
        log.info("No subtitle track found — attempting Whisper ASR transcription")
        print("[AJS] No subtitles found. Transcribing audio locally (this may take 30–60 seconds)...")

        audio_file = _download_audio(url, tmp_dir)
        if not audio_file:
            log.warning("Audio download failed for Whisper fallback: %s", url)
            return []

        raw_segments = _transcribe_with_whisper(audio_file)
        if not raw_segments:
            return []

        segments = _merge_into_sentences(raw_segments)
        segments = normalizer.annotate_segments(segments)
        log.info("Whisper ASR returning %d sentences", len(segments))
        return segments
