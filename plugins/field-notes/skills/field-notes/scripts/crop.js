#!/usr/bin/env node
// Crop: zoom into part of a rendered SVG, in world coordinates, and save it 900 px wide.
//
//   node crop.js <drawing.svg> <out.png> X Y W H
//
// X Y W H are in the same units as the SVG's viewBox (the body file's coordinates).
const fs = require('node:fs')
const { chromium } = require('playwright')

const [svgFile, out, ...box] = process.argv.slice(2)
const [x, y, w, h] = box.map(Number)
if (!svgFile || !out || box.length !== 4 || [x, y, w, h].some(Number.isNaN) || w <= 0 || h <= 0) {
  console.error('usage: node crop.js <drawing.svg> <out.png> X Y W H')
  process.exit(1)
}

const width = 900
const height = Math.round((width * h) / w)
const svg = fs
  .readFileSync(svgFile, 'utf8')
  .replace(/viewBox="[^"]*"/, `viewBox="${x} ${y} ${w} ${h}"`)
  .replace(/width="\d+" height="\d+"/, `width="${width}" height="${height}"`)

;(async () => {
  const browser = await chromium.launch()
  try {
    const page = await browser.newPage({ viewport: { width, height } })
    await page.setContent(`<html><body style="margin:0;background:#fff">${svg}</body></html>`)
    await (await page.$('svg')).screenshot({ path: out })
  } finally {
    await browser.close()
  }
})()
