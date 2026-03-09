# AJS — Release Checklist (v0.1)

## CRITICAL (must fix before release)

### Extension Reliability
- [ ] Service worker dormancy — content script fix not fully tested
- [ ] "Browser not found" UX: 1st failure → refresh extension message box
- [ ] "Browser not found" UX: 2nd+ failure → "Report Bug" button → auto-file GitHub issue
- [ ] Track failure count persistently (module-level, resets on Anki restart)
- [ ] Unsupported browser handling — document in AnkiWeb listing which browsers work
- [ ] SO_REUSEADDR confirmed working on restart — needs test on clean Windows machine

### Help / Documentation in UI
- [ ] "Japanese Sensei — Help..." menu item under Tools
- [ ] On click: open README.md if found, else show message box with path + AnkiWeb URL
- [ ] README.md to be written (installation, usage walkthrough, FAQ, screenshots)
- [ ] README path search: check add-on folder, ~/.ajs/, nearby — don't assume fixed location

### Crash Reporter (end users)
- [ ] Fine-grained GitHub PAT (issues:write only on this repo) — bake into config for distribution
- [ ] `gh` CLI not available on end-user machines — API token path must work
- [ ] Test issue creation end-to-end on a non-dev machine

### Add-on Description / AnkiWeb Listing
- [ ] Write full description with keywords: YouTube, Japanese, audio clip, sentence mining,
      browser, subtitle, immersion, word lookup, vocabulary
- [ ] Note supported browsers: Chrome, Edge (Chromium). Firefox/Safari not supported.
- [ ] Screenshots: fzf segment selector, card preview, Anki card result
- [ ] Walkthrough GIF or video

## IMPORTANT (nice to have at v0.1)

### Features
- [ ] Audio trimming: 15s clip around selected timestamp (yt-dlp + ffmpeg)
- [ ] No-subtitle fallback: manual sentence entry (E-3) UX polish
- [ ] English subtitle detection: warn user instead of silently returning empty
- [ ] TTS: confirm edge-tts works offline / on first run without extra install steps

### Testing
- [ ] macOS VM test: full pipeline, JXA, .pkg installer, macOS-specific code paths
- [ ] Windows clean-install test (no Python, no gh CLI, no yt-dlp pre-installed)
- [ ] Test with multiple Chrome windows open
- [ ] Test with Edge (should work — Chromium-based)
- [ ] Test Anki restart 3+ times — confirm port reuse holds

### Installer
- [ ] Installer writes README path into registry or known location so add-on can find it
- [ ] Installer creates desktop shortcut or Start Menu entry
- [ ] Update installer to open Chrome Web Store page post-install (once extension is published)

### Chrome / Edge Extension
- [ ] Publish to Chrome Web Store ($5 one-time)
- [ ] Edge Add-ons store (free, same extension package)
- [ ] Content script approach fully replacing service worker polling for yt-mode

## DEFERRED (post v0.1)

- [ ] Firefox extension (WebExtensions port)
- [ ] Safari extension ($99/year Apple Developer)
- [ ] Filter add-on description by language (AnkiWeb doesn't support this yet)
- [ ] Expanded "Sensei" features: grammar hints, JLPT level tagging, etc.
- [ ] Anki card template customization
- [ ] Support for non-YouTube yt-dlp sources (NHK, etc.)

---

## VERSIONING REFERENCE

| Bump | When |
|------|------|
| v0.1 → v0.2 | New feature or behavior change (pre-stable) |
| v0.x → v0.x.1 | Bug fix only, no new behavior |
| v0.x → v1.0 | Battle-tested, stable, ready for general distribution |
| v1.0 → v1.1 | New feature, backwards compatible |
| v1.x → v2.0 | Breaking change, major architectural shift, new scope |

Rule of thumb:
- Patch (x.x.Y): nothing changed from the user's perspective except something broken now works
- Minor (x.Y.0): user sees new things / new options
- Major (X.0.0): user's workflow changes, old configs/shortcuts may not work

