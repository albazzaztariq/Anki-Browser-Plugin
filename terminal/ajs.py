"""
AJS Terminal — ajs.py
Main entry point for the Anki Japanese Sensei terminal pipeline.

Full pipeline (steps match Section 7.1 of the SRS):
  1. Capture the active browser tab URL (url_capture)
  2. Fetch the Japanese video transcript (transcript)
  3. Prompt the user for the target word (fzf_menu.input_prompt) — FR-4
  4. Normalise Romaji to Hiragana (normalizer) — FR-5
  5. Show fzf transcript selection menu — FR-7 / FR-8
  6. Get dictionary entry from LLM (dictionary) — FR-6 / FR-9
  7. Synthesise audio (tts) — FR-11
  8. Write pending card file (card_writer)
  9. Print confirmation and exit

Error handling per spec:
  E-1  Ollama not running → clear message, exit
  E-3  No transcript → offer manual sentence entry
  E-4  Empty word input → reprompt
  E-5  TTS failure → continue without audio, warn user

Usage:
  python ajs.py [--url <url>]   # --url is optional; omit to auto-capture from browser
  python ajs.py --help
"""

import argparse
import os
import sys
import textwrap
import traceback
import unicodedata
from typing import Optional
from datetime import datetime, timezone
from pathlib import Path

print("[DEBUG] ajs.py: script starting")

# ---------------------------------------------------------------------------
# PyInstaller bundle PATH fix
# When ajs is frozen as a .exe, sys._MEIPASS holds the unpacked bundle dir.
# fzf.exe is placed there by the build, so we prepend it to PATH so that
# shutil.which("fzf") and subprocess calls both find it correctly.
# ---------------------------------------------------------------------------
if getattr(sys, 'frozen', False):
    bundle_dir = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    os.environ['PATH'] = str(bundle_dir) + os.pathsep + os.environ.get('PATH', '')
    print(f"[DEBUG] ajs.py: frozen exe, prepended bundle dir to PATH: {bundle_dir}")

# ---------------------------------------------------------------------------
# Import pipeline modules
# ---------------------------------------------------------------------------
try:
    from config import AUDIO_DIR, PENDING_CARD_PATH
    from logger import get_logger
    import url_capture
    import transcript as transcript_mod
    import normalizer
    import fzf_menu
    import dictionary as dictionary_mod
    import tts as tts_mod
    import card_writer
    import crash_reporter
    from llm import is_ollama_running
    print("[DEBUG] ajs.py: all pipeline modules imported successfully")
except ImportError as exc:
    print(f"[ERROR] ajs.py: Failed to import pipeline module — {exc}")
    print("        Make sure all dependencies are installed: pip install -r requirements.txt")
    sys.exit(1)

log = get_logger("ajs_main")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _print_banner() -> None:
    """Print a welcome banner."""
    print("\n" + "="*60)
    print("  ⚡ Anki Japanese Sensei (AJS) — Terminal Pipeline")
    print("="*60)
    print("  Help / Report a bug: https://github.com/albazzaztariq/Anki-Browser-Plugin/issues")
    print("  Press Esc at any time to exit.\n")


def _prompt_word() -> str:
    """
    Prompt the user for the target word.  Reprompts on empty input (E-4).

    Returns:
        Non-empty word string.
    """
    print("[DEBUG] ajs._prompt_word: prompting for word")
    while True:
        word = fzf_menu.input_prompt("Word to look up (romaji, hiragana, kanji — anything works)")
        if word.strip():
            print(f"[DEBUG] ajs._prompt_word: user entered '{word}'")
            log.info("User entered word: '%s'", word)
            return word.strip()
        print("\n[AJS] Word cannot be empty. Please try again. (Ctrl-C to quit)\n")
        log.warning("Empty word input — reprompting (E-4)")


def _show_nomatch_popup(query: str) -> None:
    """
    Show a 'no matches found' popup after the user pressed Enter with no results.
    Pressing any key (including Esc) dismisses it and returns to the caller
    so the fzf loop can reopen — the 'Press Escape Twice to Exit' means the
    second Esc is handled inside fzf itself (rc=130 → exit confirmation).
    """
    _show_popup(
        lines=[
            f"  '{query}' was not found in the transcript.",
            "",
            "  Press Escape Once To Go Back.",
            "  Press Escape Twice to Exit.",
        ],
        title="  \u26a0  No Matches Found",
        key_hint="",
    )


def _select_transcript_segment(segments: list[dict]) -> tuple[str, str]:
    """
    Open fzf with ALL transcript segments. The user types to filter live
    (every character updates the list in real time — fzf's native behaviour).
    Pressing Enter on a result is the final selection; no extra confirm step.

    Returns:
        (word_raw, context_sentence)
        word_raw        — the fzf query string the user typed (used as the word to look up).
        context_sentence — the full text of the selected segment.
        Both are empty strings ("", "") if the user exits without selecting.
    """
    print(f"[DEBUG] ajs._select_transcript_segment: {len(segments)} segments")
    log.debug("Selecting transcript segment from %d entries", len(segments))

    if not segments:
        return ("", "")

    def _char_width(ch: str) -> int:
        if unicodedata.east_asian_width(ch) in ("F", "W"):
            return 2
        return 1

    def _slice_by_display_width(text: str, width: int) -> list[str]:
        text = text.strip()
        if not text:
            return [""]

        chunks: list[str] = []
        current = ""
        current_width = 0

        for ch in text:
            ch_width = _char_width(ch)
            if current and current_width + ch_width > width:
                chunks.append(current)
                current = ch
                current_width = ch_width
            else:
                current += ch
                current_width += ch_width

        if current:
            chunks.append(current)
        return chunks

    def _split_segment_for_menu(seg: dict, width: int) -> list[tuple[str, str, str]]:
        text = seg["text"].replace("\n", " ").strip()
        raw_chunks = _slice_by_display_width(text, width)
        result: list[tuple[str, str, str]] = []
        for chunk in raw_chunks:
            chunk = chunk.strip()
            if not chunk:
                continue
            result.append((
                chunk,
                normalizer.get_reading(chunk).replace("\n", " ").strip(),
                normalizer.get_romaji(chunk).replace("\n", " ").strip(),
            ))
        return result or [(text, seg.get("kana", text), seg.get("romaji", text))]

    # Build multi-line display items:
    #   Line 1: [MM:SS] kanji text
    #   Line 2:         hiragana reading  (omitted if same as kanji)
    #   Line 3:         romaji            (omitted if empty / redundant)
    # Single-line items: "[MM:SS] kanji  /romaji/"
    # No NUL-delimited mode — avoids Windows pipe swallowing \x00 bytes.
    all_items: list[str] = []
    item_to_text: dict[str, str] = {}  # display line → clean kanji text
    # Be conservative: fzf's visible list area is narrower than the raw terminal.
    # A smaller fixed cap prevents visual wrapping/ellipsis in the picker.
    # fzf's actual visible list width is much narrower than the raw terminal width,
    # especially once borders and the preview gutter are accounted for.
    # Keep this conservative so one menu entry stays close to two visible JP lines.
    chunk_width = 18

    for seg in segments:
        ts = f"[{int(seg['start'] // 60):02d}:{int(seg['start'] % 60):02d}]"
        for kanji, kana, romaji in _split_segment_for_menu(seg, chunk_width):
            line1 = f"{ts} {kanji}"
            line2 = kana
            line3 = romaji or normalizer.get_romaji(kanji)
            item = "\n".join([line1, line2, line3])
            all_items.append(item)
            item_to_text[line1] = kanji

    header = (
        "Full transcript loaded  \u00b7  Type to filter live  \u00b7  Up/Down: select  \u00b7  Enter: choose  \u00b7  Esc: exit"
    )
    query = ""

    while True:
        query, selected, rc = fzf_menu.fzf_select_with_query(
            all_items,
            prompt="Search transcript",
            header=header,
            read0=True,
            initial_query=query,
        )

        if rc == 0 and selected:
            raw = selected[0].strip()
            first_line = raw.splitlines()[0] if raw else ""
            text = item_to_text.get(first_line, "")
            if not text:
                bracket_end = first_line.find("]")
                text = first_line[bracket_end + 1:].strip() if bracket_end != -1 else first_line

            word_raw = query.strip()
            print(f"[DEBUG] ajs._select_transcript_segment: selected text='{text[:80]}', query='{word_raw}'")
            log.info("Transcript segment selected: '%s' (query='%s')", text[:80], word_raw)
            return (word_raw, text)

        elif rc == 1:
            # No match — user pressed Enter but the list was empty.
            print(f"[DEBUG] ajs._select_transcript_segment: no match for query='{query}'")
            log.info("fzf no-match for query '%s' — showing popup", query)
            _show_nomatch_popup(query or "")
            # Loop — reopen fzf so user can try again.

        else:
            # rc == 130 — Esc / Ctrl-C (the "second Esc" the popup warned about).
            print("[DEBUG] ajs._select_transcript_segment: Esc — confirm exit")
            log.info("fzf escaped — showing exit confirmation")
            if _confirm_exit():
                print("\n[AJS] Goodbye.\n")
                sys.exit(0)
            # User chose not to exit — loop back, reopen fzf.


def _prompt_manual_sentence() -> str:
    """
    Prompt user to manually enter an example sentence (E-3 fallback).

    Returns:
        Sentence string (may be empty if user skips).
    """
    print("[DEBUG] ajs._prompt_manual_sentence: prompting for manual sentence")
    sentence = fzf_menu.input_prompt(
        "No transcript available. Enter a Japanese example sentence (or press Enter to skip)"
    )
    return sentence.strip()


def _confirm_card(card_data: dict) -> bool:
    """
    Show the assembled card fields to the user and ask for confirmation (FR-14).

    Returns:
        True if user confirms, False to abort.
    """
    print("\n" + "─"*60)
    print("  CARD PREVIEW")
    print("─"*60)
    print(f"  Word             : {card_data.get('word', '')}")
    print(f"  Reading          : {card_data.get('reading', '')}")
    print(f"  Part of speech   : {card_data.get('part_of_speech', '')}")
    print(f"  Definition (EN)  : {card_data.get('definition_en', '')}")
    print(f"  Example sentence : {card_data.get('example_sentence', '')}")
    audio = card_data.get('audio_path', '')
    print(f"  Audio            : {audio if audio else '(none)'}")
    print(f"  Source URL       : {card_data.get('source_url', '')[:80]}")
    print("─"*60)

    while True:
        try:
            choice = input("  Add this card? [y/n/q]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n[AJS] Aborted.")
            return False

        # Normalize full-width JP keyboard chars (ｙ→y, ｎ→n, ｑ→q etc.)
        choice = choice.translate(str.maketrans(
            "ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ"
            "ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ",
            "abcdefghijklmnopqrstuvwxyz"
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        ))
        if choice in ("y", "yes"):
            return True
        if choice in ("n", "no", "q", "quit"):
            return False
        print("  Please enter y (yes) or n/q (no/quit).")


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def _clear() -> None:
    """Clear the terminal screen."""
    os.system("cls" if sys.platform == "win32" else "clear")


def _show_popup(lines: list[str], title: str = "",
                key_hint: str = "Press any key to continue") -> None:
    """
    Clear the screen and draw a centred box popup, then wait for a keypress.
    Looks like a BIOS message box — clean, no surrounding debug noise.
    """
    import shutil
    _clear()

    cols = shutil.get_terminal_size((80, 24)).columns
    rows = shutil.get_terminal_size((80, 24)).lines

    content: list[str] = []
    if title:
        content.append(title)
        content.append("")
    content.extend(lines)
    content.append("")
    content.append(key_hint)

    inner_w  = min(max(len(l) for l in content) + 4, cols - 6)
    left_pad = " " * max(0, (cols - inner_w - 2) // 2)

    def _row(text: str = "") -> str:
        return left_pad + "│  " + text[: inner_w - 4].ljust(inner_w - 4) + "  │"

    box_lines = (
        [left_pad + "┌" + "─" * inner_w + "┐",
         _row()]
        + [_row(l) for l in content]
        + [_row(), left_pad + "└" + "─" * inner_w + "┘"]
    )

    top_pad = max(0, (rows - len(box_lines)) // 2)
    print("\n" * top_pad, end="")
    print("\n".join(box_lines))
    _getch()


def _confirm_exit() -> bool:
    """
    Show an exit-confirmation popup.
    Returns True if the user confirms they want to quit, False to resume.
    """
    _clear()
    import shutil
    cols = shutil.get_terminal_size((80, 24)).columns
    rows = shutil.get_terminal_size((80, 24)).lines

    box_lines = [
        "",
        "  Exit Anki Japanese Sensei?",
        "",
        "  Your progress will not be saved.",
        "",
        "  [ Enter ]  Yes, exit",
        "  [ Any other key ]  Cancel — go back",
        "",
    ]
    inner_w  = min(max(len(l) for l in box_lines) + 2, cols - 6)
    left_pad = " " * max(0, (cols - inner_w - 2) // 2)

    def _row(text: str = "") -> str:
        return left_pad + "│" + text[: inner_w].ljust(inner_w) + "│"

    rendered = (
        [left_pad + "┌" + "─" * inner_w + "┐"]
        + [_row(l) for l in box_lines]
        + [left_pad + "└" + "─" * inner_w + "┘"]
    )
    top_pad = max(0, (rows - len(rendered)) // 2)
    print("\n" * top_pad, end="")
    print("\n".join(rendered))

    try:
        key = _getch()
    except (EOFError, KeyboardInterrupt):
        key = "\r"
    return key in ("\r", "\n")


def _getch() -> str:
    """Read a single keypress without requiring Enter. Cross-platform."""
    if sys.platform == "win32":
        import msvcrt
        ch = msvcrt.getwch()
        # Arrow keys / special keys send 0x00 or 0xe0 followed by a second byte — consume it.
        if ch in ("\x00", "\xe0"):
            msvcrt.getwch()
            return ""
        return ch
    else:
        import tty, termios
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            return sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _confirm_quit() -> bool:
    """Ask the user to confirm they want to quit. Returns True if they do."""
    try:
        answer = input("\n  Really quit? [y/n]: ").strip().lower()
        return answer in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        return True


def run(url_override: Optional[str] = None) -> None:
    """
    Execute the full AJS terminal pipeline.

    Args:
        url_override: If provided, skip browser URL capture and use this URL.
    """
    try:
        _run(url_override)
    except KeyboardInterrupt:
        if _confirm_quit():
            print("\n[AJS] Goodbye.\n")
            sys.exit(0)
        else:
            print("[AJS] Resuming...\n")
            _run(url_override)


def _run(url_override: Optional[str] = None) -> None:
    print("[DEBUG] ajs.run: pipeline starting")
    log.info("AJS pipeline starting")
    _print_banner()

    # ── Step E-1: Ensure Ollama is running — auto-start if needed.
    print("[DEBUG] ajs.run: checking Ollama availability")
    print("[AJS] Checking local LLM (Ollama)...", flush=True)
    if not is_ollama_running():
        print("[AJS] Ollama not running — attempting to start it...", flush=True)
        log.info("Ollama not running — attempting auto-start")
        import subprocess as _sp, platform as _platform
        try:
            if _platform.system() == "Windows":
                # Start Ollama app minimised; it registers itself as a system-tray service
                _sp.Popen(
                    ["ollama", "serve"],
                    creationflags=_sp.CREATE_NO_WINDOW,
                    stdout=_sp.DEVNULL,
                    stderr=_sp.DEVNULL,
                )
            else:
                # macOS / Linux
                _sp.Popen(
                    ["ollama", "serve"],
                    stdout=_sp.DEVNULL,
                    stderr=_sp.DEVNULL,
                    start_new_session=True,
                )
        except FileNotFoundError:
            print("\n[AJS ERROR] Ollama is not installed or not on PATH.")
            print("            Install it from https://ollama.com then re-run AJS.\n")
            log.error("Ollama binary not found — cannot auto-start (E-1)")
            sys.exit(1)

        # Wait up to 30 s for Ollama to become ready
        import time as _time
        print("[AJS] Waiting for Ollama to start", end="", flush=True)
        for _ in range(30):
            _time.sleep(1)
            print(".", end="", flush=True)
            if is_ollama_running():
                break
        print()

        if not is_ollama_running():
            print("\n[AJS ERROR] Ollama did not start within 30 seconds.")
            print("            Start it manually from the system tray or Applications,")
            print("            then try again.\n")
            log.error("Ollama failed to start within 30s (E-1)")
            sys.exit(1)

        print("[AJS] Ollama started.\n")
        log.info("Ollama auto-started successfully")
    else:
        print("[AJS] Ollama is running.\n")
    print("[DEBUG] ajs.run: Ollama confirmed running")

    # ── Step 1: URL capture.
    if url_override:
        url = url_override.strip()
        print(f"[DEBUG] ajs.run: using URL override: {url}")
        log.info("Using URL override: %s", url)
    else:
        print("[AJS] Capturing browser URL...", flush=True)
        url = url_capture.get_url()

    print(f"[AJS] Video URL: {url}\n")

    # ── Step 2: Transcript fetch.
    print("[AJS] Fetching Japanese transcript (this may take a few seconds)...", flush=True)
    print("[DEBUG] ajs.run: fetching transcript")
    segments = transcript_mod.fetch_transcript(url)

    has_transcript = bool(segments)
    if has_transcript:
        print(f"[AJS] Transcript loaded: {len(segments)} segments.\n")
        print(f"[DEBUG] ajs.run: {len(segments)} transcript segments loaded")
    else:
        print("[AJS] No Japanese transcript found for this video.")
        print("      You will be asked to enter the example sentence manually.\n")
        print("[DEBUG] ajs.run: no transcript — E-3 fallback path")
        log.info("No transcript found — E-3 fallback")

    # ── Step 3 + 5: Word search & transcript context selection.
    # When a transcript is available, fzf is the single input step:
    #   • user types → list filters live (every character is a query)
    #   • Enter selects a segment — no extra confirmation step
    #   • The fzf query string becomes the word to look up
    # When there is no transcript, fall back to a plain word prompt + manual sentence.
    if has_transcript:
        print("[AJS] Search the transcript for the word you heard:\n")
        word_raw, context_sentence = _select_transcript_segment(segments)
        # word_raw is the fzf query; if the user selected without typing,
        # prompt them for the word separately.
        if not word_raw.strip():
            print("[AJS] No search term typed — please enter the word to look up:")
            word_raw = _prompt_word()
    else:
        # E-3: no transcript — ask for word then manual sentence.
        print("[AJS] — — — — — — — — — — — — — —")
        word_raw = _prompt_word()
        context_sentence = _prompt_manual_sentence()
        if not context_sentence:
            print("[AJS] No example sentence provided — LLM will generate one.\n")

    crash_reporter.log_event("word_entered", word_raw)

    # ── Step 4: Normalise input — hiragana reading + romaji (FR-5).
    print("[DEBUG] ajs.run: normalising word")
    reading_from_input = normalizer.get_reading(word_raw)
    romaji_from_input  = normalizer.get_romaji(word_raw)
    crash_reporter.log_event("word_normalised", f"reading={reading_from_input} romaji={romaji_from_input}")
    print(f"[AJS] Reading: {reading_from_input}  ({romaji_from_input})\n")

    crash_reporter.log_event("context_selected", context_sentence[:100])
    print(f"[DEBUG] ajs.run: context_sentence='{context_sentence[:80]}'")

    # ── Step 6: LLM dictionary lookup (FR-6 / FR-9 / FR-10).
    print("\n[AJS] Looking up word in dictionary (LLM)...", flush=True)
    print("[DEBUG] ajs.run: calling dictionary.get_definition")
    try:
        entry = dictionary_mod.get_definition(reading_from_input, context_sentence)
    except RuntimeError as exc:
        print(f"\n[AJS ERROR] {exc}\n")
        log.error("Dictionary lookup failed: %s", exc)
        sys.exit(1)

    crash_reporter.log_event("llm_success", f"word={entry.get('word')} reading={entry.get('reading')}")
    print(f"[DEBUG] ajs.run: dictionary entry retrieved: {entry}")
    print(f"[AJS] Entry: {entry['word']} ({entry['reading']}) — {entry['definition_en'][:60]}\n")

    # ── Step 7: TTS audio synthesis (FR-11 / E-5).
    audio_path_str = ""
    sentence_for_tts = entry.get("example_sentence", "") or context_sentence

    if sentence_for_tts:
        print("[AJS] Synthesising audio (requires internet)...", flush=True)
        print("[DEBUG] ajs.run: calling tts.synthesize")
        audio_file = tts_mod.make_audio_path(entry["word"])
        try:
            tts_mod.synthesize(sentence_for_tts, audio_file)
            audio_path_str = str(audio_file)
            print(f"[AJS] Audio saved: {audio_file.name}\n")
            print(f"[DEBUG] ajs.run: audio saved to {audio_file}")
        except RuntimeError as exc:
            # E-5: TTS failed — continue without audio.
            print(f"\n[AJS WARNING] {exc}\n")
            print("[AJS] Continuing — card will be added without audio.\n")
            log.warning("TTS failed (E-5): %s", exc)
    else:
        print("[AJS] No sentence available for TTS — skipping audio.\n")
        print("[DEBUG] ajs.run: no sentence for TTS")

    # ── Step 8: Assemble and write pending card.
    word_final = entry.get("word", reading_from_input)
    card_data = {
        "word":             word_final,
        "reading":          entry.get("reading", reading_from_input),
        "romaji":           normalizer.get_romaji(word_final) or romaji_from_input,
        "definition_en":    entry.get("definition_en", ""),
        "example_sentence": entry.get("example_sentence", context_sentence),
        "part_of_speech":   entry.get("part_of_speech", ""),
        "audio_path":       audio_path_str,
        "source_url":       url,
        "created_at":       datetime.now(timezone.utc).isoformat(),
    }

    print("[DEBUG] ajs.run: assembled card_data")
    log.debug("Card data assembled: %s", card_data)

    # ── Step FR-14: Editable preview & confirmation.
    confirmed = _confirm_card(card_data)
    crash_reporter.log_event("card_confirm", "accepted" if confirmed else "rejected")
    if not confirmed:
        print("\n[AJS] Card creation aborted. Nothing was written to Anki.\n")
        log.info("User aborted card creation at preview step")
        sys.exit(0)

    print("\n[DEBUG] ajs.run: writing pending card")
    try:
        card_writer.write_pending_card(card_data)
    except (ValueError, OSError) as exc:
        print(f"\n[AJS ERROR] Could not write pending card: {exc}\n")
        log.error("card_writer failed: %s", exc)
        sys.exit(1)

    # ── Done.
    print("\n" + "="*60)
    print("  Card queued — open Anki to review and add.")
    print(f"  Word: {card_data['word']} ({card_data['reading']})")
    print("="*60 + "\n")
    print("[DEBUG] ajs.run: pipeline complete")
    log.info("Pipeline complete. Card queued for: '%s'", card_data["word"])


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="ajs",
        description="Anki Japanese Sensei — capture a Japanese word from a YouTube video and queue it as an Anki card.",
    )
    parser.add_argument(
        "--url",
        metavar="URL",
        default=None,
        help="YouTube video URL (if omitted, AJS will capture it from the active browser tab).",
    )
    args = parser.parse_args()

    try:
        run(url_override=args.url)
    except KeyboardInterrupt:
        print("\n[AJS] Pipeline interrupted by user. Goodbye.\n")
        log.info("Pipeline interrupted by user")
        sys.exit(0)
    except Exception as exc:
        print(f"\n[AJS FATAL ERROR] An unexpected error occurred:\n  {exc}\n")
        traceback.print_exc()
        log.exception("Unhandled exception in AJS pipeline: %s", exc)
        crash_reporter.file_report(sys.exc_info(), ask_user=True)
        sys.exit(1)


if __name__ == "__main__":
    print("[DEBUG] ajs.py: __main__ block entered")
    main()
