// Runs on every youtube.com/watch page.
// Handles two jobs:
//   1. Ctrl+Shift+F pressed while browser is active — trigger AJS immediately
//      with the current tab URL. No manual shortcut config, works in all browsers.
//   2. Poll for pending tab requests from the Anki-side shortcut and respond.

const AJS_PORT = 27384;
const BROWSER_LABEL = navigator.userAgent.includes("Edg/") ? "Edge" : navigator.userAgent.includes("Firefox/") ? "Firefox" : "Chrome";
const RUNTIME = typeof browser !== 'undefined' ? browser : chrome;

async function triggerAJS() {
  try {
    await fetch(`http://localhost:${AJS_PORT}/trigger`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: window.location.href, title: document.title, browser: BROWSER_LABEL })
    });
  } catch (_) {}
}

// Ctrl+Shift+F while YouTube tab is focused — fire immediately.
document.addEventListener("keydown", (e) => {
  if (e.ctrlKey && e.shiftKey && e.key === "F") {
    e.preventDefault();
    triggerAJS();
  }
});

// Poll for Anki-side shortcut requests (Ctrl+Shift+F pressed while Anki is active).
setInterval(async () => {
  try {
    const r = await fetch(`http://localhost:${AJS_PORT}/ping`, { cache: "no-store" });
    if (!r.ok) return;
    const { pending, mode } = await r.json();
    if (!pending) return;
    await fetch(`http://localhost:${AJS_PORT}/tabs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify([{ title: document.title, url: window.location.href, browser: BROWSER_LABEL }])
    }).catch(() => {});
    RUNTIME.runtime.sendMessage({ action: "pushTabs", mode: mode || "yt" }).catch(async () => {
      await fetch(`http://localhost:${AJS_PORT}/tabs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify([{ title: document.title, url: window.location.href, browser: BROWSER_LABEL }])
      }).catch(() => {});
    });
  } catch (_) {}
}, 500);
