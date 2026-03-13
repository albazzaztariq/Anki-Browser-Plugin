const AJS_PORT = 27384;
const BROWSER_LABEL = navigator.userAgent.includes("Edg/") ? "Edge" : "Chrome";

// When true, extension sends a "debug" array with the trigger; terminal prints it so you see every step and variable in the terminal.
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
chrome.runtime.onConnect.addListener(port => {
  if (port.name === 'keepAlive') { /* holding the port open is enough */ }
});

async function getVideoTime(tabId, debug) {
  _push(debug, "getVideoTime ENTRY", { tabId });
  let t;
  // 1) Scripting main frame
  t = await getVideoTimeViaScripting(tabId, false, debug);
  _push(debug, "getVideoTime after scripting(main) t=", t);
  if (t != null) {
    _push(debug, "getVideoTime RETURN (from main)", t);
    return t;
  }
  t = await getVideoTimeViaScripting(tabId, true, debug);
  _push(debug, "getVideoTime after scripting(allFrames) t=", t);
  if (t != null) {
    _push(debug, "getVideoTime RETURN (from allFrames)", t);
    return t;
  }
  // 2) Content script message
  t = await getVideoTimeViaMessage(tabId, debug);
  _push(debug, "getVideoTime after sendMessage(before inject) t=", t);
  if (t != null) {
    _push(debug, "getVideoTime RETURN (from sendMessage)", t);
    return t;
  }
  // 3) Inject then sendMessage
  try {
    _push(debug, "getVideoTime injecting content.js");
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ["content.js"],
    });
    await new Promise(r => setTimeout(r, 100));
    t = await getVideoTimeViaMessage(tabId, debug);
    _push(debug, "getVideoTime after sendMessage(after inject) t=", t);
  } catch (e) {
    _push(debug, "getVideoTime inject or sendMessage threw", { message: e?.message, name: e?.name });
  }
  _push(debug, "getVideoTime RETURN (final) t=", t != null ? t : null);
  return t != null ? t : null;
}

function getVideoTimeViaMessage(tabId, debug) {
  return new Promise(resolve => {
    _push(debug, "getVideoTimeViaMessage ENTRY", { tabId });
    chrome.tabs.sendMessage(tabId, { action: "getVideoTime" }, response => {
      const err = chrome.runtime.lastError?.message;
      _push(debug, "getVideoTimeViaMessage lastError", err != null ? err : null);
      _push(debug, "getVideoTimeViaMessage response", response != null ? { time: response?.time } : null);
      if (chrome.runtime.lastError || !response) resolve(null);
      else resolve(response.time ?? null);
    });
  });
}

async function getVideoTimeViaScripting(tabId, allFrames, debug) {
  _push(debug, "getVideoTimeViaScripting ENTRY", { tabId, allFrames });
  try {
    const results = await chrome.scripting.executeScript({
      target: allFrames ? { tabId, allFrames: true } : { tabId },
      func: () => {
        const v = document.querySelector('video');
        return v && typeof v.currentTime === 'number' ? v.currentTime : null;
      },
    });
    _push(debug, "getVideoTimeViaScripting results (raw)", results);
    for (const r of results || []) {
      const val = r?.result;
      if (typeof val === 'number' && val >= 0) {
        _push(debug, "getVideoTimeViaScripting RETURN (first valid)", val);
        return val;
      }
    }
    _push(debug, "getVideoTimeViaScripting RETURN (no valid)", null);
    return null;
  } catch (e) {
    _push(debug, "getVideoTimeViaScripting threw", { message: e?.message, name: e?.name });
    return null;
  }
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

chrome.commands.onCommand.addListener(async (command) => {
  if (command !== "trigger-ajs") return;
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.url) return;
  const debug = AJS_DEBUG_TO_TERMINAL ? [] : null;
  let timestamp = await getVideoTime(tab.id, debug);
  if (timestamp == null) timestamp = parseTimestampFromUrl(tab.url);
  if (debug) debug.push("parseTimestampFromUrl(url) => " + JSON.stringify(timestamp));
  const body = { url: tab.url, title: tab.title || "", browser: BROWSER_LABEL, timestamp };
  if (debug) body.debug = debug;
  for (let i = 0; i < 3; i++) {
    try {
      const r = await fetch(`http://localhost:${AJS_PORT}/trigger`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body)
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
      await new Promise(res => setTimeout(res, 3000));
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

chrome.runtime.onStartup.addListener(() => startPolling());
chrome.runtime.onInstalled.addListener(() => startPolling());
startPolling();
