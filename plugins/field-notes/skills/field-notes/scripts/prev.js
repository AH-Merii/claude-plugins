#!/usr/bin/env node
// Preview: render one or more SVGs side by side, each on a white card, to a PNG.
//
//   node prev.js <out.png> <a.svg> [b.svg ...]
//
// Pass the original icon first and the new drawing second for a before-vs-after sheet.
const fs = require('node:fs')
const { chromium } = require('playwright')

const [out, ...files] = process.argv.slice(2)
if (!out || files.length === 0) {
  console.error('usage: node prev.js <out.png> <a.svg> [b.svg ...]')
  process.exit(1)
}

const dataUrl = file => `data:image/svg+xml;base64,${fs.readFileSync(file).toString('base64')}`
const card = file =>
  `<div style="background:#fff;border:1px solid #ddd;border-radius:10px;padding:10px">` +
  `<img src="${dataUrl(file)}" style="width:440px;display:block"></div>`

;(async () => {
  const browser = await chromium.launch()
  try {
    const page = await browser.newPage({ deviceScaleFactor: 2 })
    await page.setContent(
      `<html><body style="margin:0;background:#f3f4f5">` +
        `<div id="sheet" style="display:inline-flex;gap:20px;padding:20px">${files.map(card).join('')}</div>` +
        `</body></html>`,
    )
    await page.waitForTimeout(500) // let the SVG filters settle
    await (await page.$('#sheet')).screenshot({ path: out })
  } finally {
    await browser.close()
  }
})()
