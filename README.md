<p align="center">
  <img src="extension/icons/icon128.png" width="96" alt="AJS icon" />
</p>

<h1 align="center">Anki Japanese Sensei</h1>
<p align="center"><em>Turn any Japanese YouTube video into Anki flashcards — one keypress, under 20 seconds.</em></p>

<p align="center">
  <a href="https://github.com/albazzaztariq/Anki-Browser-Plugin/releases/latest">
    <img src="https://img.shields.io/github/v/release/albazzaztariq/Anki-Browser-Plugin?label=download&color=c0392b" alt="Latest release" />
  </a>
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20macOS-lightgrey" alt="Platform" />
  <img src="https://img.shields.io/badge/AI-100%25%20offline-brightgreen" alt="Offline AI" />
  <img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT License" />
</p>

---

Never lose a word again. You're watching Japanese YouTube, something is said, you almost catch it — press **Ctrl+Shift+E** and have a finished Anki card with audio ready in under a minute.

---

## What It Does

1. Press **Ctrl+Shift+E** inside Anki while a YouTube video is open in your browser.
2. A terminal opens, fetches the video's subtitle track, and asks what word you heard.
3. Search for it — kanji, hiragana, or romaji all work.
4. Pick the sentence it appeared in for context.
5. The app looks up the word, generates an English definition, and synthesises a Japanese audio clip.
6. A finished card — word, reading, definition, example sentence, audio — drops straight into Anki.

---

## What You Need

| Requirement | Notes |
|-------------|-------|
| **Anki Desktop** | Version 23.x or later |
| **Chrome** | Firefox, Edge, and Safari coming soon |
| **AJS Tab Helper** extension | Installed automatically by the installer |
| **Internet connection** | Only needed for the audio synthesis step |

---

## Installation

Run the AJS installer included in this package. It will:

- Install the terminal pipeline to `%APPDATA%\AJS\` (Windows) or `~/.ajs/` (macOS)
- Copy the Anki add-on to your Anki add-ons folder automatically
- Load the AJS Tab Helper browser extension into Chrome

After installing, start Anki, open a YouTube video in your browser, and press **Ctrl+Shift+E**.

---

## How It Interacts With Your Computer

**The Anki add-on** runs quietly in the background whenever Anki is open. It listens on a local port (`localhost:27384`) — a private connection only your own machine can reach, never the internet.

**The browser extension** (AJS Tab Helper) sits in Chrome or Edge and does one job: when you press the shortcut, it tells the add-on which video tab is open. It never reads page content and never sends data anywhere except to your local Anki app.

**The terminal pipeline** runs only when you trigger it. It downloads subtitles via yt-dlp, processes them locally, and calls a locally-running AI model (Ollama) for the dictionary lookup. Your video data does not leave your machine.

**Audio synthesis** calls Microsoft's Edge TTS service over the internet to generate a natural-sounding Japanese audio clip. This is the only step that makes an outbound network call.

---

## Supported Browsers

| Browser | Status |
|---------|--------|
| Google Chrome | ✓ Supported |
| Microsoft Edge | 🔜 Coming soon |
| Firefox | 🔜 Coming soon |
| Safari | 🔜 Coming soon |

---

## Reporting a Problem

If something goes wrong, the app will ask whether you want to submit a bug report. Saying yes files a report automatically — you don't need to do anything else.

To report manually:

1. Go to: https://github.com/albazzaztariq/Anki-Browser-Plugin/issues
2. Click **New Issue**
3. Describe what you were doing when the problem occurred
4. If there is a crash report file in `~/.ajs/crash_reports/`, paste its contents into the issue

We aim to respond within a few days.

---

## Frequently Asked Questions

**The shortcut does nothing.**
Make sure Anki is open with a profile loaded. The shortcut is Ctrl+Shift+E.

**"No browser tabs found."**
Open your video in Chrome, go to `chrome://extensions`, find AJS Tab Helper, and click the reload button (↺). Then try the shortcut again.

**"Ollama is not running."**
The AI engine wasn't started automatically. Open the Ollama app from your system tray or Applications folder and try again. If it's not installed, re-run the AJS installer — it handles this.

**The word definition looks wrong.**
The AI model runs locally and occasionally makes mistakes on unusual words. You can edit any field directly in Anki after the card is imported.

**The video has no Japanese subtitles.**
You'll be asked to type an example sentence manually, or press Enter to let the AI generate one.

---

## Privacy

- No account required
- No data is sent to external servers except the audio synthesis step (Microsoft Edge TTS)
- The browser extension only ever communicates with your local Anki application
- Crash reports are only submitted if you explicitly approve them
