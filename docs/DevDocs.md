# AJS — Developer Documentation

**Project:** Japanese — YouTube Audio Clip Generator (codename: Anki Japanese Sensei / AJS)
**Author:** albazzaztariq — https://github.com/albazzaztariq
**Repository:** https://github.com/albazzaztariq/Anki-Browser-Plugin
**Contact / Hire:** Open an issue on the repository above or reach out via GitHub profile.

---

## 1. Problem Statement

Japanese learners watching authentic content — YouTube videos, streams, anime — frequently hear words or phrases they cannot catch fast enough to write down. By the time they pause the video, open a dictionary, look up the word, find an example sentence, record audio, and manually create an Anki card, the moment is gone and the friction defeats the habit.

**AJS eliminates that friction.** One keyboard shortcut triggers the entire pipeline: the video's subtitle track is fetched, the user searches for the word they heard, picks the sentence it appeared in, and a complete Anki card — kanji, hiragana reading, English definition, contextual example sentence, and synthesised audio — is created and imported automatically.

Secondary problems solved:
- Subtitle tracks are fragmented into display-timed chunks, not linguistic sentences. AJS merges them at punctuation and silence boundaries.
- Japanese text comes in multiple scripts (kanji, hiragana, katakana, romaji). AJS normalises all forms so searching works regardless of what the user types.
- Local LLM inference keeps dictionary lookups private, fast, and free after initial setup.

---

## 2. Architecture Overview

AJS is composed of three loosely-coupled components that communicate over the local machine only:

```
┌─────────────────────────┐       localhost:27384        ┌──────────────────────────┐
│   Anki Add-on           │ ◄────────────────────────── │  Chrome / Edge Extension  │
│   (ajs_addon/)          │   HTTP POST /tabs            │  (extension/)             │
│                         │   GET  /ping                 │  background.js polls      │
│  - QTimer polls for     │                              │  every 200ms              │
│    pending_card.json    │                              └──────────────────────────┘
│  - HTTPServer thread    │
│  - Qt menu / shortcut   │
└────────────┬────────────┘
             │  subprocess  (cmd /c  or  osascript)
             ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│   Terminal Pipeline  (terminal/)                                            │
│                                                                             │
│   ajs.py ──► transcript.py ──► normalizer.py ──► fzf (fuzzy search)        │
│          ──► dictionary.py ──► llm.py ──► Ollama (localhost:11434)          │
│          ──► tts.py (edge-tts, internet) ──► card_writer.py                 │
│                                                                             │
│   Output: ~/.ajs/pending_card.json                                          │
└─────────────────────────────────────────────────────────────────────────────┘
             │  filesystem polling (QTimer, 500ms)
             ▼
┌─────────────────────────┐
│   Anki Add-on           │
│   bridge.py             │
│   Reads pending_card,   │
│   imports via anki API  │
└─────────────────────────┘
```

See `Docs/FlowDiagram.md` for the full step-by-step sequence diagram.

---

## 3. Components

### 3.1 Anki Add-on (`ajs_addon/`)

Loaded by Anki Desktop at startup. Written in Python using Anki's PyQt6 bindings.

| File | Purpose |
|------|---------|
| `__init__.py` | Registration, QTimer, Tools menu, HTTP tab server, Qt dialogs |
| `bridge.py` | Polls for `pending_card.json`, imports card via Anki's `mw.col` API |
| `config.py` | Paths, timer interval, server port |
| `logger.py` | Rotating file logger (`~/.ajs/anki_addon.log`) |

**Tab server** (`localhost:27384`): A `threading.HTTPServer` running in a daemon thread. Implements two endpoints:
- `GET /ping` — returns `{"pending": bool, "mode": "yt"|"all"}`. Polled by the extension every 200ms.
- `POST /tabs` — receives tab list `[{title, url}]` from the extension. Signals `_tab_ready` threading.Event.

`SO_REUSEADDR` is set on the listening socket so Anki restarts don't leave the port in TIME_WAIT. A `profile_will_close` hook and `atexit` handler call `server_close()` on exit.

### 3.2 Chrome / Edge Extension (`extension/`)

Manifest V3. Permissions: `tabs`, `alarms`.

| File | Purpose |
|------|---------|
| `manifest.json` | MV3 manifest, permissions, icon paths |
| `background.js` | Service worker: polls `/ping`, pushes tabs via `/tabs` POST |
| `content.js` | Content script on youtube.com: polls `/ping` directly, POSTs own URL for yt-mode (avoids service worker dormancy) |

MV3 service workers are killed by Chrome after inactivity. The content script running inside the YouTube tab handles the common case (yt-mode) without needing the service worker to be alive. The `chrome.alarms` API (minimum 30s interval) provides a heartbeat to restart the service worker for all-tabs mode.

### 3.3 Terminal Pipeline (`terminal/`)

Invoked as a subprocess (`cmd /c ajs.bat --url <url>` on Windows, `osascript Terminal` on macOS). Runs in a visible terminal window so the user can interact with it.

| File | Purpose |
|------|---------|
| `ajs.py` | Main pipeline orchestrator, UI helpers, popup/getch utilities |
| `transcript.py` | yt-dlp subprocess, json3 subtitle parser, sentence merger |
| `normalizer.py` | pykakasi kanji→hiragana→romaji conversion, segment annotation |
| `fzf_menu.py` | fzf wrapper (NUL-delimited multi-line mode), numbered fallback |
| `dictionary.py` | LLM prompt template, JSON extraction, retry with backoff |
| `llm.py` | HTTP POST to Ollama `/api/generate`, spinner thread, error typing |
| `tts.py` | edge-tts audio synthesis |
| `card_writer.py` | Writes `pending_card.json` |
| `crash_reporter.py` | Diagnostics collection, GitHub issue filing |
| `url_capture.py` | Fallback URL capture (not used when --url is passed) |
| `config.py` | All constants: model name, timeouts, paths, retry counts |
| `logger.py` | Rotating file logger (`~/.ajs/ajs.log`) |

---

## 4. Packages and Dependencies

### Python (terminal pipeline)
| Package | Version | Purpose |
|---------|---------|---------|
| `yt-dlp` | latest | Downloads subtitle/caption tracks from YouTube in json3 format |
| `pykakasi` | ≥2.2 | Converts kanji/katakana/romaji → hiragana; generates romaji for search |
| `edge-tts` | ≥6.1 | Microsoft Edge TTS — synthesises Japanese audio clips |
| `requests` | bundled with Anki | HTTP client for Ollama API and crash report submission |
| `fzf` | ≥0.46 | External binary — fuzzy-search terminal UI for transcript selection |

### Python (Anki add-on)
| Package | Source |
|---------|--------|
| `PyQt6` | Bundled with Anki 23.x |
| `requests` | Bundled with Anki 23.x |
| `http.server` | Python stdlib |
| `threading` | Python stdlib |

### AI / LLM
| Component | Details |
|-----------|---------|
| **Ollama** | Local LLM inference server. https://ollama.com — free, runs entirely offline after setup |
| **qwen2.5:3b** | Default model. Lightweight (3B parameters, ~2GB RAM). Good JSON adherence. Pull with: `ollama pull qwen2.5:3b` |

The model is prompted to return a strict JSON object with five fields: `word`, `reading`, `definition_en`, `example_sentence`, `part_of_speech`. Retries with exponential backoff (2s → 4s → 8s) on malformed output. Connection errors (Ollama not running) fail immediately without retrying.

### Browser Extension
| Technology | Notes |
|------------|-------|
| Chrome Extension Manifest V3 | Service worker background script, content scripts |
| `chrome.tabs` API | Queries open tabs by URL pattern or all tabs |
| `chrome.alarms` API | 30s heartbeat to restart dormant service worker |

---

## 5. Key Design Decisions

**Why localhost HTTP instead of native messaging?**
Native messaging requires a registry entry and a separately installed host binary. HTTP over loopback needs nothing on the extension side and is easier to debug. Security is equivalent for localhost-only use.

**Why a content script for tab detection instead of relying on the service worker?**
MV3 service workers are killed by Chrome after ~30s of inactivity. A content script running inside the YouTube tab is alive as long as the tab is open — no dormancy issue.

**Why local LLM (Ollama) instead of a cloud API?**
Privacy (no video data leaves the machine), no API key management, no per-request cost, works offline. The tradeoff is occasional malformed output which the retry policy handles.

**Why fzf for the transcript UI?**
fzf provides instant fuzzy search across potentially 500+ subtitle segments with zero UI framework dependency. NUL-delimited (`--read0`) mode allows true multi-line entries so kanji, hiragana, and romaji display as stacked lines while remaining searchable across all three forms.

**IPC between terminal and Anki: why a file?**
`pending_card.json` is the simplest possible IPC — no sockets, no named pipes, works across process restarts, and is trivially debuggable (just open the file). The QTimer polls every 500ms which is imperceptible latency.

---

## 6. Reporting Issues / Contributing

To report a bug through the built-in tool:
- Run AJS normally; if a crash occurs, select yes when asked to file a report.
- This creates a GitHub issue automatically with full diagnostics attached.

To report or contribute manually:
1. Go to https://github.com/albazzaztariq/Anki-Browser-Plugin/issues
2. Click **New Issue** and fill in what happened + steps to reproduce
3. For code contributions, fork the repository, make changes on a branch, and open a pull request targeting `main`

**Contact / available for hire:** https://github.com/albazzaztariq
