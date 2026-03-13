const AJS_PORT = 27384;
const BROWSER_LABEL = "Chrome";

// Accept keepalive ports from content scripts — keeps MV3 SW alive.
chrome.runtime.onConnect.addListener(port => {
  if (port.name === 'keepAlive') { /* holding the port open is enough */ }
});

async function getVideoTime(tabId) {
  // Primary: ask content script via message passing.
  const viaContent = await new Promise(resolve => {
    chrome.tabs.sendMessage(tabId, { action: "getVideoTime" }, response => {
      if (chrome.runtime.lastError || !response) resolve(null);
      else resolve(response.time ?? null);
    });
  });
  if (viaContent != null) return viaContent;

  // Fallback: inject directly if content script not available.
  try {
    const [res] = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => {
        const videos = Array.from(document.querySelectorAll('video'));
        const v = videos.find(v => !v.paused && v.currentTime > 0) || videos.find(v => v.currentTime > 0) || videos[0] || null;
        return v ? v.currentTime : null;
      },
    });
    return res?.result ?? null;
  } catch { return null; }
}

async function pushTabs(mode) {
  const tabs = await chrome.tabs.query({});
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

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === "pushTabs") {
    pushTabs(msg.mode || "yt").then(() => sendResponse({ ok: true }));
    return true;
  }
});

chrome.commands.onCommand.addListener(async (command) => {
  if (command !== "trigger-ajs") return;
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
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

// Single polling loop — dedup flag prevents duplicate loops on repeated SW wakes.
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

// Alarm wakes the SW when content scripts are frozen — no burst loop.
chrome.alarms.create("ajs-poll", { periodInMinutes: 1 });
chrome.alarms.onAlarm.addListener(alarm => {
  if (alarm.name === "ajs-poll") startPolling();
});

chrome.runtime.onStartup.addListener(() => startPolling());
chrome.runtime.onInstalled.addListener(() => startPolling());
startPolling();
