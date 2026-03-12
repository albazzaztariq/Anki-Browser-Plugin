const AJS_PORT = 27384;
const BROWSER_LABEL = "Firefox";

// Accept keepalive ports from content scripts.
browser.runtime.onConnect.addListener(port => {
  if (port.name === 'keepAlive') { /* holding the port open is enough */ }
});

async function pushTabs(mode) {
  const tabs = await browser.tabs.query({});
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

// Single polling loop — persistent:true background stays alive indefinitely.
// Dedup flag prevents a second loop if something calls startPolling() twice.
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

// Alarm as a safety net only — startPolling() is a no-op if already running.
browser.alarms.create("ajs-poll", { periodInMinutes: 1 });
browser.alarms.onAlarm.addListener(alarm => {
  if (alarm.name === "ajs-poll") startPolling();
});

// Inject content script into already-open YouTube tabs on startup.
function injectIntoExistingTabs() {
  browser.tabs.query({}).then(tabs => {
    for (const tab of tabs) {
      if (tab.url && tab.url.includes("youtube.com/watch")) {
        browser.tabs.executeScript(tab.id, { file: "content.js" }).catch(() => {});
      }
    }
  });
}

injectIntoExistingTabs();
startPolling();
