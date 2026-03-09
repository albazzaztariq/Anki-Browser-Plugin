# AnkiWeb Add-on Listing
## Anki Japanese Sensei (AJS)

> Paste the content below into the AnkiWeb submission description field.
> Screenshots to capture are marked with **[SCREENSHOT: ...]** — see bottom of file.

---

## LISTING TEXT (copy-paste to AnkiWeb)

---

**Turn any Japanese YouTube video into Anki flashcards in under 60 seconds — no copy-paste, no tab-switching, no typing.**

Anki Japanese Sensei (AJS) watches any Japanese YouTube video alongside you. The moment you hear a word or phrase you want to learn, press **Ctrl+Shift+E**. A fuzzy-search picker instantly appears showing every subtitle segment from the video — search in romaji, hiragana, or kanji. Pick your segment, and AJS automatically:

- Looks up the word with a local AI (runs 100% offline, no API key needed)
- Generates a full dictionary entry: reading, meaning, part of speech, example sentences
- Creates a beautifully formatted Anki card with native audio (Azure TTS)
- Adds it directly to your deck — you never leave Anki

**Every step is keyboard-only. No mouse. No copy-paste. No internet required after setup.**

---

## How It Works

**Step 1 — Watch any Japanese YouTube video**
Open Chrome or Edge and watch normally. AJS runs silently in the background.

**Step 2 — Hear something interesting? Press Ctrl+Shift+E**
A terminal window pops up with a fuzzy-search list of every subtitle segment from the video. The list shows kanji, hiragana reading, and romaji on three separate lines — so you can search however you think.

**Step 3 — Search and select**
Type any part of the word in romaji, hiragana, or kanji. The list filters in real time. Press Enter to select, Escape to go back.

**Step 4 — Confirm your word**
AJS extracts the exact word from the segment and shows you a confirmation step before looking it up. Press Enter to proceed, Escape to re-search.

**Step 5 — AI generates the card (offline)**
A local AI model (Ollama + qwen2.5:3b, runs on your machine) builds the dictionary entry. A spinner shows while it thinks — typically 5–15 seconds.

**Step 6 — Preview and approve**
The full card preview appears: front side (kanji + reading), back side (meaning, part of speech, JLPT level, example sentences with English translation, native audio). Press Enter to add to Anki, Escape to discard.

**Step 7 — Done. Card added.**
The card appears in your chosen Anki deck immediately, ready for your next review session.

---

## Features

- **Offline AI** — Uses Ollama running locally. No data leaves your machine. No API key. No subscription.
- **Native audio** — Azure TTS (ja-JP-NanamiNeural voice) generates natural-sounding audio for every card. Falls back gracefully if unavailable.
- **Romaji/hiragana/kanji search** — Fuzzy-search any subtitle segment by how you know it, not how it's written.
- **True multi-line fzf display** — Each subtitle entry shows kanji on line 1, hiragana on line 2, romaji on line 3. No parenthetical clutter.
- **Keyboard-first UX** — Every prompt is Enter to confirm / Escape to go back. No y/n. No mouse required.
- **Crash reporter** — If something goes wrong, one keypress files a detailed bug report directly to GitHub.
- **Works while Anki is closed** — Cards queue in a pending file and import the moment you open Anki.
- **Automatic LLM retry** — Exponential backoff on timeouts; connection errors fail fast with a clear message.

---

## Requirements

| Component | Details |
|-----------|---------|
| **Anki** | 2.1.55 or newer (Qt6 build recommended) |
| **Chrome or Edge** | Any recent version |
| **Ollama** | Free, runs locally — ollama.com |
| **AI Model** | qwen2.5:3b (auto-downloaded on first run, ~2 GB) |
| **Python** | 3.11+ (Windows: bundled in installer) |
| **fzf** | Optional but recommended — fuzzy search UI |
| **OS** | Windows 10/11, macOS 13+ |

---

## Installation

1. **Download** the installer from [GitHub Releases](https://github.com/albazzaztariq/Anki-Browser-Plugin/releases)
2. **Run the installer** — sets up Python, dependencies, and the Anki add-on automatically
3. **Install Ollama** from [ollama.com](https://ollama.com) and run: `ollama pull qwen2.5:3b`
4. **Load the browser extension** — drag the `extension/` folder into Chrome's extension page (developer mode)
5. **Open Anki** and look for the **Japanese Sensei** menu item under Tools
6. Start watching Japanese YouTube and press **Ctrl+Shift+E**

Full setup guide: [README on GitHub](https://github.com/albazzaztariq/Anki-Browser-Plugin)

---

## Privacy

- No data is sent to any server. The AI runs 100% locally on your machine via Ollama.
- The browser extension only reads YouTube subtitle data from the active tab.
- Audio is generated via Azure TTS (Microsoft) — only the word/phrase text is sent, no personal data.
- Crash reports are opt-in — you must press Enter to submit. Nothing is sent automatically.

---

## Source Code & Support

- **GitHub:** https://github.com/albazzaztariq/Anki-Browser-Plugin
- **Issues / Bug Reports:** Use the built-in crash reporter (press Enter when prompted) or open a GitHub issue directly
- **Developer:** albazzaztariq

---

## Tags (for AnkiWeb search)

japanese, japanese learning, vocabulary, kanji, hiragana, JLPT, AI, automation, YouTube, subtitles, flashcards, offline AI, local LLM, Ollama, TTS, audio, sentence mining, immersion, input method

---
---

# SCREENSHOTS NEEDED
## Capture these in order for the walkthrough

The AnkiWeb listing supports up to 5 screenshots. Recommended set:

### Screenshot 1 — YouTube Video + Extension Active
**What to show:** Chrome with a Japanese YouTube video playing. The extension icon should be visible in the toolbar.
**How:** Open any Japanese YouTube video (NHK, anime, vlog, etc.) and take a full browser screenshot.
**File:** `docs/screenshots/01_youtube_video.png`

### Screenshot 2 — fzf Segment Picker
**What to show:** The terminal window with the fzf fuzzy picker open showing subtitle segments.
Each entry should show 3 lines: kanji / hiragana / romaji.
The prompt should read something like "Select segment > " with a search term typed in.
**How:** Run `python ajs.py` on a Japanese YouTube URL, press Ctrl+Shift+E, and screenshot the terminal.
**File:** `docs/screenshots/02_fzf_picker.png`

### Screenshot 3 — AI Processing + Spinner
**What to show:** Terminal showing "Looking up 勉強する..." with the dots spinner in progress.
**How:** Capture during the 5-15s LLM processing window.
**File:** `docs/screenshots/03_ai_processing.png`

### Screenshot 4 — Card Preview
**What to show:** The full card preview in the terminal:
  - Front: kanji + reading
  - Back: meaning, part of speech, JLPT level, example sentences with translation
  - "[Enter] Add to Anki  [Esc] Discard" prompt at the bottom
**How:** Complete the word lookup and screenshot the preview before pressing Enter.
**File:** `docs/screenshots/04_card_preview.png`

### Screenshot 5 — Anki Card in Browser
**What to show:** The Anki card browser showing the newly added card with the audio icon.
**How:** After adding a card, open Anki's card browser (Ctrl+Shift+B) and screenshot the card.
**File:** `docs/screenshots/05_anki_card.png`

---

## MOCKUP — fzf picker (for reference / placeholder)

This is what Screenshot 2 should look like:

```
╭─────────────────────────────────────────────────────────╮
│  Select segment > べん                                   │
│ ──────────────────────────────────────────────────────  │
│  [02:14] 勉強することが大切だと思います                      │
│          べんきょうすることがたいせつだとおもいます             │
│          benkyou suru koto ga taisetsu da to omoimasu   │
│                                                          │
│  [00:47] 勉強は毎日続けることが重要です                       │
│          べんきょうはまいにちつづけることがじゅうようです        │
│          benkyou ha mainichi tsuzukeru koto ga...        │
│                                                          │
│  [05:31] 勉強会に参加してみてください                         │
│          べんきょうかいにさんかしてみてください               │
│          benkyoukai ni sanka shite mite kudasai          │
│                                                          │
│  Esc: Exit AJS                    3/47 results           │
╰─────────────────────────────────────────────────────────╯
```

## MOCKUP — Card Preview (for reference / placeholder)

```
╭──────────────────────────────────────────────────────────╮
│                      CARD PREVIEW                        │
│                                                          │
│  FRONT                                                   │
│  ─────────────────────────────────────────────────       │
│  勉強する　　べんきょうする                               │
│                                                          │
│  BACK                                                    │
│  ─────────────────────────────────────────────────       │
│  to study; to work hard at learning                      │
│                                                          │
│  【Part of speech】 verb (する-verb)                      │
│  【JLPT】 N5                                             │
│                                                          │
│  Example:                                                │
│  毎日日本語を勉強しています。                               │
│  Mainichi nihongo wo benkyou shite imasu.                │
│  "I study Japanese every day."                           │
│                                                          │
│  🔊 Audio: ja-JP-NanamiNeural                            │
│                                                          │
│  [Enter] Add to Anki              [Esc] Discard          │
╰──────────────────────────────────────────────────────────╯
```
