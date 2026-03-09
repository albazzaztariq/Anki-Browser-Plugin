# AJS — Process Flow & Architecture Diagram

## Full Pipeline Sequence

```
USER                    ANKI ADD-ON              CHROME EXTENSION         TERMINAL PIPELINE
 |                           |                          |                        |
 |  Ctrl+Shift+E             |                          |                        |
 |-------------------------->|                          |                        |
 |                           |  _tab_pending.set()      |                        |
 |                           |  GET /ping → pending:true|                        |
 |                           |<-------------------------|                        |
 |                           |                          |  chrome.tabs.query()   |
 |                           |                          |----------------------->|
 |                           |  POST /tabs [{title,url}]|                        |
 |                           |<-------------------------|                        |
 |                           |  _tab_ready.set()        |                        |
 |                           |                          |                        |
 |  Tab picker (if >1)       |                          |                        |
 |<--------------------------|                          |                        |
 |  Select tab               |                          |                        |
 |-------------------------->|                          |                        |
 |                           |                          |                        |
 |                           |  subprocess: cmd /c ajs.bat --url <url>           |
 |                           |-------------------------------------------------->|
 |                           |                          |                        |
 |                           |                          |        yt-dlp subprocess
 |                           |                          |        downloads .json3
 |                           |                          |        subtitle file
 |                           |                          |        [localhost only]
 |                           |                          |                        |
 |  fzf opens (transcript)   |                          |                        |
 |<--------------------------------------------------------------------------|   |
 |  User types / searches    |                          |                        |
 |-------------------------------------------------------------------------->|   |
 |                           |                          |                        |
 |                           |                          |        POST /api/generate
 |                           |                          |        → Ollama (localhost:11434)
 |                           |                          |        ← JSON: word/reading/
 |                           |                          |           definition/sentence/pos
 |                           |                          |                        |
 |                           |                          |        edge-tts (internet)
 |                           |                          |        → audio .mp3 file
 |                           |                          |                        |
 |  Card preview / confirm   |                          |                        |
 |<--------------------------------------------------------------------------|   |
 |  Enter to accept          |                          |                        |
 |-------------------------------------------------------------------------->|   |
 |                           |                          |                        |
 |                           |                          |  writes pending_card.json
 |                           |                          |  → ~/.ajs/pending_card.json
 |                           |                          |                        |
 |                           |  QTimer (500ms)          |                        |
 |                           |  detects pending_card.json                        |
 |                           |  bridge.py imports card  |                        |
 |                           |  via mw.col Anki API     |                        |
 |                           |                          |                        |
 |  Card appears in Anki     |                          |                        |
 |<--------------------------|                          |                        |
```

---

## Component Dependency Map

```
┌─────────────────────────────────────────────────────────────────────┐
│  ANKI ADD-ON  (ajs_addon/)                                          │
│                                                                     │
│  __init__.py                                                        │
│    ├── config.py          (constants: port, paths, intervals)       │
│    ├── logger.py          (rotating file log → ~/.ajs/addon.log)    │
│    ├── bridge.py          (card importer, polls filesystem)         │
│    │     └── config.py                                              │
│    └── [stdlib]                                                     │
│          ├── http.server  (tab server on localhost:27384)           │
│          ├── threading    (daemon thread + Event sync)              │
│          └── atexit       (clean shutdown hook)                     │
│                                                                     │
│  [Anki bundled]                                                     │
│    ├── PyQt6              (QTimer, QDialog, QAction, QShortcut)     │
│    └── requests           (Ollama health check in status dialog)    │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ subprocess launch
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  TERMINAL PIPELINE  (terminal/)                                     │
│                                                                     │
│  ajs.py  (orchestrator)                                             │
│    ├── config.py                                                    │
│    ├── logger.py          (rotating file log → ~/.ajs/ajs.log)      │
│    ├── url_capture.py     (fallback browser URL capture)            │
│    ├── transcript.py                                                │
│    │     ├── normalizer.py                                          │
│    │     │     └── pykakasi          [pip]                          │
│    │     └── yt-dlp                  [external binary / pip]        │
│    ├── fzf_menu.py                                                  │
│    │     └── fzf                     [external binary]              │
│    ├── dictionary.py                                                │
│    │     └── llm.py                                                 │
│    │           ├── requests          [pip]                          │
│    │           └── Ollama            [external service :11434]      │
│    │                 └── qwen2.5:3b  [ollama model]                 │
│    ├── tts.py                                                       │
│    │     └── edge-tts                [pip] → internet (MS TTS)      │
│    ├── card_writer.py     (writes pending_card.json)                │
│    └── crash_reporter.py                                            │
│          ├── gh CLI        [optional, for auto issue filing]        │
│          └── GitHub API    [fallback, needs GITHUB_ISSUE_TOKEN]     │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│  BROWSER EXTENSION  (extension/)                                    │
│                                                                     │
│  background.js  (MV3 service worker)                                │
│    ├── chrome.tabs        (query open tabs)                         │
│    ├── chrome.alarms      (30s heartbeat, prevents dormancy)        │
│    └── fetch              (polls localhost:27384/ping)              │
│                                                                     │
│  content.js  (injected into youtube.com tabs)                       │
│    ├── fetch              (polls localhost:27384/ping directly)     │
│    └── chrome.runtime.sendMessage  (wakes service worker for       │
│                                     all-tabs mode)                  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Data Flow: Subtitle Processing

```
YouTube video URL
      │
      ▼
  yt-dlp subprocess
  --sub-lang ja --sub-format json3
      │
      ▼
  .json3 file  (events[].segs[].utf8  with  tStartMs / dDurationMs)
      │
      ▼
  _parse_json3()
  strips \r\n, collapses whitespace
  → list[{start, duration, text}]
      │
      ▼
  _merge_into_sentences()
  splits at: 。！？…!?
  force-splits on silence gap > 1.5s
  → list[{start, duration, text}]  (fewer, cleaner segments)
      │
      ▼
  normalizer.annotate_segments()
  pykakasi: text → hiragana reading, hepburn romaji
  adds: reading, romaji, display fields
  → list[{start, duration, text, reading, romaji, display}]
      │
      ▼
  fzf  (NUL-delimited multi-line entries)
  Line 1: [MM:SS] 白馬の王子様
  Line 2:         はくばのおうじさま
  Line 3:         hakubanooujisama
  Search matches any of the three forms
```

---

## IPC Summary

| Channel | Protocol | Parties | Direction |
|---------|----------|---------|-----------|
| Tab request/response | HTTP (localhost:27384) | Add-on ↔ Extension | Bidirectional |
| Terminal launch | subprocess (cmd /c) | Add-on → Terminal | One-way |
| Card handoff | JSON file (~/.ajs/pending_card.json) | Terminal → Add-on | One-way (file) |
| LLM inference | HTTP (localhost:11434) | Terminal → Ollama | Request/response |
| Audio synthesis | HTTPS | Terminal → MS Edge TTS | Request/response |
| Crash reporting | HTTPS (GitHub API) | Terminal → GitHub | One-way (optional) |

---

## Notes on Dependencies

- **yt-dlp** must be in PATH or installed via pip. Used as a subprocess, not a library.
- **fzf** must be in PATH or bundled with the installer. Used as a subprocess.
- **Ollama** runs as a separate background service. Not managed by AJS.
- **edge-tts** is a pure Python package; no external binary needed.
- **pykakasi** loads a dictionary on first import (~1s). The Kakasi instance is reused across calls.
- **gh CLI** is optional. Only needed for automatic crash report submission from dev machines. End-user crash reports will use the GitHub API token path once a fine-grained PAT is configured in `config.py` (`GITHUB_ISSUE_TOKEN`).
