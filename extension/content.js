// Runs on every youtube.com/watch page.
// Polls Anki's local server; when a tab request is pending, wakes the
// background service worker to do a fresh chrome.tabs.query and push results.
setInterval(async () => {
  try {
    const r = await fetch("http://localhost:27384/ping", { cache: "no-store" });
    if (!r.ok) return;
    const { pending } = await r.json();
    if (pending) {
      chrome.runtime.sendMessage({ action: "pushTabs" }).catch(() => {});
    }
  } catch (_) {}
}, 200);
