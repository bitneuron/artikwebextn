// ─── Lens Content Script ──────────────────────────────────────────────────────
// Runs on every page. Extracts content and handles area-selection overlay.
// Guard against duplicate injection (programmatic injection on tabs that
// were open before the extension was installed/reloaded).
if (!window.__lensContentLoaded) {
  window.__lensContentLoaded = true;

// ─── Message listener ───────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === 'extractContent') {
    sendResponse(extractContent());
    return true;
  }
  if (msg.action === 'startSelection') {
    startAreaSelection();
    sendResponse({ started: true });
    return true;
  }
  if (msg.action === 'getPageInfo') {
    sendResponse({
      scrollHeight: Math.max(document.body.scrollHeight, document.documentElement.scrollHeight),
      scrollWidth:  Math.max(document.body.scrollWidth,  document.documentElement.scrollWidth),
      viewportH:    window.innerHeight,
      viewportW:    window.innerWidth,
      dpr:          window.devicePixelRatio || 1,
    });
    return true;
  }
  if (msg.action === 'startScrollCapture') {
    window.__lensCapture?.start();
    sendResponse({ ok: true });
    return true;
  }
  if (msg.action === 'stopScrollCapture') {
    window.__lensCapture?.stop();
    sendResponse({ ok: true });
    return true;
  }
});

} // end guard

// ─── Scroll capture listener ──────────────────────────────────────────────────
// Stored on window so it survives multiple content.js injections and is
// callable from chrome.scripting.executeScript in any execution context.

if (!window.__lensCapture) {
  window.__lensCapture = { active: false, timer: null, heartbeat: null };

  window.__lensCapture._onScroll = function () {
    if (!window.__lensCapture.active) return;
    clearTimeout(window.__lensCapture.timer);
    window.__lensCapture.timer = setTimeout(() => {
      chrome.runtime.sendMessage({ action: 'scrollCapture', scrollY: window.scrollY })
        .catch(() => {});
    }, 200);
  };

  window.__lensCapture.start = function () {
    window.__lensCapture.active = true;
    window.addEventListener('scroll', window.__lensCapture._onScroll, { passive: true });
    // Heartbeat every 20s keeps the service worker alive
    clearInterval(window.__lensCapture.heartbeat);
    window.__lensCapture.heartbeat = setInterval(() => {
      chrome.runtime.sendMessage({ action: 'keepAlive' }).catch(() => {});
    }, 20000);
    return true;
  };

  window.__lensCapture.stop = function () {
    window.__lensCapture.active = false;
    window.removeEventListener('scroll', window.__lensCapture._onScroll);
    clearTimeout(window.__lensCapture.timer);
    clearInterval(window.__lensCapture.heartbeat);
    return true;
  };
}


// ─── Content extraction ───────────────────────────────────────────────────────

function extractContent() {
  const result = {
    url:       window.location.href,
    title:     document.title,
    text:      '',
    headings:  [],
    paragraphs:[],
    links:     [],
    images:    [],
    tables:    [],
    lists:     [],
    metadata:  {},
    pageH:     Math.max(document.body.scrollHeight, document.documentElement.scrollHeight),
    pageW:     Math.max(document.body.scrollWidth,  document.documentElement.scrollWidth),
    viewportH: window.innerHeight,
    viewportW: window.innerWidth,
  };

  // Metadata
  const metaTags = {
    description: 'meta[name="description"]',
    keywords:    'meta[name="keywords"]',
    author:      'meta[name="author"]',
    ogTitle:     'meta[property="og:title"]',
    ogDesc:      'meta[property="og:description"]',
    ogImage:     'meta[property="og:image"]',
  };
  for (const [key, sel] of Object.entries(metaTags)) {
    const el = document.querySelector(sel);
    if (el) result.metadata[key] = el.content || el.getAttribute('content') || '';
  }

  // Headings
  document.querySelectorAll('h1,h2,h3,h4,h5,h6').forEach(h => {
    const text = h.innerText.trim();
    if (text) result.headings.push({ level: parseInt(h.tagName[1]), text });
  });

  // Paragraphs
  document.querySelectorAll('p').forEach(p => {
    const text = p.innerText.trim();
    if (text.length > 20) result.paragraphs.push(text);
  });

  // Links
  const seenLinks = new Set();
  document.querySelectorAll('a[href]').forEach(a => {
    const url = a.href;
    if (!url || url.startsWith('javascript:') || seenLinks.has(url)) return;
    seenLinks.add(url);
    result.links.push({ text: (a.innerText || a.title || '').trim(), url });
  });

  // Images
  document.querySelectorAll('img').forEach(img => {
    const src = img.src || img.dataset.src || img.dataset.lazySrc || '';
    if (src && !src.startsWith('data:')) {
      result.images.push({ src, alt: img.alt || '', width: img.naturalWidth, height: img.naturalHeight });
    }
  });

  // Tables
  document.querySelectorAll('table').forEach(table => {
    const rows = [];
    table.querySelectorAll('tr').forEach(tr => {
      const cells = [...tr.querySelectorAll('td,th')].map(td => td.innerText.trim());
      if (cells.length) rows.push(cells);
    });
    if (rows.length) result.tables.push(rows);
  });

  // Lists
  document.querySelectorAll('ul,ol').forEach(lst => {
    const items = [...lst.querySelectorAll(':scope > li')]
      .map(li => li.innerText.trim())
      .filter(Boolean);
    if (items.length) result.lists.push({ type: lst.tagName === 'OL' ? 'ordered' : 'unordered', items });
  });

  // Main text (cleaned)
  const clone = document.body.cloneNode(true);
  clone.querySelectorAll('script,style,nav,footer,header,aside,noscript,iframe').forEach(el => el.remove());
  const mainEl = clone.querySelector('main,article,[id*="content"],[id*="main"],[class*="content"],[class*="main"]') || clone;
  result.text = mainEl.innerText.replace(/\n{3,}/g, '\n\n').trim();

  return result;
}


// ─── Area selection overlay ───────────────────────────────────────────────────

function startAreaSelection() {
  // Clean up any existing overlay
  document.getElementById('__lens_overlay__')?.remove();
  document.getElementById('__lens_sel_box__')?.remove();
  document.getElementById('__lens_instructions__')?.remove();

  const dpr = window.devicePixelRatio || 1;

  // Dim overlay
  const overlay = document.createElement('div');
  overlay.id = '__lens_overlay__';
  overlay.style.cssText = `
    position: fixed !important;
    inset: 0 !important;
    background: rgba(0,0,0,0.35) !important;
    z-index: 2147483646 !important;
    cursor: crosshair !important;
  `;

  // Dashed selection rectangle
  const selBox = document.createElement('div');
  selBox.id = '__lens_sel_box__';
  selBox.style.cssText = `
    position: fixed !important;
    border: 2px dashed #6366f1 !important;
    background: rgba(99,102,241,0.08) !important;
    box-shadow: 0 0 0 1px rgba(99,102,241,0.4) !important;
    pointer-events: none !important;
    display: none !important;
    z-index: 2147483647 !important;
  `;

  // Instructions banner
  const instr = document.createElement('div');
  instr.id = '__lens_instructions__';
  instr.style.cssText = `
    position: fixed !important;
    top: 16px !important;
    left: 50% !important;
    transform: translateX(-50%) !important;
    background: #1e1b4b !important;
    color: #e0e7ff !important;
    padding: 8px 20px !important;
    border-radius: 99px !important;
    font-size: 13px !important;
    font-family: system-ui, sans-serif !important;
    font-weight: 500 !important;
    z-index: 2147483647 !important;
    pointer-events: none !important;
    box-shadow: 0 4px 20px rgba(0,0,0,0.3) !important;
    white-space: nowrap !important;
  `;
  instr.textContent = 'Lens  ·  Drag to select an area  ·  Esc to cancel';

  // Size label
  const label = document.createElement('div');
  label.style.cssText = `
    position: fixed !important;
    background: #4f46e5 !important;
    color: white !important;
    font-size: 11px !important;
    font-family: monospace !important;
    padding: 2px 6px !important;
    border-radius: 4px !important;
    pointer-events: none !important;
    display: none !important;
    z-index: 2147483647 !important;
  `;

  document.body.append(overlay, selBox, instr, label);

  // Forward wheel events so the user can scroll before dragging
  overlay.addEventListener('wheel', e => {
    window.scrollBy({ top: e.deltaY, left: e.deltaX, behavior: 'instant' });
  }, { passive: true });

  let startX = 0, startY = 0, startScrollY = 0, dragging = false;
  let autoScrollRAF = null;
  let lastMouseY = 0;

  function cleanup() {
    if (autoScrollRAF) { cancelAnimationFrame(autoScrollRAF); autoScrollRAF = null; }
    overlay.remove(); selBox.remove(); instr.remove(); label.remove();
    document.removeEventListener('keydown', onKeyDown);
  }

  function onKeyDown(e) {
    if (e.key === 'Escape') {
      cleanup();
      chrome.runtime.sendMessage({ action: 'selectionCancelled' });
    }
  }

  // Auto-scroll when dragging near top/bottom viewport edge
  const EDGE_ZONE = 80;   // px from edge that triggers scroll
  const MAX_SPEED = 18;   // px per frame

  function autoScroll() {
    if (!dragging) return;
    const vh = window.innerHeight;
    let speed = 0;
    if (lastMouseY < EDGE_ZONE)       speed = -MAX_SPEED * (1 - lastMouseY / EDGE_ZONE);
    else if (lastMouseY > vh - EDGE_ZONE) speed = MAX_SPEED * (1 - (vh - lastMouseY) / EDGE_ZONE);
    if (speed !== 0) window.scrollBy(0, speed);
    autoScrollRAF = requestAnimationFrame(autoScroll);
  }

  overlay.addEventListener('mousedown', e => {
    e.preventDefault();
    startX = e.clientX;
    startY = e.clientY;
    startScrollY = window.scrollY;
    lastMouseY = e.clientY;
    dragging = true;
    selBox.style.display = 'block';
    selBox.style.left   = startX + 'px';
    selBox.style.top    = startY + 'px';
    selBox.style.width  = '0';
    selBox.style.height = '0';
    autoScrollRAF = requestAnimationFrame(autoScroll);
  });

  overlay.addEventListener('mousemove', e => {
    if (!dragging) return;
    lastMouseY = e.clientY;

    // Adjust startY for any scrolling that happened since drag began
    const scrollDelta = window.scrollY - startScrollY;
    const adjStartY = startY - scrollDelta;

    const x = Math.min(e.clientX, startX);
    const y = Math.min(e.clientY, adjStartY);
    const w = Math.abs(e.clientX - startX);
    const h = Math.abs(e.clientY - adjStartY);

    selBox.style.left   = x + 'px';
    selBox.style.top    = y + 'px';
    selBox.style.width  = w + 'px';
    selBox.style.height = h + 'px';

    label.textContent = `${w} × ${h}`;
    label.style.display = 'block';
    label.style.left = (x + w + 6) + 'px';
    label.style.top  = (y + h + 6) + 'px';
  });

  overlay.addEventListener('mouseup', e => {
    if (!dragging) return;
    dragging = false;
    if (autoScrollRAF) { cancelAnimationFrame(autoScrollRAF); autoScrollRAF = null; }

    const scrollDelta = window.scrollY - startScrollY;
    const adjStartY = startY - scrollDelta;

    const rect = {
      x:      Math.round(Math.min(e.clientX, startX)),
      y:      Math.round(Math.min(e.clientY, adjStartY)),
      width:  Math.round(Math.abs(e.clientX - startX)),
      height: Math.round(Math.abs(e.clientY - adjStartY)),
    };

    cleanup();

    if (rect.width < 5 || rect.height < 5) {
      chrome.runtime.sendMessage({ action: 'selectionCancelled' });
      return;
    }

    const selectedText = getTextInRect(rect);

    chrome.runtime.sendMessage({
      action: 'areaSelected',
      rect,
      dpr,
      selectedText,
    });
  });

  document.addEventListener('keydown', onKeyDown);
}


// ─── Get text content within a screen rect ───────────────────────────────────

function getTextInRect(rect) {
  const elements = document.elementsFromPoint(
    rect.x + rect.width / 2,
    rect.y + rect.height / 2
  );

  // Walk elements in rect and collect visible text
  const seen = new Set();
  const texts = [];

  const walker = document.createTreeWalker(
    document.body,
    NodeFilter.SHOW_TEXT,
    {
      acceptNode(node) {
        if (!node.textContent.trim()) return NodeFilter.FILTER_REJECT;
        const range = document.createRange();
        range.selectNode(node);
        const r = range.getBoundingClientRect();
        if (
          r.right  >= rect.x &&
          r.left   <= rect.x + rect.width &&
          r.bottom >= rect.y &&
          r.top    <= rect.y + rect.height
        ) return NodeFilter.FILTER_ACCEPT;
        return NodeFilter.FILTER_REJECT;
      }
    }
  );

  let node;
  while ((node = walker.nextNode())) {
    const text = node.textContent.trim();
    if (text && !seen.has(text)) {
      seen.add(text);
      texts.push(text);
    }
  }

  return texts.join(' ');
}
