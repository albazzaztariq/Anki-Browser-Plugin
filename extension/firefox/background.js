const AJS_PORT = 27384;
const BROWSER_LABEL = "Firefox";

// Accept keepalive ports from content scripts.
browser.runtime.onConnect.addListener(port => {
  if (port.name === 'keepAlive') { /* holding the port open is enough */ }
});

async function getVideoTime(tabId) {
  try {
    const res = await browser.tabs.executeScript(tabId, {
      code: `(function() { const v = document.querySelector('video'); return v ? v.currentTime || (v.buffered.length > 0 ? v.buffered.end(v.buffered.length - 1) : 0) : null; })()`
    });
    return res?.[0] ?? null;
  } catch (_) { return null; }
}

async function pushTabs(mode) {
  const tabs = await browser.tabs.query({});
  const filtered = mode === "all" ? tabs : tabs.filter(t => t.url && t.url.includes("youtube.com/"));
  const base = filtered.length ? filtered : tabs;
  const data = await Promise.all(base.map(async t => ({
    title: t.title, url: t.url, browser: BROWSER_LABEL,
    timestamp: t.url && t.url.includes("youtube.com/") ? await getVideoTime(t.id) : null
  })));
  await fetch(`http://localhost:${AJS_PORT}/tabs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data)
  }).catch(() => {});
}

async function checkPending() {
  try {
    const r = await fetch(`http://localhost:${AJS_PORT}/ping`, { cache: "no-store" });
    if (!r.ok) return;
    const { pending, mode } = await r.json();
    if (pending) await pushTabs(mode || "yt");
  } catch (_) {}
}

browser.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === "pushTabs") {
    pushTabs(msg.mode || "yt").then(() => sendResponse({ ok: true }));
    return true;
  }
});

browser.commands.onCommand.addListener(async (command) => {
  if (command !== "trigger-ajs") return;
  const [tab] = await browser.tabs.query({ active: true, currentWindow: true });
  if (!tab?.url) return;
  const timestamp = await getVideoTime(tab.id);
  for (let i = 0; i < 3; i++) {
    try {
      const r = await fetch(`http://localhost:${AJS_PORT}/trigger`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: tab.url, title: tab.title || "", browser: BROWSER_LABEL, timestamp })
      });
      if (r.ok) break;
    } catch (_) {}
    await new Promise(res => setTimeout(res, 300));
  }
});

// Single polling loop — persistent:true background stays alive indefinitely.
// Dedup flag prevents a second loop if something calls startPolling() twice.
let _polling = false;

async function startPolling() {
  if (_polling) return;
  _polling = true;
  try {
    while (true) {
      await checkPending();
      await new Promise(res => setTimeout(res, 3000));
    }
  } finally {
    _polling = false;
  }
}

// Alarm as a safety net only — startPolling() is a no-op if already running.
browser.alarms.create("ajs-poll", { periodInMinutes: 1 });
browser.alarms.onAlarm.addListener(alarm => {
  if (alarm.name === "ajs-poll") startPolling();
});

startPolling();
