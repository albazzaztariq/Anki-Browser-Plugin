const AJS_PORT = 27384;
const BROWSER_LABEL = "Firefox";
// When true, extension sends a "debug" array with the trigger; terminal prints it.
const AJS_DEBUG_TO_TERMINAL = true;

function _push(debug, label, obj) {
  if (!debug) return;
  try {
    debug.push(label + (obj !== undefined ? " " + JSON.stringify(obj) : ""));
  } catch (_) {
    debug.push(label + " [serialize error]");
  }
}

// Accept keepalive ports from content scripts.
browser.runtime.onConnect.addListener(port => {
  if (port.name === 'keepAlive') { /* holding the port open is enough */ }
});

function parseTimestampFromUrl(url) {
  if (!url || !url.includes("youtube.com")) return null;
  try {
    const u = new URL(url);
    const t = u.searchParams.get("t");
    if (!t) return null;
    const s = t.trim().toLowerCase();
    let sec = 0;
    const h = s.match(/(\d+)h/);
    const m = s.match(/(\d+)m/);
    const secPart = s.match(/(\d+)s?$/);
    if (h) sec += parseInt(h[1], 10) * 3600;
    if (m) sec += parseInt(m[1], 10) * 60;
    if (secPart) sec += parseInt(secPart[1], 10);
    return sec > 0 ? sec : null;
  } catch (_) {
    return null;
  }
}

async function getVideoTimeViaScripting(tabId, debug) {
  _push(debug, "getVideoTimeViaScripting ENTRY", { tabId });
  try {
    const res = await browser.tabs.executeScript(tabId, {
      allFrames: true,
      code: `(function() { const v = document.querySelector('video'); return v && typeof v.currentTime === 'number' ? v.currentTime : null; })()`
    });
    _push(debug, "getVideoTimeViaScripting results", res);
    for (const val of res || []) {
      if (typeof val === "number" && val >= 0) return val;
    }
    return null;
  } catch (e) {
    _push(debug, "getVideoTimeViaScripting error", { message: e?.message, name: e?.name });
    return null;
  }
}

async function getVideoTimeViaMessage(tabId, debug) {
  _push(debug, "getVideoTimeViaMessage ENTRY", { tabId });
  try {
    const res = await browser.tabs.sendMessage(tabId, { action: "getVideoTime" });
    _push(debug, "getVideoTimeViaMessage response", res != null ? { time: res?.time } : null);
    return res?.time ?? null;
  } catch (e) {
    _push(debug, "getVideoTimeViaMessage error", { message: e?.message, name: e?.name });
    return null;
  }
}

async function getVideoTime(tabId, tabUrl, debug) {
  _push(debug, "getVideoTime ENTRY", { tabId });
  let t = await getVideoTimeViaScripting(tabId, debug);
  _push(debug, "getVideoTime after scripting t=", t);
  if (t != null) return t;
  t = await getVideoTimeViaMessage(tabId, debug);
  _push(debug, "getVideoTime after message t=", t);
  if (t != null) return t;
  const fromUrl = parseTimestampFromUrl(tabUrl);
  _push(debug, "getVideoTime from URL t=", fromUrl);
  return fromUrl;
}

async function pushTabs(mode) {
  const tabs = await browser.tabs.query({});
  const filtered = mode === "all" ? tabs : tabs.filter(t => t.url && t.url.includes("youtube.com/"));
  const base = filtered.length ? filtered : tabs;
  const data = await Promise.all(base.map(async t => ({
    title: t.title, url: t.url, browser: BROWSER_LABEL,
    timestamp: t.url && t.url.includes("youtube.com/") ? await getVideoTime(t.id, t.url, null) : null
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
  const debug = AJS_DEBUG_TO_TERMINAL ? [] : null;
  const timestamp = await getVideoTime(tab.id, tab.url, debug);
  for (let i = 0; i < 3; i++) {
    try {
      const r = await fetch(`http://localhost:${AJS_PORT}/trigger`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: tab.url, title: tab.title || "", browser: BROWSER_LABEL, timestamp, debug })
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
