"""
AJS Anki Add-on — config.py
Configuration constants for the ajs_addon Anki plugin layer.

These settings must remain compatible with Anki's bundled Python environment.
Only stdlib and packages already bundled with Anki should be imported here.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# IPC — must match terminal/config.py PENDING_CARD_PATH
# ---------------------------------------------------------------------------
PENDING_CARD_PATH: Path = Path.home() / ".ajs" / "pending_card.json"

# ---------------------------------------------------------------------------
# Anki note type and deck
# ---------------------------------------------------------------------------
# Primary note type name.  If "Japanese" exists in the collection, use it;
# otherwise fall back to "Basic".  The bridge will create the AJS note type
# if neither "Japanese" nor "Basic" is available.
NOTE_TYPE_PREFERRED: str = "Japanese"
NOTE_TYPE_FALLBACK: str = "Basic"

# Target deck name.  A deck named "AJS::Japanese" will be created if absent.
DECK_NAME: str = "AJS::Japanese"

# ---------------------------------------------------------------------------
# QTimer polling interval
# ---------------------------------------------------------------------------
# How often (in milliseconds) the add-on checks for a pending card file.
TIMER_INTERVAL_MS: int = 2000

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_DIR: Path = Path.home() / ".ajs"
LOG_FILE: Path = LOG_DIR / "anki_addon.log"
LOG_MAX_BYTES: int = 5 * 1024 * 1024
LOG_BACKUP_COUNT: int = 3

# ---------------------------------------------------------------------------
# Anki media directory (resolved at runtime in bridge.py via mw.col.media.dir())
# This constant is a fallback only — prefer mw.col.media.dir() when available.
# ---------------------------------------------------------------------------
ANKI_MEDIA_FALLBACK: Path = Path.home() / "Anki2" / "User 1" / "collection.media"
