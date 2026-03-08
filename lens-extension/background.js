// ─── Lens Background Service Worker ──────────────────────────────────────────
// Handles screenshot capture (requires background context) and coordinates
// between popup and content scripts.

// ─── Manual scroll-capture state ─────────────────────────────────────────────
// Frames are persisted to chrome.storage.session so they survive SW restarts.
// In-memory state is a write-through cache.

let manualCapture = {
  active:       false,
  tabId:        null,
  seenScrollYs: [],
  pageInfo:     null,
  lastCapTime:  0,
};

function mcReset() {
  manualCapture = { active: false, tabId: null, seenScrollYs: [], pageInfo: null, lastCapTime: 0 };
  chrome.storage.session.remove('lensCapture').catch(() => {});
}

async function mcSaveFrame(frame) {
  const stored = await chrome.storage.session.get('lensCapture').catch(() => ({}));
  const data = stored.lensCapture || { frames: [] };
  data.frames.push(frame);
  await chrome.storage.session.set({ lensCapture: data }).catch(() => {});
}

async function mcGetFrames() {
  const stored = await chrome.storage.session.get('lensCapture').catch(() => ({}));
  return stored.lensCapture?.frames || [];
}

async function mcRestoreIfNeeded() {
  if (manualCapture.active) return; // already loaded
  const stored = await chrome.storage.session.get('lensCapture').catch(() => ({}));
  const data = stored.lensCapture;
  if (data?.active) {
    manualCapture.active   = true;
    manualCapture.tabId    = data.tabId;
    manualCapture.pageInfo = data.pageInfo;
    manualCapture.seenScrollYs = data.seenScrollYs || [];
    manualCapture.lastCapTime  = 0; // reset so next capture isn't rate-limited
  }
}

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === 'screenshot')           handleScreenshot(msg, sendResponse);
  if (msg.action === 'fullPageCapture')      handleFullPageCapture(msg, sendResponse);
  if (msg.action === 'cropScreenshot')       handleCropScreenshot(msg, sendResponse);
  if (msg.action === 'sendToArtikLens')      handleSendToArtikLens(msg, sendResponse);
  if (msg.action === 'areaSelected')         handleAreaSelected(msg, sender, sendResponse);
  if (msg.action === 'startManualCapture')   handleStartManualCapture(msg, sendResponse);
  if (msg.action === 'scrollCapture')        handleScrollCapture(msg, sender, sendResponse);
  if (msg.action === 'endManualCapture')     handleEndManualCapture(msg, sendResponse);
  if (msg.action === 'keepAlive')            { sendResponse({ ok: true }); }
  if (msg.action === 'cancelManualCapture')  { mcReset(); sendResponse({ ok: true }); }
  if (msg.action === 'getManualCaptureState') {
    (async () => {
      await mcRestoreIfNeeded();
      const frames = await mcGetFrames();
      sendResponse({ active: manualCapture.active, tabId: manualCapture.tabId, frameCount: frames.length });
    })();
  }
  return true; // keep channel open for async responses
});


// ─── Screenshot (current viewport) ───────────────────────────────────────────

async function handleScreenshot(msg, sendResponse) {
  try {
    const dataUrl = await chrome.tabs.captureVisibleTab(null, { format: 'png' });
    sendResponse({ success: true, dataUrl });
  } catch (e) {
    sendResponse({ success: false, error: e.message });
  }
}


// ─── Full page scrolling capture ──────────────────────────────────────────────

async function handleFullPageCapture(msg, sendResponse) {
  const { tabId } = msg;
  try {
    const result = await captureFullPage(tabId);
    sendResponse({ success: true, ...result });
  } catch (e) {
    sendResponse({ success: false, error: e.message });
  }
}

async function captureFullPage(tabId) {
  // Get page dimensions
  const [{ result: info }] = await chrome.scripting.executeScript({
    target: { tabId },
    func: () => ({
      scrollHeight: Math.max(document.body.scrollHeight, document.documentElement.scrollHeight),
      scrollWidth:  Math.max(document.body.scrollWidth,  document.documentElement.scrollWidth),
      viewportH:    window.innerHeight,
      viewportW:    window.innerWidth,
      dpr:          window.devicePixelRatio || 1,
      origScrollY:  window.scrollY,
    }),
  });

  const { scrollHeight, viewportH, viewportW, dpr, origScrollY } = info;

  // Scroll to top and wait for render
  await execScript(tabId, (y) => window.scrollTo(0, y), [0]);
  await sleep(600);

  const frames = [];
  let lastCaptureTime = 0;

  // Build explicit list of scroll positions, always including the last frame
  // clamped to scrollHeight - viewportH so we don't overshoot.
  const maxScroll = Math.max(0, scrollHeight - viewportH);
  const positions = [];
  for (let y = 0; y < scrollHeight; y += viewportH) {
    positions.push(Math.min(y, maxScroll));
  }
  // Deduplicate (last step may equal maxScroll from both paths)
  const unique = [...new Set(positions)];

  for (let i = 0; i < unique.length; i++) {
    const scrollY = unique[i];

    // Scroll to position and wait for render
    if (i > 0) {
      await execScript(tabId, (y) => window.scrollTo({ top: y, behavior: 'instant' }), [scrollY]);
      await sleep(450);
    }

    // Enforce at least 600ms between captures (Chrome limit: 2/sec)
    const elapsed = Date.now() - lastCaptureTime;
    if (elapsed < 600) await sleep(600 - elapsed);

    const dataUrl = await chrome.tabs.captureVisibleTab(null, { format: 'png' });
    lastCaptureTime = Date.now();
    frames.push({ dataUrl, scrollY });
  }

  // Restore original scroll
  await execScript(tabId, (y) => window.scrollTo(0, y), [origScrollY]);

  // Stitch frames using OffscreenCanvas
  const totalH = Math.ceil(scrollHeight * dpr);
  const totalW  = Math.ceil(viewportW * dpr);
  const canvas  = new OffscreenCanvas(totalW, totalH);
  const ctx     = canvas.getContext('2d');

  for (const { dataUrl, scrollY } of frames) {
    const blob   = await (await fetch(dataUrl)).blob();
    const bitmap = await createImageBitmap(blob);
    ctx.drawImage(bitmap, 0, Math.round(scrollY * dpr));
    bitmap.close();
  }

  const finalBlob = await canvas.convertToBlob({ type: 'image/png' });
  const finalUrl  = await blobToDataUrl(finalBlob);

  return {
    dataUrl: finalUrl,
    width: totalW,
    height: totalH,
    frames: frames.length,
  };
}


// ─── Crop screenshot to selection rect ───────────────────────────────────────

async function handleCropScreenshot(msg, sendResponse) {
  const { dataUrl, rect, dpr } = msg;
  try {
    const scale  = dpr || 1;
    const blob   = await (await fetch(dataUrl)).blob();
    const bitmap = await createImageBitmap(blob);
    const canvas = new OffscreenCanvas(rect.width * scale, rect.height * scale);
    const ctx    = canvas.getContext('2d');
    ctx.drawImage(bitmap, -rect.x * scale, -rect.y * scale);
    bitmap.close();
    const cropped = await canvas.convertToBlob({ type: 'image/png' });
    const url = await blobToDataUrl(cropped);
    sendResponse({ success: true, dataUrl: url });
  } catch (e) {
    sendResponse({ success: false, error: e.message });
  }
}


// ─── Area selected — take screenshot then crop ───────────────────────────────

async function handleAreaSelected(msg, sender, sendResponse) {
  const { rect, dpr } = msg;
  const tabId = sender.tab.id;
  try {
    await sleep(100); // let overlay disappear
    const screenshot = await chrome.tabs.captureVisibleTab(null, { format: 'png' });
    const scale  = dpr || 1;
    const blob   = await (await fetch(screenshot)).blob();
    const bitmap = await createImageBitmap(blob);
    const canvas = new OffscreenCanvas(rect.width * scale, rect.height * scale);
    const ctx    = canvas.getContext('2d');
    ctx.drawImage(bitmap, -rect.x * scale, -rect.y * scale);
    bitmap.close();
    const cropped = await canvas.convertToBlob({ type: 'image/png' });
    const croppedUrl = await blobToDataUrl(cropped);

    // Store result so popup can read it when it reopens
    await chrome.storage.local.set({
      lensSelectionResult: { dataUrl: croppedUrl, rect, timestamp: Date.now() }
    });

    // Update badge to notify user
    await chrome.action.setBadgeText({ text: '1', tabId });
    await chrome.action.setBadgeBackgroundColor({ color: '#4f46e5', tabId });
  } catch (e) {
    console.error('Area capture failed:', e);
  }
}


// ─── Manual scroll capture ────────────────────────────────────────────────────

async function handleStartManualCapture(msg, sendResponse) {
  const { tabId } = msg;
  try {
    mcReset();
    // Get page info
    const [{ result: info }] = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => ({
        scrollHeight: Math.max(document.body.scrollHeight, document.documentElement.scrollHeight),
        viewportH:    window.innerHeight,
        viewportW:    window.innerWidth,
        dpr:          window.devicePixelRatio || 1,
      }),
    });
    manualCapture.active   = true;
    manualCapture.tabId    = tabId;
    manualCapture.pageInfo = info;

    // Persist active state to session storage (survives SW restart)
    await chrome.storage.session.set({
      lensCapture: { active: true, tabId, pageInfo: info, frames: [], seenScrollYs: [] }
    }).catch(() => {});

    // Capture first frame at scrollY=0
    await sleep(300);
    const dataUrl = await chrome.tabs.captureVisibleTab(null, { format: 'png' });
    manualCapture.lastCapTime = Date.now();
    manualCapture.seenScrollYs.push(0);
    await mcSaveFrame({ dataUrl, scrollY: 0 });

    // Update session storage seenScrollYs
    const stored = await chrome.storage.session.get('lensCapture').catch(() => ({}));
    if (stored.lensCapture) {
      stored.lensCapture.seenScrollYs = manualCapture.seenScrollYs;
      await chrome.storage.session.set({ lensCapture: stored.lensCapture }).catch(() => {});
    }

    await chrome.action.setBadgeText({ text: 'REC', tabId });
    await chrome.action.setBadgeBackgroundColor({ color: '#ef4444', tabId });

    sendResponse({ ok: true });
  } catch (e) {
    mcReset();
    sendResponse({ ok: false, error: e.message });
  }
}

async function handleScrollCapture(msg, sender, sendResponse) {
  // Restore state if SW was restarted
  await mcRestoreIfNeeded();
  if (!manualCapture.active) { sendResponse({ ok: false }); return; }

  const { scrollY } = msg;

  // Deduplicate: skip if we've captured within 80px of this position
  const tooClose = manualCapture.seenScrollYs.some(y => Math.abs(y - scrollY) < 80);
  if (tooClose) { sendResponse({ ok: true, skipped: true }); return; }

  // Rate limit: at most 2 captures/sec
  const elapsed = Date.now() - manualCapture.lastCapTime;
  if (elapsed < 500) { sendResponse({ ok: true, skipped: true }); return; }

  try {
    const dataUrl = await chrome.tabs.captureVisibleTab(null, { format: 'png' });
    manualCapture.lastCapTime = Date.now();
    manualCapture.seenScrollYs.push(scrollY);
    await mcSaveFrame({ dataUrl, scrollY });

    // Keep seenScrollYs in sync in session storage
    const stored = await chrome.storage.session.get('lensCapture').catch(() => ({}));
    if (stored.lensCapture) {
      stored.lensCapture.seenScrollYs = manualCapture.seenScrollYs;
      await chrome.storage.session.set({ lensCapture: stored.lensCapture }).catch(() => {});
    }

    const frames = await mcGetFrames();
    sendResponse({ ok: true, frameCount: frames.length });
  } catch (e) {
    sendResponse({ ok: false, error: e.message });
  }
}

async function handleEndManualCapture(msg, sendResponse) {
  await mcRestoreIfNeeded();
  const frames = await mcGetFrames();

  if (!manualCapture.active || frames.length === 0) {
    sendResponse({ success: false, error: 'No frames captured' });
    mcReset();
    return;
  }

  const { pageInfo, tabId } = manualCapture;
  mcReset();

  try {
    await chrome.action.setBadgeText({ text: '', tabId }).catch(() => {});

    frames.sort((a, b) => a.scrollY - b.scrollY);

    const { scrollHeight, viewportW, dpr } = pageInfo;
    const totalH = Math.ceil(scrollHeight * dpr);
    const totalW  = Math.ceil(viewportW   * dpr);
    const canvas  = new OffscreenCanvas(totalW, totalH);
    const ctx     = canvas.getContext('2d');

    for (const { dataUrl, scrollY } of frames) {
      const blob   = await (await fetch(dataUrl)).blob();
      const bitmap = await createImageBitmap(blob);
      ctx.drawImage(bitmap, 0, Math.round(scrollY * dpr));
      bitmap.close();
    }

    const finalBlob = await canvas.convertToBlob({ type: 'image/png' });
    const finalUrl  = await blobToDataUrl(finalBlob);

    sendResponse({
      success: true,
      dataUrl: finalUrl,
      width:   totalW,
      height:  totalH,
      frames:  frames.length,
    });
  } catch (e) {
    sendResponse({ success: false, error: e.message });
  }
}


// ─── Send to ArtikLens API ────────────────────────────────────────────────────

async function handleSendToArtikLens(msg, sendResponse) {
  const { url, browser } = msg;
  try {
    const res = await fetch('http://localhost:8000/api/page-extractor/extract', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, browser: browser || 'chrome', use_cookies: true }),
    });
    if (!res.ok) {
      const err = await res.json();
      sendResponse({ success: false, error: err.detail || 'API error' });
      return;
    }
    const data = await res.json();
    sendResponse({ success: true, data });
  } catch (e) {
    sendResponse({ success: false, error: `Could not reach ArtikLens API: ${e.message}` });
  }
}


// ─── Helpers ──────────────────────────────────────────────────────────────────

function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

async function execScript(tabId, func, args = []) {
  return chrome.scripting.executeScript({ target: { tabId }, func, args });
}

function blobToDataUrl(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve(reader.result);
    reader.onerror   = reject;
    reader.readAsDataURL(blob);
  });
}
