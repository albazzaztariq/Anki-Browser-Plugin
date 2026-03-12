// Runs on every youtube.com/watch page.
// Sole job: keep the service worker alive via a persistent port so Chrome
// never suspends it. All polling and tab-pushing is handled by background.js.

const AJS_PORT = 27384;
const BROWSER_LABEL = "Chrome";

// Hold an open port to the SW — prevents Chrome from killing it after 30s.
function keepSWAlive() {
  try {
    const port = chrome.runtime.connect({ name: 'keepAlive' });
    port.onDisconnect.addListener(() => setTimeout(keepSWAlive, 100));
  } catch (_) {
    setTimeout(keepSWAlive, 1000);
  }
}
keepSWAlive();

// Ctrl+Shift+F while YouTube tab is focused — fire /trigger directly.
async function triggerAJS() {
  try {
    await fetch(`http://localhost:${AJS_PORT}/trigger`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: window.location.href, title: document.title, browser: BROWSER_LABEL })
    });
  } catch (_) {}
}

document.addEventListener("keydown", (e) => {
  if (e.ctrlKey && e.shiftKey && e.key === "F") {
    e.preventDefault();
    triggerAJS();
  }
});
