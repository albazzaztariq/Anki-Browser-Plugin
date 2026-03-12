const AJS_PORT = 27384;
const BROWSER_LABEL = "Firefox";

// Keep the background page alive by holding an open message port.
function keepSWAlive() {
  try {
    const port = browser.runtime.connect({ name: 'keepAlive' });
    port.onDisconnect.addListener(() => setTimeout(keepSWAlive, 100));
  } catch (_) {
    setTimeout(keepSWAlive, 1000);
  }
}
keepSWAlive();

// Content script is kept minimal for Firefox — all polling and tab-pushing
// is handled by the persistent background page, which can freely reach
// http://localhost without mixed-content blocking.
