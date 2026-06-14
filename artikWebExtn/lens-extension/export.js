chrome.storage.session.get('lensExportHtml', ({ lensExportHtml }) => {
  if (!lensExportHtml) {
    document.body.textContent = 'No export data found. Go back and click Download as PDF again.';
    return;
  }
  // Replace the entire document with the saved HTML, then print
  document.open();
  document.write(lensExportHtml);
  document.close();
  setTimeout(() => window.print(), 800);
});
