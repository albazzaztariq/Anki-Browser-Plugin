const AJS_PORT = 27384;
const BROWSER_LABEL = navigator.userAgent.includes("Edg/") ? "Edge" : navigator.userAgent.includes("Firefox/") ? "Firefox" : "Chrome";

async function pushTabs(mode) {
  const query = mode === "all" ? {} : { url: "*://www.youtube.com/watch?*" };
  return new Promise((resolve) => {
    chrome.tabs.query(query, (tabs) => {
      const data = tabs.map(t => ({ title: t.title, url: t.url, browser: BROWSER_LABEL }));
      fetch(`http://localhost:${AJS_PORT}/tabs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data)
      }).catch(() => {}).finally(resolve);
    });
  });
}

async function checkPending() {
  try {
    const r = await fetch(`http://localhost:${AJS_PORT}/ping`, { cache: "no-store" });
    if (!r.ok) return;
    const { pending, mode } = await r.json();
    if (pending) await pushTabs(mode || "yt");
  } catch (_) {}
}

// Content script sends this message to wake the service worker immediately
// (content scripts can be frozen in background tabs, but sending a message
// always wakes the service worker).
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === "pushTabs") {
    pushTabs(msg.mode || "yt").then(() => sendResponse({ ok: true }));
    return true; // keep channel open for async response
  }
});

// Keyboard shortcut pressed while browser is the active window.
// Get the active tab URL and POST it directly to /trigger — no need for Anki
// to be focused or for the tab picker to appear.
chrome.commands.onCommand.addListener(async (command) => {
  if (command !== "trigger-ajs") return;
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.url) return;
  try {
    await fetch(`http://localhost:${AJS_PORT}/trigger`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: tab.url, title: tab.title || "", browser: BROWSER_LABEL })
    });
  } catch (_) {
    // Anki not running — nothing to do
  }
});

// Alarm fires every 1 minute — wakes the service worker even when all
// content scripts are frozen (minimised browser, background windows).
// On wake, burst-poll for the full minute gap so no request is missed.
chrome.alarms.create("ajs-poll", { periodInMinutes: 1 });
chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name !== "ajs-poll") return;
  const end = Date.now() + 58000;
  while (Date.now() < end) {
    await checkPending();
    await new Promise(res => setTimeout(res, 500));
  }
});

// Poll continuously on startup — Chrome kills this after ~5 min of SW runtime,
// but the alarm above re-wakes it before the next request is missed.
async function startPolling() {
  while (true) {
    await checkPending();
    await new Promise(res => setTimeout(res, 500));
  }
}

chrome.runtime.onStartup.addListener(startPolling);
chrome.runtime.onInstalled.addListener(startPolling);
startPolling();
