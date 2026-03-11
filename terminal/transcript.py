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
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

# Japanese sentence-final punctuation (full-width and ASCII variants)
_SENT_END = re.compile(r'[。！？…!?]')

print("[DEBUG] transcript.py: module loading")

from config import TRANSCRIPT_TMP_DIR, WHISPER_MODEL_SIZE, WHISPER_DEVICE, WHISPER_COMPUTE_TYPE
from logger import get_logger
import normalizer

log = get_logger("transcript")


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

    cmd = [
        "yt-dlp",
        "--skip-download",
        "--sub-lang", "ja",
        "--sub-format", "json3",
        "--output", output_template,
    ]

    if auto:
        cmd.append("--write-auto-sub")
        print("[DEBUG] transcript._run_ytdlp: requesting auto-generated captions")
        log.debug("Requesting auto-generated Japanese captions for: %s", url)
    else:
        cmd.append("--write-sub")
        print("[DEBUG] transcript._run_ytdlp: requesting manual subtitles")
        log.debug("Requesting manual Japanese subtitles for: %s", url)

    cmd.append(url)

    print(f"[DEBUG] transcript._run_ytdlp: running command: {' '.join(cmd)}")
    log.debug("yt-dlp command: %s", " ".join(cmd))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        print(f"[DEBUG] transcript._run_ytdlp: yt-dlp finished with rc={result.returncode}")
        log.debug("yt-dlp rc=%d stdout=%s", result.returncode, result.stdout[:200])

        if result.returncode != 0:
            log.warning("yt-dlp returned non-zero: %s", result.stderr[:300])

    except FileNotFoundError:
        print("[DEBUG] transcript._run_ytdlp: yt-dlp not found in PATH")
        log.error("yt-dlp not found — install it with: pip install yt-dlp")
        return None
    except subprocess.TimeoutExpired:
        print("[DEBUG] transcript._run_ytdlp: yt-dlp timed out after 120s")
        log.error("yt-dlp timed out fetching %s", url)
        return None

    # Locate the downloaded file (yt-dlp appends language code to the filename).
    pattern = str(tmp_dir / "ajs_transcript*.json3")
    matches = glob.glob(pattern)
    print(f"[DEBUG] transcript._run_ytdlp: glob found files: {matches}")

    if matches:
        return Path(matches[0])

    log.debug("No .json3 file found in %s after yt-dlp run", tmp_dir)
    return None


def _parse_json3(path: Path) -> list[dict]:
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
    print(f"[DEBUG] transcript._parse_json3: parsing {path}")
    log.debug("Parsing json3 subtitle file: %s", path)

    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[DEBUG] transcript._parse_json3: failed to read/parse file — {exc}")
        log.error("Failed to parse json3 file %s: %s", path, exc)
        return []

    segments: list[dict] = []
    events = data.get("events", [])
    print(f"[DEBUG] transcript._parse_json3: found {len(events)} events")

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

        segments.append({
            "start": start_ms / 1000.0,
            "duration": duration_ms / 1000.0,
            "text": text,
        })

    print(f"[DEBUG] transcript._parse_json3: parsed {len(segments)} non-empty segments")
    log.debug("Parsed %d subtitle segments", len(segments))
    return segments


# ---------------------------------------------------------------------------
# Sentence merger
# ---------------------------------------------------------------------------

def _merge_into_sentences(segments: list[dict], max_gap_s: float = 1.5) -> list[dict]:
    """
    Merge raw subtitle segments into proper Japanese sentences.

    Subtitle tracks — whether manual or auto-generated — break at display
    timing boundaries, not linguistic ones.  A single sentence may span
    several segments; a single segment may contain multiple sentences.
    This function reassembles them correctly.

    Strategy:
      1. Walk segments in order, accumulating text into a buffer.
      2. After appending each chunk, scan for sentence-final punctuation
         (。！？… and ASCII ! ?) and flush the buffer as a sentence when found.
      3. Force-flush on a silence gap > max_gap_s seconds (scene change /
         speaker pause) even without punctuation.
      4. Fall back to raw segments if merging produces no output.

    Args:
        segments:  Raw parsed segments from _parse_json3.
        max_gap_s: Silence gap (seconds) that forces a sentence boundary.

    Returns:
        list[dict] with same keys as input: start, duration, text.
    """
    if not segments:
        return []

    sentences: list[dict] = []
    buf: list[tuple[str, float, float]] = []  # (text, start, end)

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

        # Split within this segment at sentence-final punctuation,
        # keeping the punctuation character attached to its sentence.
        parts   = _SENT_END.split(text)
        markers = _SENT_END.findall(text)

        for i, part in enumerate(parts):
            chunk = (part + markers[i]) if i < len(markers) else part
            chunk = chunk.strip()
            if not chunk:
                continue
            buf.append((chunk, seg_start, seg_end))
            if i < len(markers):   # sentence-final punctuation found → flush
                _flush()

    _flush()  # flush any remaining buffer

    if not sentences:
        log.warning("_merge_into_sentences produced no output — returning raw segments")
        return segments

    log.debug("Merged %d raw segments → %d sentences", len(segments), len(sentences))
    print(f"[DEBUG] transcript._merge_into_sentences: {len(segments)} segments → {len(sentences)} sentences")
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
    cmd = [
        "yt-dlp",
        "--extract-audio",
        "--audio-format", "wav",
        "--audio-quality", "0",
        "--output", output_template,
        url,
    ]
    print(f"[DEBUG] transcript._download_audio: running {' '.join(cmd)}")
    log.debug("Downloading audio for Whisper: %s", url)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )
        print(f"[DEBUG] transcript._download_audio: yt-dlp rc={result.returncode}")
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
    print(f"[DEBUG] transcript._download_audio: found files: {matches}")
    return Path(matches[0]) if matches else None


def _transcribe_with_whisper(audio_path: Path) -> list[dict]:
    """
    Transcribe a local audio file using faster-whisper with Japanese language.

    Returns a list of segment dicts (start, duration, text), same format as
    _parse_json3, or an empty list on failure.
    """
    print(f"[DEBUG] transcript._transcribe_with_whisper: loading model '{WHISPER_MODEL_SIZE}'")
    log.info("Transcribing audio with Whisper model '%s'", WHISPER_MODEL_SIZE)
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        log.error("faster-whisper not installed — run: pip install faster-whisper")
        print("[DEBUG] transcript._transcribe_with_whisper: faster-whisper not installed")
        return []

    try:
        model = WhisperModel(WHISPER_MODEL_SIZE, device=WHISPER_DEVICE, compute_type=WHISPER_COMPUTE_TYPE)
        segments, info = model.transcribe(str(audio_path), language="ja", beam_size=5)
        print(f"[DEBUG] transcript._transcribe_with_whisper: detected language '{info.language}' with probability {info.language_probability:.2f}")
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

        print(f"[DEBUG] transcript._transcribe_with_whisper: got {len(result)} segments")
        log.info("Whisper produced %d segments", len(result))
        return result

    except Exception as exc:
        log.error("Whisper transcription failed: %s", exc)
        print(f"[DEBUG] transcript._transcribe_with_whisper: failed — {exc}")
        return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fetch_transcript(url: str) -> list[dict]:
    """
    Fetch the Japanese subtitle/transcript for the given video URL.

    Tries manual subtitles first, then auto-generated captions.
    Returns an empty list if neither is available (the caller is expected to
    handle the E-3 fallback — offer manual sentence entry).

    Args:
        url: YouTube (or compatible) video URL.

    Returns:
        list[dict] — each entry: {start: float, duration: float, text: str}
    """
    print(f"[DEBUG] transcript.fetch_transcript: fetching transcript for {url}")
    log.info("Fetching transcript for URL: %s", url)

    TRANSCRIPT_TMP_DIR.mkdir(parents=True, exist_ok=True)

    # Use a fresh temp dir for this run to avoid stale files.
    with tempfile.TemporaryDirectory(dir=str(TRANSCRIPT_TMP_DIR), prefix="ajs_run_") as tmp_str:
        tmp_dir = Path(tmp_str)
        print(f"[DEBUG] transcript.fetch_transcript: using tmp dir {tmp_dir}")

        # 1. Try manual subtitles.
        sub_file = _run_ytdlp(url, tmp_dir, auto=False)

        if not sub_file:
            print("[DEBUG] transcript.fetch_transcript: no manual subtitles, trying auto-generated")
            log.info("No manual subtitles found — trying auto-generated captions")
            sub_file = _run_ytdlp(url, tmp_dir, auto=True)

        if sub_file:
            raw_segments = _parse_json3(sub_file)
            segments     = _merge_into_sentences(raw_segments)
            segments     = normalizer.annotate_segments(segments)
            print(f"[DEBUG] transcript.fetch_transcript: returning {len(segments)} sentences (from {len(raw_segments)} raw segments)")
            log.info("Returning %d sentences (merged from %d raw segments)", len(segments), len(raw_segments))
            return segments

        # 3. No subtitle track found — fall back to local Whisper ASR.
        print("[DEBUG] transcript.fetch_transcript: no subtitles found — falling back to Whisper ASR")
        log.info("No subtitle track found — attempting Whisper ASR transcription")
        print("[AJS] No subtitles found. Transcribing audio locally (this may take 30–60 seconds)...")

        audio_file = _download_audio(url, tmp_dir)
        if not audio_file:
            print("[DEBUG] transcript.fetch_transcript: audio download failed — giving up")
            log.warning("Audio download failed for Whisper fallback: %s", url)
            return []

        raw_segments = _transcribe_with_whisper(audio_file)
        if not raw_segments:
            return []

        segments = _merge_into_sentences(raw_segments)
        segments = normalizer.annotate_segments(segments)
        print(f"[DEBUG] transcript.fetch_transcript: Whisper returning {len(segments)} sentences")
        log.info("Whisper ASR returning %d sentences", len(segments))
        return segments
