const AJS_PORT = 27384;
const BROWSER_LABEL = navigator.userAgent.includes("Edg/") ? "Edge" : "Chrome";

// Accept keepalive ports from content scripts.
chrome.runtime.onConnect.addListener(port => {
  if (port.name === 'keepAlive') { /* holding the port open is enough */ }
});

async function pushTabs(mode) {
  const tabs = await chrome.tabs.query({});
  const filtered = mode === "all" ? tabs : tabs.filter(t => t.url && t.url.includes("youtube.com/watch"));
  const data = (filtered.length ? filtered : tabs).map(t => ({ title: t.title, url: t.url, browser: BROWSER_LABEL }));
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
  for (let i = 0; i < 3; i++) {
    try {
      const r = await fetch(`http://localhost:${AJS_PORT}/trigger`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: tab.url, title: tab.title || "", browser: BROWSER_LABEL })
      });
      if (r.ok) break;
    } catch (_) {}
    await new Promise(res => setTimeout(res, 300));
  }
});

// Single polling loop — dedup flag prevents duplicate loops if SW wakes
// multiple times (alarm + keepalive port reconnect).
let _polling = false;

async function startPolling() {
  if (_polling) return;
  _polling = true;
  try {
    while (true) {
      await checkPending();
      await new Promise(res => setTimeout(res, 1500));
    }
  } finally {
    _polling = false;
  }
}

// Alarm wakes the SW when all content scripts are frozen.
// It just calls startPolling() — no burst loop.
chrome.alarms.create("ajs-poll", { periodInMinutes: 1 });
chrome.alarms.onAlarm.addListener(alarm => {
  if (alarm.name === "ajs-poll") startPolling();
});

// Inject content script into already-open YouTube tabs on SW startup.
function injectIntoExistingTabs() {
  chrome.tabs.query({}, tabs => {
    for (const tab of tabs) {
      if (tab.url && tab.url.includes("youtube.com/watch")) {
        chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["content.js"] }).catch(() => {});
      }
    }
  });
}

chrome.runtime.onStartup.addListener(() => { injectIntoExistingTabs(); startPolling(); });
chrome.runtime.onInstalled.addListener(() => { injectIntoExistingTabs(); startPolling(); });
injectIntoExistingTabs();
startPolling();
