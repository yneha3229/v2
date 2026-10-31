#!/usr/bin/env node
// Render a self-contained Proofroom HTML report to an A4 PDF with Playwright's Chromium.
// Usage: node render_pdf.js <input.html> <output.pdf> [footer text]
// The footer text defaults to <meta name="proofroom-footer" content="..."> in the page.
// Exit codes: 0 ok, 2 usage, 3 playwright missing, 1 render failure.
'use strict';
const path = require('path');
const { pathToFileURL } = require('url');

let chromium;
try {
  ({ chromium } = require('playwright'));
} catch (e) {
  console.error('PROOFROOM_NO_PLAYWRIGHT: ' + e.message.split('\n')[0]);
  process.exit(3);
}

const esc = (s) => String(s).replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

(async () => {
  const [htmlPath, pdfPath, footerArg] = process.argv.slice(2);
  if (!htmlPath || !pdfPath) {
    console.error('usage: render_pdf.js <input.html> <output.pdf> [footer]');
    process.exit(2);
  }
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage();
    await page.goto(pathToFileURL(path.resolve(htmlPath)).href, { waitUntil: 'load' });
    await page.emulateMedia({ media: 'print' });
    const footer = footerArg || await page.evaluate(() => {
      const m = document.querySelector('meta[name="proofroom-footer"]');
      return m ? m.content : 'Proofroom';
    });
    const footerTemplate =
      '<div style="width:100%;font-size:7px;font-family:Inter,Helvetica,Arial,sans-serif;' +
      'color:#6b6a65;padding:0 14mm;display:flex;justify-content:space-between;">' +
      `<span>${esc(footer)}</span>` +
      '<span>page <span class="pageNumber"></span> of <span class="totalPages"></span></span></div>';
    await page.pdf({
      path: pdfPath,
      format: 'A4',
      printBackground: true,
      displayHeaderFooter: true,
      headerTemplate: '<span></span>',
      footerTemplate,
      preferCSSPageSize: true,
    });
  } finally {
    await browser.close();
  }
})().catch((e) => {
  console.error('PROOFROOM_RENDER_FAILED: ' + ((e && e.stack) || e));
  process.exit(1);
});
