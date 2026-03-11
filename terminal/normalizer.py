"""
AJS Terminal — normalizer.py
Converts Japanese text (Romaji, Kanji, mixed) to a clean Hiragana reading.

This satisfies FR-5 (Romaji Normalisation): the system shall convert Romaji input
to Hiragana using pykakasi before any downstream processing.

Inputs:
  text (str) — any Japanese text: Romaji, Kanji, Katakana, Hiragana, or mixed

Outputs:
  str — Hiragana reading of the input text

Packages used:
  - pykakasi (third-party) — converts Romaji/Kanji to Hiragana/Katakana/Romaji
      pykakasi.Kakasi().convert(text) returns a list of dicts with keys:
          orig     : original substring
          hira     : hiragana reading
          kana     : katakana reading
          hepburn  : Hepburn romaji
          passport : Passport romaji
          kunrei   : Kunrei romaji
"""

import re
import sys

print("[DEBUG] normalizer.py: module loading")

from logger import get_logger

log = get_logger("normalizer")
_KANA_ONLY_RE = re.compile(r"^[\u3040-\u30ff\u30fc\u3000-\u303f\uff01-\uff60\s]+$")

# ---------------------------------------------------------------------------
# pykakasi initialisation (one instance is reused across calls)
# ---------------------------------------------------------------------------

try:
    import pykakasi  # type: ignore
    print("[DEBUG] normalizer.py: pykakasi imported successfully")
    _kks = pykakasi.Kakasi()
    log.debug("pykakasi Kakasi instance created")
except ImportError:
    print("[DEBUG] normalizer.py: pykakasi not installed — normalizer will pass text through unchanged")
    log.error("pykakasi not installed. Install with: pip install pykakasi")
    _kks = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def annotate_segments(segments: list[dict]) -> list[dict]:
    """
    Add 'reading', 'kana', 'romaji', and 'display' fields to each transcript segment.

    - reading : full hiragana reading of the segment text
    - romaji  : Hepburn romaji of the segment text
    - display : "original（hiragana）" — shown in fzf so users can read kanji

    All three forms are used for search so users can find segments by typing
    kanji, hiragana, or romaji.  Falls back gracefully if pykakasi is absent.

    Args:
        segments: list of dicts with at least a 'text' key.

    Returns:
        Same list with reading/romaji/display added in-place.
    """
    for seg in segments:
        text = seg.get("text", "")
        if _kks and text:
            try:
                tokens  = _kks.convert(text)
                reading = "".join(t.get("hira", "") or t.get("orig", "") for t in tokens)
                romaji  = "".join(t.get("hepburn", "") or t.get("orig", "") for t in tokens)
                kana_parts: list[str] = []
                for token in tokens:
                    orig = token.get("orig", "")
                    hira = token.get("hira", "") or orig
                    kana_parts.append(orig if _KANA_ONLY_RE.match(orig) else hira)
                kana_line = "".join(kana_parts)
            except Exception:
                reading = text
                romaji  = text
                kana_line = text
        else:
            reading = text
            romaji  = text
            kana_line = text

        seg["reading"] = reading
        seg["kana"]    = kana_line
        seg["romaji"]  = romaji.lower()
        seg["display"] = f"{text}（{reading}）" if reading and reading != text else text

    return segments


def get_romaji(text: str) -> str:
    """
    Return the Hepburn romaji transliteration of the input text.
    Falls back to original text if pykakasi is unavailable.
    """
    print(f"[DEBUG] normalizer.get_romaji: input='{text}'")
    if not text or not text.strip() or _kks is None:
        return text
    try:
        result = _kks.convert(text)
        romaji = "".join(token.get("hepburn", token.get("orig", "")) for token in result)
        print(f"[DEBUG] normalizer.get_romaji: romaji='{romaji}'")
        log.info("Romaji for '%s' => '%s'", text, romaji)
        return romaji
    except Exception as exc:
        log.exception("pykakasi romaji conversion failed: %s", exc)
        return text


def get_reading(text: str) -> str:
    """
    Return the Hiragana reading of the input text.

    If pykakasi is not available, returns the original text unchanged
    with a warning so the pipeline can still continue.

    Conversion logic:
      - For each token returned by pykakasi, prefer the 'hira' field
        (hiragana). If 'hira' is empty, fall back to 'orig' (original text).
      - Tokens are joined without separator to reconstruct the word.

    Args:
        text: Japanese text in any script or Romaji.

    Returns:
        Hiragana string, e.g. "はなはだしい" for "hanahadashii" or "甚だしい".
    """
    print(f"[DEBUG] normalizer.get_reading: input='{text}'")
    log.debug("get_reading called with text='%s'", text)

    if not text or not text.strip():
        print("[DEBUG] normalizer.get_reading: empty input — returning as-is")
        log.warning("Empty text passed to get_reading")
        return text

    if _kks is None:
        print("[DEBUG] normalizer.get_reading: pykakasi unavailable — returning original text")
        log.warning("pykakasi unavailable — returning original text")
        return text

    try:
        result = _kks.convert(text)
        print(f"[DEBUG] normalizer.get_reading: pykakasi returned {len(result)} tokens")
        log.debug("pykakasi produced %d tokens for input '%s'", len(result), text)

        hiragana_parts: list[str] = []
        for token in result:
            hira = token.get("hira", "")
            orig = token.get("orig", "")

            if hira:
                hiragana_parts.append(hira)
            else:
                # Preserve punctuation or characters pykakasi did not convert.
                hiragana_parts.append(orig)

        reading = "".join(hiragana_parts)
        print(f"[DEBUG] normalizer.get_reading: reading='{reading}'")
        log.info("Reading for '%s' => '%s'", text, reading)
        return reading

    except Exception as exc:
        print(f"[DEBUG] normalizer.get_reading: pykakasi error — {exc}")
        log.exception("pykakasi conversion failed for '%s': %s", text, exc)
        return text
