const AJS_PORT = 27384;

async function pushTabs(mode) {
  const query = mode === "all" ? {} : { url: "*://www.youtube.com/watch?*" };
  return new Promise((resolve) => {
    chrome.tabs.query(query, (tabs) => {
      const data = tabs.map(t => ({ title: t.title, url: t.url }));
      fetch(`http://localhost:${AJS_PORT}/tabs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data)
      }).catch(() => {}).finally(resolve);
    });
  });
}

async function poll() {
  try {
    const r = await fetch(`http://localhost:${AJS_PORT}/ping`, { cache: "no-store" });
    if (r.ok) {
      const { pending, mode } = await r.json();
      if (pending) await pushTabs(mode || "yt");
    }
  } catch (_) {}
}

// chrome.alarms fires every 0.5 minutes (minimum Chrome allows is 0.5 min = 30s).
// This keeps the service worker alive reliably — unlike a while loop which Chrome
// will kill. On each alarm tick we also kick off a fast polling burst.
chrome.alarms.create("ajs-keepalive", { periodInMinutes: 0.5 });

chrome.alarms.onAlarm.addListener(async () => {
  // Burst-poll for up to 25s (every 200ms) to cover the alarm gap.
  const end = Date.now() + 25000;
  while (Date.now() < end) {
    await poll();
    await new Promise(res => setTimeout(res, 200));
  }
});

// Also run a polling burst on startup/install so it's responsive immediately.
async function startPolling() {
  while (true) {
    await poll();
    await new Promise(res => setTimeout(res, 200));
  }
}

chrome.runtime.onStartup.addListener(startPolling);
chrome.runtime.onInstalled.addListener(startPolling);
startPolling();
