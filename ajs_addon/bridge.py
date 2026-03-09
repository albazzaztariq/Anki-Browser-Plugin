"""
AJS Anki Add-on — bridge.py
Bridges the terminal pipeline output and the Anki collection.

Responsibilities:
  - check_pending()  : Called by a QTimer every TIMER_INTERVAL_MS ms.
                       Reads pending_card.json, shows the preview dialog,
                       and — on user confirmation — commits the note to Anki.
  - _ensure_deck()   : Creates the AJS::Japanese deck if it does not exist.
  - _ensure_notetype(): Returns the best available note type (Japanese > Basic > AJS Basic).
  - _copy_audio()    : Moves the MP3 file into Anki's collection.media directory.

Uses the modern Anki Python API (Anki 23.x+):
    note = mw.col.new_note(notetype)
    note["Front"] = ...
    mw.col.add_note(note, deck_id)

All blocking operations (this module runs on the Qt main thread inside a QTimer
callback) are intentionally lightweight — only file I/O and Anki API calls.
Heavy work (LLM, TTS) is done by the terminal pipeline, not here.
"""

import json
import shutil
import sys
from pathlib import Path

from .config import (
    PENDING_CARD_PATH,
    DECK_NAME,
    NOTE_TYPE_PREFERRED,
    NOTE_TYPE_FALLBACK,
)
from .logger import get_logger

log = get_logger("bridge")


# ---------------------------------------------------------------------------
# Anki API helpers
# ---------------------------------------------------------------------------

def _get_mw():
    """
    Import and return Anki's main window object (mw).
    Deferred import so the module can be imported outside Anki for testing.
    """
    try:
        from aqt import mw  # type: ignore
        return mw
    except ImportError:
        log.error("aqt not available — bridge can only run inside Anki")
        return None


def _ensure_deck(mw) -> int:
    """
    Return the deck ID for DECK_NAME, creating the deck if it does not exist.

    Args:
        mw: Anki main window object.

    Returns:
        int — deck ID.
    """
    log.debug("Ensuring deck exists: '%s'", DECK_NAME)

    deck_id = mw.col.decks.id(DECK_NAME, create=True)
    log.info("Deck '%s' id=%s", DECK_NAME, deck_id)
    return deck_id


def _ensure_notetype(mw):
    """
    Return the best available Anki note type for Japanese vocabulary cards.

    Priority:
      1. "Japanese"  — user may have a custom Japanese note type
      2. "Basic"     — Anki's built-in type (always present)
      3. Create a minimal "AJS Basic" type with the required fields as fallback

    Args:
        mw: Anki main window object.

    Returns:
        Anki notetype dict-like object.
    """
    log.debug("Finding note type — preferred='%s' fallback='%s'",
              NOTE_TYPE_PREFERRED, NOTE_TYPE_FALLBACK)

    models = mw.col.models

    for name in (NOTE_TYPE_PREFERRED, NOTE_TYPE_FALLBACK):
        nt = models.by_name(name)
        if nt:
            log.info("Using note type: '%s'", name)
            return nt

    # Neither found — create a minimal AJS note type.
    log.info("Creating AJS Basic note type")
    nt = models.new("AJS Basic")
    for field_name in ("Front", "Back"):
        field = models.new_field(field_name)
        models.add_field(nt, field)
    tmpl = models.new_template("Card 1")
    tmpl["qfmt"] = "{{Front}}"
    tmpl["afmt"] = "{{FrontSide}}<hr id=answer>{{Back}}"
    models.add_template(nt, tmpl)
    models.add(nt)
    return nt


def _build_front(card_data: dict) -> str:
    """
    Build the Front field content from card data.
    Format: <word> (<reading>)
    """
    word = card_data.get("word", "")
    reading = card_data.get("reading", "")
    if reading and reading != word:
        return f"{word}　【{reading}】"
    return word


def _build_back(card_data: dict, audio_anki_name: str) -> str:
    """
    Build the Back field content from card data.
    Includes definition, example sentence, audio tag, and source.
    """
    lines = []

    pos = card_data.get("part_of_speech", "")
    if pos:
        lines.append(f"<i>{pos}</i>")

    defn = card_data.get("definition_en", "")
    if defn:
        lines.append(f"<b>{defn}</b>")

    sentence = card_data.get("example_sentence", "")
    if sentence:
        lines.append(f"<br>{sentence}")

    if audio_anki_name:
        lines.append(f"[sound:{audio_anki_name}]")

    source = card_data.get("source_url", "")
    if source:
        lines.append(f'<br><small><a href="{source}">{source[:60]}…</a></small>')

    return "<br>".join(lines)


def _copy_audio_to_media(mw, audio_path_str: str) -> str:
    """
    Copy the MP3 file into Anki's collection.media directory.

    Returns:
        The filename (not full path) to use in the [sound:...] tag.
        Returns "" if audio_path_str is empty or the file does not exist.
    """
    log.debug("Copying audio: '%s'", audio_path_str)

    if not audio_path_str:
        return ""

    src = Path(audio_path_str)
    if not src.exists():
        log.warning("Audio source file not found: %s", src)
        return ""

    try:
        media_dir = Path(mw.col.media.dir())
    except Exception as exc:
        log.error("Cannot get Anki media dir: %s", exc)
        return ""

    dest = media_dir / src.name
    try:
        shutil.copy2(str(src), str(dest))
        log.info("Audio copied to media dir: %s", dest.name)
        return src.name
    except OSError as exc:
        log.error("Failed to copy audio to media: %s", exc)
        return ""


def _add_note_to_collection(mw, card_data: dict) -> bool:
    """
    Create and persist an Anki note from card_data using the modern Anki API.

    Field mapping (FR-12):
      Front = word + reading
      Back  = definition + example sentence + audio + source URL

    Args:
        mw:        Anki main window.
        card_data: Dict from pending_card.json.

    Returns:
        True on success, False on failure.
    """
    log.info("Adding note to collection: word='%s'", card_data.get("word"))

    try:
        deck_id = _ensure_deck(mw)
        notetype = _ensure_notetype(mw)

        # Copy audio to Anki media folder (FR-13).
        audio_anki_name = _copy_audio_to_media(mw, card_data.get("audio_path", ""))

        # Build field content.
        front = _build_front(card_data)
        back = _build_back(card_data, audio_anki_name)

        log.debug("Front='%s' Back='%s'", front[:80], back[:80])

        # Create the note using the modern Anki API.
        note = mw.col.new_note(notetype)

        # Assign fields — handle both "Front"/"Back" naming and custom field names.
        field_names = [f["name"] for f in notetype["flds"]]
        log.debug("Note type fields: %s", field_names)

        if len(field_names) >= 2:
            note[field_names[0]] = front
            note[field_names[1]] = back
        elif len(field_names) == 1:
            note[field_names[0]] = f"{front}\n\n{back}"
        else:
            log.error("Note type has no fields!")
            return False

        # Add note to the collection.
        mw.col.add_note(note, deck_id)
        mw.col.save()

        log.info("Note added successfully: id=%s word='%s'", note.id, card_data.get("word"))

        # Refresh the Anki card browser / main window.
        try:
            mw.reset()
        except Exception:
            pass

        return True

    except Exception as exc:
        log.exception("Failed to add note: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Public API — called by QTimer in __init__.py
# ---------------------------------------------------------------------------

def check_pending() -> None:
    """
    Check for a pending card file and, if found, show the preview dialog.

    This function is called every TIMER_INTERVAL_MS milliseconds from the
    QTimer in __init__.py.  It must complete quickly and never block.

    Flow:
      1. Check if PENDING_CARD_PATH exists.
      2. If yes: read it, show PreviewDialog.
      3. If user clicks "Add Card": commit note, delete pending file.
      4. If user clicks "Skip": delete pending file without adding.
    """
    # Poll is silent — only log when a card is actually found.

    if not PENDING_CARD_PATH.exists():
        return  # Nothing to do — most common path.

    log.info("Pending card file detected: %s", PENDING_CARD_PATH)

    # Read the card data.
    try:
        raw = PENDING_CARD_PATH.read_text(encoding="utf-8")
        card_data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        log.error("Could not read pending card file: %s", exc)
        # Remove corrupted file to avoid infinite error loop.
        try:
            PENDING_CARD_PATH.unlink(missing_ok=True)
        except OSError:
            pass
        return

    log.info("Card data loaded: word='%s'", card_data.get("word"))

    # Immediately remove the pending file to prevent re-triggering while the
    # dialog is open.
    try:
        PENDING_CARD_PATH.unlink(missing_ok=True)
        log.debug("Pending card file removed")
    except OSError as exc:
        log.warning("Could not remove pending card file: %s", exc)

    # Show the preview dialog on the Qt main thread.
    mw = _get_mw()
    if mw is None:
        log.error("mw is None — cannot show dialog")
        return

    try:
        from .ui.preview import PreviewDialog  # type: ignore
        dialog = PreviewDialog(card_data, parent=mw)
        result = dialog.exec()

        log.debug("PreviewDialog result=%d", result)

        if result == PreviewDialog.Accepted:
            # Get the (possibly edited) card data from the dialog.
            edited_card = dialog.get_card_data()
            log.info("User confirmed card — adding to collection")

            success = _add_note_to_collection(mw, edited_card)

            if success:
                from aqt.utils import showInfo  # type: ignore
                showInfo(
                    f"Card added successfully!\n\n"
                    f"Word: {edited_card.get('word', '')} ({edited_card.get('reading', '')})\n"
                    f"Deck: {DECK_NAME}"
                )
            else:
                from aqt.utils import showWarning  # type: ignore
                showWarning(
                    "[AJS] Failed to add card to Anki.\n"
                    "Check the AJS log at ~/.ajs/anki_addon.log for details."
                )

        else:
            log.info("User skipped card: word='%s'", card_data.get("word"))

    except Exception as exc:
        log.exception("Unexpected error in check_pending: %s", exc)
        try:
            from aqt.utils import showWarning  # type: ignore
            showWarning(f"[AJS] Error processing pending card:\n{exc}")
        except Exception:
            pass
