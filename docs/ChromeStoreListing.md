# Chrome Web Store Listing — AJS Tab Helper

---

## Name
AJS Tab Helper

## Short description (132 chars max)
Connects Anki Japanese Sensei to your YouTube tabs — lets the terminal pipeline find and extract subtitles in one keypress.

## Full description

**Turn any Japanese YouTube video into an Anki flashcard in under 60 seconds.**

AJS Tab Helper is the browser-side companion to **Anki Japanese Sensei (AJS)** — a free, open-source desktop tool that watches Japanese YouTube videos with you and builds vocabulary cards on demand.

---

### How it works

1. You watch a Japanese video in Chrome
2. You hear an unfamiliar word — press **Ctrl+Shift+E**
3. A fuzzy-search picker shows every subtitle line from the video
4. Pick the line, confirm the word
5. A local AI model generates the full dictionary entry (kanji, reading, meaning, JLPT level, example sentences)
6. Native-speaker audio is synthesised automatically
7. The card lands in Anki — done

**This extension's only job:** when the AJS desktop app asks "what YouTube tabs are open and what are their URLs?", this extension answers. That's it. It does not read page content, inject scripts into YouTube, or transmit anything outside your own machine.

---

### What this extension does

- Exposes a local-only API on `http://localhost:27384` — only your own machine can reach it
- Responds to tab queries from the AJS desktop process
- Uses the `tabs` permission to list open tabs and their URLs
- Uses `alarms` for a periodic keep-alive heartbeat

**It does not:**
- Read the content of any web page
- Store, log, or transmit any data
- Communicate with any server on the internet
- Run any code on YouTube or other sites

---

### Requirements

- **AJS desktop app** — free installer for Windows and macOS at [github.com/albazzaztariq/Anki-Browser-Plugin](https://github.com/albazzaztariq/Anki-Browser-Plugin)
- **Anki 2.1.55+** — free flashcard app at ankiweb.net
- Everything else (Ollama, AI model, tools) is handled by the installer

---

### Privacy

This extension communicates **only with localhost**. No data is sent to any external server, ever. There is no account, no analytics, no tracking.

Full source code: [github.com/albazzaztariq/Anki-Browser-Plugin/tree/master/extension](https://github.com/albazzaztariq/Anki-Browser-Plugin/tree/master/extension)

---

### Support

- Issues: github.com/albazzaztariq/Anki-Browser-Plugin/issues
- Docs: albazzaztariq.github.io/Anki-Browser-Plugin

---

## Category
Productivity

## Language
English

## Screenshots needed (1280×800 or 640×400)

1. **YouTube + picker** — Chrome with a Japanese video playing, the fzf subtitle picker open in a terminal alongside it
2. **Card preview** — the terminal card preview showing kanji, reading, meaning, example sentence
3. **Anki card** — the finished card open in the Anki card browser
4. **Extension popup** (if you add one) or the extension icon in the Chrome toolbar with the video tab visible

## Promotional tile (440×280)
Large AJS logo / 日本語先生 kanji on dark background with tagline:
"YouTube → Anki. One keypress."

## Store icon (128×128)
Square dark background, white/gold 語 kanji, small "AJS" text beneath.

---

## Permissions justification (for the review form)

| Permission | Reason |
|------------|--------|
| `tabs` | Read the URL and title of open tabs so the desktop app can find the active YouTube video. No page content is accessed. |
| `alarms` | Keep-alive heartbeat — wakes the service worker every 25 seconds so it stays responsive to local requests. |
| `host_permissions: localhost:27384` | Receive requests from the AJS desktop process running on the same machine. No external hosts. |
