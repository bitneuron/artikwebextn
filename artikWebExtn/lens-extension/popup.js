// ─── Lens Popup ───────────────────────────────────────────────────────────────

let capturedData   = null;  // extracted content
let screenshotUrl  = null;  // full-page screenshot dataURL
let currentTabId   = null;
let currentTabUrl  = null;
let activeResultTab = 'content'; // tracks which result tab is active

// ─── Init ─────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  currentTabId  = tab.id;
  currentTabUrl = tab.url;

  // Show truncated URL in header
  const urlEl = document.getElementById('page-url');
  try {
    const u = new URL(tab.url);
    urlEl.textContent = u.hostname + (u.pathname !== '/' ? u.pathname.slice(0, 30) : '');
    urlEl.title = tab.url;
  } catch {
    urlEl.textContent = tab.url?.slice(0, 40) || '—';
  }

  // Check if there's a pending selection result from a previous area-select
  const stored = await chrome.storage.local.get('lensSelectionResult');
  if (stored.lensSelectionResult) {
    const { dataUrl, rect, selectedText, timestamp } = stored.lensSelectionResult;
    // Only use if captured within last 60 seconds
    if (Date.now() - timestamp < 60_000) {
      await chrome.storage.local.remove('lensSelectionResult');
      await chrome.action.setBadgeText({ text: '', tabId: currentTabId });
      showSelectionResult(dataUrl, rect, selectedText);
    }
  }

  // Ensure API key is stored
  const { openaiKey } = await chrome.storage.local.get('openaiKey');
  if (!openaiKey) {
    // Set your OpenAI API key here on first run
    await chrome.storage.local.set({ openaiKey: '' });
  }

  // Wire up buttons
  document.getElementById('btn-extract').addEventListener('click', doExtract);
  document.getElementById('btn-screenshot').addEventListener('click', doScreenshot);
  document.getElementById('btn-select').addEventListener('click', doSelectArea);
  document.getElementById('btn-artiklens').addEventListener('click', openInArtikLens);
  document.getElementById('btn-copy-all').addEventListener('click', copyAllText);
  document.getElementById('btn-dl-img').addEventListener('click', downloadScreenshot);
  document.getElementById('btn-copy-img').addEventListener('click', copyScreenshot);
  document.getElementById('btn-ask-ai').addEventListener('click', toggleAiPanel);
  document.getElementById('btn-ai-close').addEventListener('click', toggleAiPanel);
  document.getElementById('btn-ai-send').addEventListener('click', sendToOpenAI);
  document.getElementById('btn-open-chatgpt').addEventListener('click', openInChatGPT);
  document.getElementById('btn-dl-pdf').addEventListener('click', downloadAsPDF);

  // Tab switching
  document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => switchTab(tab.dataset.tab));
  });

  // Copy buttons
  document.querySelectorAll('.copy-btn').forEach(btn => {
    btn.addEventListener('click', () => handleCopy(btn.dataset.copy));
  });
});


// ─── Extract Content ──────────────────────────────────────────────────────────

async function doExtract() {
  setAllButtonsDisabled(true);
  showStatus('Extracting page content...', 'info');
  try {
    const [{ result }] = await chrome.scripting.executeScript({
      target: { tabId: currentTabId },
      func: () => {
        // Re-run extractContent from content.js if available
        if (typeof extractContent === 'function') return extractContent();
        return null;
      },
    });

    if (!result) {
      // Fall back: send message to content script
      const data = await sendToContent(currentTabId, { action: 'extractContent' });
      capturedData = data;
    } else {
      capturedData = result;
    }

    renderContent(capturedData);
    showStatus(`Extracted: ${capturedData.headings.length} headings · ${capturedData.paragraphs.length} paragraphs · ${capturedData.images.length} images · ${capturedData.links.length} links`, 'success');
    showResults();
    switchTab('content');
  } catch (e) {
    showStatus('Extraction failed: ' + e.message, 'error');
  } finally {
    setAllButtonsDisabled(false);
  }
}

function renderContent(data) {
  // Headings
  const headingsList = document.getElementById('headings-list');
  document.getElementById('heading-label').textContent = `Headings (${data.headings.length})`;
  headingsList.innerHTML = '';
  data.headings.slice(0, 40).forEach(h => {
    const el = document.createElement('div');
    el.className = `heading-item h${h.level}`;
    el.innerHTML = `<span class="heading-level">H${h.level}</span><span class="heading-text" title="${esc(h.text)}">${esc(h.text)}</span>`;
    headingsList.appendChild(el);
  });
  if (data.headings.length === 0) headingsList.innerHTML = '<p style="color:#475569;font-size:11px">No headings found</p>';

  // Text
  document.getElementById('text-preview').textContent = data.text?.slice(0, 800) + (data.text?.length > 800 ? '…' : '') || 'No text';

  // Images
  document.getElementById('img-count').textContent = data.images.length;
  const grid = document.getElementById('images-grid');
  grid.innerHTML = '';
  data.images.slice(0, 30).forEach(img => {
    const el = document.createElement('div');
    el.className = 'img-thumb';
    el.innerHTML = `<img src="${esc(img.src)}" alt="${esc(img.alt)}" loading="lazy" onerror="this.parentNode.style.display='none'"/><div class="img-open">Open</div>`;
    el.querySelector('.img-open').addEventListener('click', () => chrome.tabs.create({ url: img.src }));
    grid.appendChild(el);
  });
  if (data.images.length === 0) grid.innerHTML = '<p style="color:#475569;font-size:11px">No images found</p>';

  // Links
  document.getElementById('link-count').textContent = data.links.length;
  const linksList = document.getElementById('links-list');
  linksList.innerHTML = '';
  data.links.slice(0, 80).forEach(link => {
    const el = document.createElement('a');
    el.className = 'link-item';
    el.href = link.url;
    el.target = '_blank';
    el.rel = 'noopener noreferrer';
    el.innerHTML = `<div class="link-text">${esc(link.text || link.url)}</div><div class="link-url">${esc(link.url)}</div>`;
    linksList.appendChild(el);
  });
  if (data.links.length === 0) linksList.innerHTML = '<p style="color:#475569;font-size:11px">No links found</p>';
}


// ─── Screenshot (current viewport) ───────────────────────────────────────────

async function doScreenshot() {
  setAllButtonsDisabled(true);
  showStatus('Capturing screenshot…', 'info');
  try {
    const response = await chrome.runtime.sendMessage({ action: 'screenshot' });
    if (!response.success) throw new Error(response.error);
    screenshotUrl = response.dataUrl;
    renderScreenshot(screenshotUrl);
    showStatus('Screenshot captured', 'success');
    showResults();
    switchTab('screenshot');
  } catch (e) {
    showStatus('Screenshot failed: ' + e.message, 'error');
  } finally {
    setAllButtonsDisabled(false);
  }
}

function renderScreenshot(dataUrl, label) {
  const area = document.getElementById('screenshot-area');
  area.innerHTML = `<img src="${dataUrl}" alt="Page screenshot" style="cursor:zoom-in" />`;
  area.querySelector('img').addEventListener('click', () => {
    const win = window.open();
    win.document.write(`<img src="${dataUrl}" style="max-width:100%">`);
  });
  document.getElementById('shot-actions').classList.remove('hidden');
}


// ─── Select Area ──────────────────────────────────────────────────────────────

async function doSelectArea() {
  showStatus('Click and drag on the page to select an area. Press Esc to cancel.', 'info');
  try {
    // Inject content script in case the tab was open before the extension loaded
    await chrome.scripting.executeScript({
      target: { tabId: currentTabId },
      files: ['content.js'],
    }).catch(() => {}); // ignore if already injected (guard in content.js handles dedup)
    await sendToContent(currentTabId, { action: 'startSelection' });
    setTimeout(() => window.close(), 600);
  } catch (e) {
    showStatus('Could not activate selection: ' + e.message, 'error');
  }
}

function showSelectionResult(dataUrl, rect, selectedText) {
  screenshotUrl = dataUrl;

  const area = document.getElementById('screenshot-area');
  area.innerHTML = `<img src="${dataUrl}" alt="Selected area" style="max-width:100%;max-height:220px;cursor:zoom-in"/>`;
  area.querySelector('img').addEventListener('click', () => {
    const win = window.open();
    win.document.write(`<img src="${dataUrl}" style="max-width:100%">`);
  });
  document.getElementById('shot-actions').classList.remove('hidden');

  let statusText = `Area selected: ${rect.width}×${rect.height}px`;
  if (selectedText) statusText += ` · "${selectedText.slice(0, 60)}${selectedText.length > 60 ? '…' : ''}"`;
  showStatus(statusText, 'success');
  showResults();
  switchTab('screenshot');

  if (selectedText) {
    // Also show extracted text from the selected region
    capturedData = capturedData || {};
    capturedData._selectionText = selectedText;
  }
}


// ─── Open in ArtikLens ────────────────────────────────────────────────────────

async function openInArtikLens() {
  // Open ArtikLens with the URL pre-filled
  const artiklensUrl = `http://localhost:3000/artiklens`;
  await chrome.tabs.create({ url: artiklensUrl });

  // Also trigger extraction via the API
  showStatus('Opening ArtikLens...', 'info');
  const res = await chrome.runtime.sendMessage({
    action: 'sendToArtikLens',
    url: currentTabUrl,
    browser: 'chrome',
  });

  if (res.success) {
    showStatus('Sent to ArtikLens successfully', 'success');
  } else {
    showStatus(`ArtikLens: ${res.error}`, 'error');
  }
}


// ─── Download / Copy screenshot ───────────────────────────────────────────────

function downloadScreenshot() {
  if (!screenshotUrl) return;
  const a = document.createElement('a');
  a.href = screenshotUrl;
  a.download = `lens-capture-${Date.now()}.png`;
  a.click();
}

async function copyScreenshot() {
  if (!screenshotUrl) return;
  try {
    const blob = await (await fetch(screenshotUrl)).blob();
    await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]);
    showStatus('Image copied to clipboard', 'success');
  } catch (e) {
    showStatus('Copy failed: ' + e.message, 'error');
  }
}

function copyAllText() {
  if (!capturedData) return;
  let text = `${capturedData.title}\n${capturedData.url}\n\n`;
  if (capturedData.headings?.length) {
    text += capturedData.headings.map(h => `${'#'.repeat(h.level)} ${h.text}`).join('\n') + '\n\n';
  }
  text += capturedData.text || '';
  navigator.clipboard.writeText(text);
  showStatus('All text copied to clipboard', 'success');
}

function handleCopy(type) {
  if (!capturedData) return;
  let text = '';
  if (type === 'headings') text = capturedData.headings.map(h => `${'#'.repeat(h.level)} ${h.text}`).join('\n');
  if (type === 'text')     text = capturedData.text || '';
  navigator.clipboard.writeText(text);
  showStatus('Copied!', 'success');
  setTimeout(() => hideStatus(), 1500);
}


// ─── OpenAI integration ───────────────────────────────────────────────────────

function toggleAiPanel() {
  document.getElementById('ai-panel').classList.toggle('hidden');
}

async function downloadAsPDF() {
  const question  = document.getElementById('ai-question').value.trim();
  const responseText = document.getElementById('ai-response').textContent;
  const pageTitle = capturedData?.title || currentTabUrl;
  const pageText  = capturedData?.text?.slice(0, 12000) || '(no extracted text — use Extract Content first)';
  const now       = new Date().toLocaleString();

  const screenshotSection = screenshotUrl
    ? `<h2>Page Screenshot</h2>
       <img src="${screenshotUrl}" style="max-width:100%;border:1px solid #ddd;border-radius:4px;margin-bottom:8px;display:block;" />`
    : '<p style="color:#999;font-size:12px">(no screenshot — take a screenshot before asking next time)</p>';

  const html = `<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Lens Export — ${esc(pageTitle)}</title>
<style>
  body { font-family: Georgia, serif; max-width: 800px; margin: 40px auto; padding: 0 24px; color: #1a1a1a; line-height: 1.7; }
  h1 { font-size: 20px; border-bottom: 2px solid #4f46e5; padding-bottom: 8px; color: #1e1b4b; }
  h2 { font-size: 15px; color: #3730a3; margin-top: 28px; }
  .meta { font-size: 12px; color: #666; margin-bottom: 24px; }
  .box { background: #f5f5ff; border-left: 4px solid #4f46e5; padding: 12px 16px; border-radius: 4px; white-space: pre-wrap; font-size: 13px; }
  .answer { background: #f0fdf4; border-left: 4px solid #16a34a; padding: 12px 16px; border-radius: 4px; white-space: pre-wrap; font-size: 13px; }
  .content { font-size: 12px; color: #444; white-space: pre-wrap; }
  @media print { body { margin: 20px; } img { max-width: 100%; } }
</style>
</head>
<body>
<h1>Lens Page Export</h1>
<div class="meta">Exported: ${now}<br>URL: <a href="${esc(currentTabUrl)}">${esc(currentTabUrl)}</a></div>

${screenshotSection}

<h2>Question</h2>
<div class="box">${esc(question || '(no question)')}</div>

<h2>AI Response</h2>
<div class="answer">${esc(responseText)}</div>

<h2>Full Page Content</h2>
<div class="content">${esc(pageText)}</div>
</body>
</html>`;

  // Save HTML to session storage, then open the export page
  // (blob URLs become inaccessible when the popup closes)
  await chrome.storage.session.set({ lensExportHtml: html });
  chrome.tabs.create({ url: chrome.runtime.getURL('export.html') });
}

function openInChatGPT() {
  const question = document.getElementById('ai-question').value.trim();
  const ctx = document.querySelector('input[name="ai-ctx"]:checked')?.value || 'text';

  // Build the full message with page context
  let msg = '';
  if (ctx === 'text' && capturedData?.text) {
    const title   = capturedData.title || currentTabUrl;
    const snippet = capturedData.text.slice(0, 6000);
    msg = `Page: ${title}\nURL: ${currentTabUrl}\n\n${snippet}\n\n---\n${question || 'Summarize this page.'}`;
  } else {
    msg = `Page URL: ${currentTabUrl}\n\n${question || 'What can you tell me about this page?'}`;
  }

  const url = 'https://chatgpt.com/?q=' + encodeURIComponent(msg);
  chrome.tabs.create({ url });
}

async function sendToOpenAI() {
  const { openaiKey: key } = await chrome.storage.local.get('openaiKey');
  const question = document.getElementById('ai-question').value.trim();
  if (!question) { showStatus('Enter a question first', 'error'); return; }
  const responseEl = document.getElementById('ai-response');
  responseEl.textContent = 'Thinking…';
  responseEl.className = 'ai-response loading';
  responseEl.classList.remove('hidden');
  document.getElementById('btn-ai-send').disabled = true;

  try {
    const content = [];

    if (activeResultTab === 'screenshot') {
      // Screenshot tab — send the captured image
      if (!screenshotUrl) { throw new Error('No screenshot captured. Use Screenshot or Select Area first.'); }
      content.push({ type: 'image_url', image_url: { url: screenshotUrl } });
      content.push({ type: 'text', text: `URL: ${currentTabUrl}\n\n---\n${question}` });

    } else if (activeResultTab === 'images') {
      // Images tab — send image URLs as a list + question
      if (!capturedData?.images?.length) { throw new Error('No images found. Extract Content first.'); }
      const imgList = capturedData.images.slice(0, 50)
        .map((img, i) => `${i + 1}. ${img.alt ? `[${img.alt}] ` : ''}${img.src}`).join('\n');
      content.push({ type: 'text', text: `Page: ${capturedData.title || ''}\nURL: ${currentTabUrl}\n\nImages on this page:\n${imgList}\n\n---\n${question}` });

    } else if (activeResultTab === 'links') {
      // Links tab — send link list + question
      if (!capturedData?.links?.length) { throw new Error('No links found. Extract Content first.'); }
      const linkList = capturedData.links.slice(0, 80)
        .map((l, i) => `${i + 1}. ${l.text ? `${l.text} — ` : ''}${l.url}`).join('\n');
      content.push({ type: 'text', text: `Page: ${capturedData.title || ''}\nURL: ${currentTabUrl}\n\nLinks on this page:\n${linkList}\n\n---\n${question}` });

    } else {
      // Content tab (default) — send headings + main text
      if (!capturedData) { throw new Error('No content extracted. Use Extract Content first.'); }
      const headings = capturedData.headings?.map(h => `${'#'.repeat(h.level)} ${h.text}`).join('\n') || '';
      const body = capturedData.text?.slice(0, 6000) || '';
      content.push({ type: 'text', text: `Page: ${capturedData.title || ''}\nURL: ${currentTabUrl}\n\n${headings}\n\n${body}\n\n---\n${question}` });
    }

    const messages = [{ role: 'user', content }];
    // Model versions — keep in sync with shared/models.json (extension is a
    // standalone package; it can't import the app's config module).
    const model = activeResultTab === 'screenshot' ? 'gpt-5' : 'gpt-5-mini';

    const res = await fetch('https://api.openai.com/v1/chat/completions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${key}` },
      body: JSON.stringify({ model, messages, max_completion_tokens: 1500, reasoning_effort: 'minimal' }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error?.message || `API error ${res.status}`);
    }

    const data = await res.json();
    const reply = data.choices?.[0]?.message?.content || '(no response)';
    responseEl.textContent = reply;
    responseEl.className = 'ai-response';
    document.getElementById('btn-dl-pdf').classList.remove('hidden');
  } catch (e) {
    responseEl.textContent = 'Error: ' + e.message;
    responseEl.className = 'ai-response';
  } finally {
    document.getElementById('btn-ai-send').disabled = false;
  }
}


// ─── UI helpers ───────────────────────────────────────────────────────────────

function showStatus(msg, type = 'info') {
  const el = document.getElementById('status');
  el.textContent = msg;
  el.className = `status ${type}`;
  el.classList.remove('hidden');
}
function hideStatus() {
  document.getElementById('status').classList.add('hidden');
}
function showProgress(text = 'Working...') {
  document.getElementById('progress-text').textContent = text;
  document.getElementById('progress').classList.remove('hidden');
  animateProgress();
}
function hideProgress() {
  document.getElementById('progress').classList.add('hidden');
}
function animateProgress() {
  const fill = document.getElementById('progress-fill');
  let w = 0;
  const iv = setInterval(() => {
    w = Math.min(w + Math.random() * 8, 90);
    fill.style.width = w + '%';
    if (!document.getElementById('progress').classList.contains('hidden') === false) clearInterval(iv);
  }, 200);
}
function showResults() {
  document.getElementById('results').classList.remove('hidden');
  document.getElementById('footer').classList.remove('hidden');
}
function switchTab(name) {
  activeResultTab = name;
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === name));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.add('hidden'));
  document.getElementById(`tab-${name}`)?.classList.remove('hidden');
}
function setAllButtonsDisabled(val) {
  ['btn-extract','btn-screenshot','btn-select'].forEach(id => {
    document.getElementById(id).disabled = val;
  });
}
function esc(str) {
  return (str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function sendToContent(tabId, msg) {
  return new Promise((resolve, reject) => {
    chrome.tabs.sendMessage(tabId, msg, (res) => {
      if (chrome.runtime.lastError) reject(new Error(chrome.runtime.lastError.message));
      else resolve(res);
    });
  });
}
