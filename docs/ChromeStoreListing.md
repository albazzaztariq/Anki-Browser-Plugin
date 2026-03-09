# Chrome Web Store — AJS Tab Helper
## Promotional Listing Draft

---

<p align="center">
  <img width="128" height="128" alt="AJS Tab Helper icon" src="https://github.com/user-attachments/assets/fa45ccb5-7949-44ca-a466-683d0974a952"/>
</p>

---

## SHORT DESCRIPTION  

```
Connects Anki Japanese Sensei to your YouTube tabs so you can turn any Japanese video into flashcards in one keypress.
```

---

## FULL DESCRIPTION  *(paste directly into Chrome Web Store)*

---

**One keypress. One card. No copy-paste.**

You're watching Japanese YouTube. You hear a word you don't know.
Press **Ctrl+Shift+E** or select the tool in the menu — and 60 seconds later it's an Anki flashcard,
complete with kanji, reading, meaning, example sentences, and native audio.

That's Anki Japanese Sensei. This extension allows it to pull that audio straight from your browser.

---

**What AJS Tab Helper does**

When you press the shortcut, the AJS desktop app asks:
*"What YouTube tab is the user on right now?"*
This extension answers. That's its entire job.

It does not read page content. It does not touch YouTube's player.
It talks to nothing on the internet. Only your own machine.

---

**The full workflow**

  ① Watch any Japanese YouTube video in Chrome
  ② Hear an unfamiliar word — press Ctrl+Shift+E
  ③ A fuzzy-search picker shows every subtitle line
     Search in romaji, hiragana, or kanji — all work
  ④ Pick the segment · confirm the word
  ⑤ Local AI builds the dictionary entry (100% offline, no API key)
  ⑥ Preview the card: kanji · reading · meaning · JLPT · audio
  ⑦ Press Enter — card lands in Anki

**Keyboard only. No mouse. No account.**

---

**Privacy — the short version**

This extension only talks to localhost.
No servers. No analytics. No tracking. Ever.
Full source: github.com/albazzaztariq/Anki-Browser-Plugin

---

**Requirements**

→ AJS desktop app (free installer for Windows & macOS)
   github.com/albazzaztariq/Anki-Browser-Plugin/releases
→ Anki 2.1.55+ (free — ankiweb.net)
→ Everything else (Ollama, AI model, tools) is handled by the installer

---

**Support**
github.com/albazzaztariq/Anki-Browser-Plugin/issues

---

## PERMISSIONS JUSTIFICATION  *(for the review form)*

| Permission | Justification |
|------------|---------------|
| `tabs` | Reads the URL and title of open tabs so the AJS desktop process can identify the active YouTube tab. No page content is accessed. |
| `alarms` | Keeps the service worker alive with a 25-second heartbeat so it stays responsive between user actions. |
| `host_permissions: localhost:27384` | Receives requests from the AJS desktop app running on the same machine. No external hosts. |

---

## SCREENSHOTS  *(1280×800 recommended)*

### Screenshot 1 — The trigger moment
**Show:** Chrome with a Japanese video paused, Ctrl+Shift+E keys highlighted or annotated.
**Caption idea:** "Hear something? One shortcut is all it takes."
**File:** `docs/screenshots/ext_01_trigger.png`

### Screenshot 2 — Subtitle picker
**Show:** Terminal with the fzf picker open, three-line subtitle entries, a search term typed in.
**Caption idea:** "Every subtitle line — searchable in romaji, hiragana, or kanji."
**File:** `docs/screenshots/ext_02_picker.png`

### Screenshot 3 — Card preview
**Show:** Full card preview in terminal: kanji, reading, meaning, example, audio indicator.
**Caption idea:** "Full dictionary card, generated offline in under 15 seconds."
**File:** `docs/screenshots/ext_03_preview.png`

### Screenshot 4 — Anki deck
**Show:** Anki card browser with a freshly added card, audio icon visible.
**Caption idea:** "Card added. Done. Back to watching."
**File:** `docs/screenshots/ext_04_anki.png`

---

## PROMOTIONAL TILE  *(440×280 — marquee image)*

```
┌──────────────────────────────────────────────────────┐
│                                                      │
│    [探]                                              │
│                                                      │
│    AJS Tab Helper                      日本語先生    │
│                                                      │
│    YouTube → Anki.                                   │
│    One keypress.                                     │
│                                                      │
│    ─────────────────────────────────────────────     │
│    Free · Open Source · 100% Offline AI              │
└──────────────────────────────────────────────────────┘
```

**Design notes:**
- Dark background (`#0d0d0d`) matching the landing page
- 探 kanji large, red (`#c0392b`), top-left — mirrors the extension icon
- "AJS Tab Helper" in white serif (Yu Mincho / Georgia)
- 日本語先生 in gold (`#c9a84c`), top-right, small
- Tagline "YouTube → Anki. One keypress." in white, large
- Footer bar: "Free · Open Source · 100% Offline AI" in muted white

---

## STORE ICON  *(already exists)*

`extension/icons/icon128.png` — camera + magnifying glass + 探
Upload this directly. No changes needed.

---

## CATEGORY
`Productivity`

## LANGUAGE
`English`
