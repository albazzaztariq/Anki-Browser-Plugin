"""
AJS Terminal — card_writer.py
Writes the assembled card data to the IPC file read by the Anki add-on.

The pending card file (~/.ajs/pending_card.json) is the sole communication
channel between the terminal pipeline and the Anki add-on (bridge.py).
The add-on polls for this file every 2 seconds via a QTimer.

Card data schema (all fields are strings unless noted):
  {
      "word":             str  — kanji/kana form of the word
      "reading":          str  — hiragana reading
      "definition_en":    str  — English definition
      "example_sentence": str  — Japanese example sentence
      "part_of_speech":   str  — grammatical category
      "audio_path":       str  — absolute path to the MP3 file (may be "")
      "source_url":       str  — original video URL
      "created_at":       str  — ISO-8601 UTC timestamp
  }

Inputs:
  card_data (dict) — the assembled card dict (fields listed above)

Outputs:
  None (writes file to disk)

Packages used:
  - json     (stdlib) — serialises the card dict to JSON
  - pathlib  (stdlib) — file path handling
  - datetime (stdlib) — generates ISO-8601 timestamp
"""

import json
import sys
from typing import Dict, Optional
from datetime import datetime, timezone
from pathlib import Path

print("[DEBUG] card_writer.py: module loading")

from config import PENDING_CARD_PATH
from logger import get_logger

log = get_logger("card_writer")

# Fields that must be present in card_data (values may be empty strings).
_REQUIRED_KEYS = {
    "word", "reading", "definition_en", "example_sentence",
    "part_of_speech", "audio_path", "source_url",
}


def write_pending_card(card_data: dict) -> None:
    """
    Serialise card_data to JSON and write it to the pending card file.

    The file is written atomically: we write to a temp file in the same
    directory and then rename it, to avoid the Anki add-on reading a
    partially-written file.

    Adds a 'created_at' field automatically if not present.

    Args:
        card_data: Dict matching the schema documented above.

    Raises:
        ValueError:  If required fields are missing from card_data.
        OSError:     If the directory cannot be created or the file cannot be written.
    """
    print(f"[DEBUG] card_writer.write_pending_card: writing card for word='{card_data.get('word', '?')}'")
    log.info("Writing pending card for word='%s'", card_data.get("word", "?"))

    # Validate.
    missing = _REQUIRED_KEYS - set(card_data.keys())
    if missing:
        msg = f"card_data is missing required fields: {missing}"
        print(f"[DEBUG] card_writer.write_pending_card: {msg}")
        log.error(msg)
        raise ValueError(msg)

    # Add timestamp.
    payload = dict(card_data)
    if "created_at" not in payload:
        payload["created_at"] = datetime.now(timezone.utc).isoformat()

    # Ensure the ~/.ajs directory exists.
    pending_dir = PENDING_CARD_PATH.parent
    print(f"[DEBUG] card_writer.write_pending_card: ensuring dir {pending_dir}")
    try:
        pending_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        log.error("Cannot create pending card directory %s: %s", pending_dir, exc)
        raise

    # Atomic write: temp file → rename.
    tmp_path = PENDING_CARD_PATH.with_suffix(".tmp")
    print(f"[DEBUG] card_writer.write_pending_card: writing to tmp file {tmp_path}")

    try:
        tmp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp_path.replace(PENDING_CARD_PATH)
    except OSError as exc:
        log.error("Failed to write pending card to %s: %s", PENDING_CARD_PATH, exc)
        raise

    print(f"[DEBUG] card_writer.write_pending_card: pending card written to {PENDING_CARD_PATH}")
    log.info("Pending card written to: %s", PENDING_CARD_PATH)


def clear_pending_card() -> None:
    """
    Delete the pending card file if it exists.

    Called by the Anki add-on after successfully importing the card,
    but can also be called by the terminal if the user aborts.
    """
    print(f"[DEBUG] card_writer.clear_pending_card: removing {PENDING_CARD_PATH}")
    log.debug("Clearing pending card file: %s", PENDING_CARD_PATH)

    try:
        PENDING_CARD_PATH.unlink(missing_ok=True)
        print("[DEBUG] card_writer.clear_pending_card: file removed (or was absent)")
        log.info("Pending card file removed")
    except OSError as exc:
        print(f"[DEBUG] card_writer.clear_pending_card: could not remove file — {exc}")
        log.warning("Could not remove pending card file: %s", exc)


def read_pending_card() -> Optional[Dict]:
    """
    Read and parse the pending card file, if it exists.

    Used by the Anki add-on bridge (bridge.py) and can also be used
    by the terminal for verification.

    Returns:
        Parsed dict if the file exists and is valid JSON, else None.
    """
    print(f"[DEBUG] card_writer.read_pending_card: checking {PENDING_CARD_PATH}")
    log.debug("Reading pending card from: %s", PENDING_CARD_PATH)

    if not PENDING_CARD_PATH.exists():
        print("[DEBUG] card_writer.read_pending_card: file not found")
        return None

    try:
        text = PENDING_CARD_PATH.read_text(encoding="utf-8")
        data = json.loads(text)
        print(f"[DEBUG] card_writer.read_pending_card: loaded card for word='{data.get('word', '?')}'")
        log.info("Pending card loaded: word='%s' created_at='%s'",
                 data.get("word"), data.get("created_at"))
        return data
    except (OSError, json.JSONDecodeError) as exc:
        print(f"[DEBUG] card_writer.read_pending_card: error reading file — {exc}")
        log.error("Failed to read pending card: %s", exc)
        return None
