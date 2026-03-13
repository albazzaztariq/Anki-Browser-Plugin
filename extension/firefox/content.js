browser.runtime.onMessage.addListener((msg, sender) => {
  if (msg.action === "getVideoTime") {
    const videos = Array.from(document.querySelectorAll('video'));
    const v = videos.find(v => !v.paused && v.currentTime > 0) || videos.find(v => v.currentTime > 0) || videos[0] || null;
    return Promise.resolve({ time: v ? v.currentTime : null });
  }
});
