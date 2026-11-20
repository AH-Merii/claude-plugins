#!/usr/bin/env node
// Contact sheet: screenshot the #sheet element of a local HTML page to a PNG.
//
//   node sheet.js <out.png> <sheet.html>
//
// contact_sheet.py writes the page (its images are file:// URLs, so the page is opened as a file).
const { pathToFileURL } = require('node:url')
const path = require('node:path')
const { chromium } = require('playwright')

const [out, page] = process.argv.slice(2)
if (!out || !page) {
  console.error('usage: node sheet.js <out.png> <sheet.html>')
  process.exit(1)
}

;(async () => {
  const browser = await chromium.launch()
  try {
    const tab = await browser.newPage()
    await tab.goto(pathToFileURL(path.resolve(page)).href, { waitUntil: 'load' })
    await (await tab.$('#sheet')).screenshot({ path: out })
  } finally {
    await browser.close()
  }
})()
