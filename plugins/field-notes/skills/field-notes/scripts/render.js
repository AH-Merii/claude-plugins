#!/usr/bin/env node
// inkwash: renders a line-and-wash sketch (Excalidraw elements) to a watercolour-style SVG.
//
//   node render.js <sketch.json> <out.svg> [--paper] [--px 400] [--seed 1]
//
// Input: an .excalidrawlib (first item) or a JSON object with an `elements` array.
//   freedraw elements  -> ink: pressure-sensitive pen strokes (perfect-freehand outline)
//   closed line shapes -> washes: watercolour layers (filled polygons with a fill colour)
//   ellipses           -> dots: splatter and granulation specks
// Output: a self-contained SVG. Filters do the "wet media" work that paint apps do:
//   diffusion  feTurbulence + feDisplacementMap make the wash edge bleed irregularly
//   wet edge   the rim of each wash (source minus its eroded self) is darkened: pigment pooling
//   granulation high-frequency noise thins the pigment in the paper's tooth
//   glazing    every wash multiplies over what is under it, so layers build like transparent paint
//   ink        a hair of displacement so the line reads as nib on paper, not vector
// Each wash picks one of several filter variants (different noise seeds) so no two edges match.
const fs = require('fs');
const { getStroke } = require('perfect-freehand');

const args = process.argv.slice(2);
const opt = (k, d) => { const i = args.indexOf(k); return i < 0 ? d : (args[i + 1] === undefined || args[i + 1].startsWith('--') ? true : args[i + 1]); };
const [inp, out] = args.filter(a => !a.startsWith('--') && !/^\d+$/.test(a));
if (!inp || !out) { console.error('usage: node render.js <sketch.json> <out.svg> [--paper] [--px 400] [--seed 1]'); process.exit(1); }
const PAPER = !!opt('--paper', false), PX = +opt('--px', 400), SEED = +opt('--seed', 1);

const raw = JSON.parse(fs.readFileSync(inp, 'utf8'));
const elements = raw.elements || (raw.libraryItems ? raw.libraryItems[0].elements : raw.library ? raw.library[0] : raw);
const els = elements.filter(e => !e.isDeleted);

const r = v => Math.round(v * 100) / 100;
const abs = e => (e.points || []).map(([x, y]) => [e.x + x, e.y + y]);

// ---- bounds
let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
for (const e of els) {
  const pts = e.type === 'ellipse' ? [[e.x, e.y], [e.x + e.width, e.y + e.height]] : abs(e);
  for (const [x, y] of pts) { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x); y1 = Math.max(y1, y); }
}
const PAD = 4; x0 -= PAD; y0 -= PAD; x1 += PAD; y1 += PAD;
const W = x1 - x0, H = y1 - y0;

// ---- geometry helpers
function inkPath(e) {
  // perfect-freehand drops outline points on very small strokes, so work at 10x and scale back
  const K = 10;
  const pts = abs(e).map(([x, y], i) => [x * K, y * K, (e.pressures && e.pressures[i]) ?? 0.5]);
  const size = Math.max(0.35, (e.strokeWidth || 1) * 4.25) * K;
  const precise = !!(e.customData && e.customData.precise); const flat = !!(e.customData && e.customData.flat); // flat: screen text and bars, even width with round ends // ruled marks: follow the points exactly, no pen lag
  const o = getStroke(pts, { size, thinning: precise ? 0.8 : 0.62, smoothing: precise ? 0.25 : 0.55, streamline: precise ? 0 : 0.35, simulatePressure: false, last: true,
    start: { taper: flat ? 0 : precise ? size * 0.6 : size * 1.5, cap: true }, end: { taper: flat ? 0 : precise ? size * 0.8 : size * 2.5, cap: true } });
  if (o.length < 3) return '';
  for (const q of o) { q[0] /= K; q[1] /= K; }
  let d = `M${r(o[0][0])} ${r(o[0][1])}`;
  for (let i = 1; i < o.length; i++) { const [a, b] = o[i], [c, f] = o[(i + 1) % o.length]; d += `Q${r(a)} ${r(b)} ${r((a + c) / 2)} ${r((b + f) / 2)}`; }
  return d + 'Z';
}
function smoothClosed(pts) { // Catmull-Rom through the points, as cubic beziers
  const P = pts.slice(); if (P.length > 2 && P[0][0] === P[P.length - 1][0] && P[0][1] === P[P.length - 1][1]) P.pop();
  const n = P.length; let d = `M${r(P[0][0])} ${r(P[0][1])}`;
  for (let i = 0; i < n; i++) {
    const p0 = P[(i - 1 + n) % n], p1 = P[i], p2 = P[(i + 1) % n], p3 = P[(i + 2) % n];
    const c1 = [p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6], c2 = [p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6];
    d += `C${r(c1[0])} ${r(c1[1])} ${r(c2[0])} ${r(c2[1])} ${r(p2[0])} ${r(p2[1])}`;
  }
  return d + 'Z';
}

// ---- filters
const VARIANTS = 5;
function washFilter(i) {
  const wet = i >= 3; // the last variants are wet-in-wet: wider bleed, softer body
  const s = SEED * 31 + i * 7, bf = (wet ? 0.05 + 0.01 * i : 0.08 + 0.025 * i).toFixed(3), scale = (wet ? 4.5 + 0.5 * i : 2.2 + 0.35 * i).toFixed(2), blur = wet ? 1.0 : 0.4;
  return `<filter id="w${i}" x="-60%" y="-60%" width="220%" height="220%" color-interpolation-filters="sRGB">
<feTurbulence type="fractalNoise" baseFrequency="${bf}" numOctaves="4" seed="${s}" result="t"/>
<feDisplacementMap in="SourceGraphic" in2="t" scale="${scale}" xChannelSelector="R" yChannelSelector="G" result="d"/>
<feGaussianBlur in="d" stdDeviation="${blur}" result="soft"/>
<feMorphology in="d" operator="erode" radius="0.75" result="er"/>
<feComposite in="d" in2="er" operator="out" result="rim"/>
<feGaussianBlur in="rim" stdDeviation="0.3" result="rimS"/>
<feComponentTransfer in="rimS" result="rimD"><feFuncA type="linear" slope="1.1"/></feComponentTransfer>
<feTurbulence type="fractalNoise" baseFrequency="1.4" numOctaves="2" seed="${s + 3}" result="g"/>
<feColorMatrix in="g" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 -0.8 1.08" result="gm"/>
<feComposite in="soft" in2="gm" operator="in" result="gran"/>
<feMerge><feMergeNode in="gran"/><feMergeNode in="rimD"/></feMerge>
</filter>`;
}
const defs = [];
for (let i = 0; i < VARIANTS; i++) defs.push(washFilter(i));
defs.push(`<filter id="crisp" x="-10%" y="-10%" width="120%" height="120%" color-interpolation-filters="sRGB">
<feTurbulence type="fractalNoise" baseFrequency="1.4" numOctaves="2" seed="${SEED * 31 + 40}" result="g"/>
<feColorMatrix in="g" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 -0.5 1.12" result="gm"/>
<feTurbulence type="fractalNoise" baseFrequency="0.35" numOctaves="2" seed="${SEED * 31 + 41}" result="t"/>
<feDisplacementMap in="SourceGraphic" in2="t" scale="0.35" xChannelSelector="R" yChannelSelector="G" result="d"/>
<feComposite in="d" in2="gm" operator="in"/>
</filter>`);
defs.push(`<filter id="ink" x="-5%" y="-5%" width="110%" height="110%">
<feTurbulence type="fractalNoise" baseFrequency="0.7" numOctaves="2" seed="${SEED + 5}" result="t"/>
<feDisplacementMap in="SourceGraphic" in2="t" scale="0.2" xChannelSelector="R" yChannelSelector="G"/>
</filter>`);
if (PAPER) defs.push(`<filter id="paper" x="0" y="0" width="100%" height="100%">
<feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="3" seed="${SEED + 9}" result="n"/>
<feColorMatrix in="n" type="matrix" values="0 0 0 0 0.94  0 0 0 0 0.93  0 0 0 0 0.9  0 0 0 -0.5 0.55"/>
</filter>`);

// ---- layers
const washes = [], dots = [], ink = [], over = [];
let wi = 0;
for (const e of els) {
  const op = (e.opacity ?? 100) / 100;
  const cd = e.customData || {};
  // customData.over: forms that stand in front of earlier ink go in a top layer, in document order
  const W_ = cd.over ? over : washes, D_ = cd.over ? over : dots, I_ = cd.over ? over : ink, IF = cd.over ? ' filter="url(#ink)"' : '';
  if (cd.knockout) { // paper-white backing that hides the lines behind a form
    W_.push(`<path d="M${abs(e).map(([x, y]) => r(x) + ' ' + r(y)).join('L')}Z" fill="${PAPER ? '#fbfaf6' : '#ffffff'}"/>`);
    continue;
  }
  if (e.type === 'freedraw') {
    const d = inkPath(e); if (d) I_.push(`<path d="${d}" fill="${e.strokeColor}" fill-opacity="${r(op)}"${IF}/>`);
  } else if (e.type === 'line' && e.backgroundColor && e.backgroundColor !== 'transparent' && e.customData && e.customData.crisp) {
    // precise fill: paint laid carefully inside the line (buttons, lamps, labels): no bleed, just paper grain
    W_.push(`<path d="M${abs(e).map(([x, y]) => r(x) + ' ' + r(y)).join('L')}Z" fill="${e.backgroundColor}" fill-opacity="${r(op)}" filter="url(#crisp)" style="mix-blend-mode:multiply"/>`);
  } else if (e.type === 'line' && e.backgroundColor && e.backgroundColor !== 'transparent') {
    // wash: pigment strength a bit higher than the flat preview, since edges and granulation thin it out
    W_.push(`<path d="${smoothClosed(abs(e))}" fill="${e.backgroundColor}" fill-opacity="${r(Math.min(1, op * 1.25))}" filter="url(#w${wi++ % VARIANTS})" style="mix-blend-mode:multiply"/>`);
  } else if (e.type === 'line') {
    I_.push(`<path${IF} d="M${abs(e).map(([x, y]) => r(x) + ' ' + r(y)).join('L')}" fill="none" stroke="${e.strokeColor}" stroke-opacity="${r(op)}" stroke-width="${r((e.strokeWidth || 1) * 0.6)}" stroke-linecap="round"/>`);
  } else if (e.type === 'ellipse') {
    D_.push(`<ellipse cx="${r(e.x + e.width / 2)}" cy="${r(e.y + e.height / 2)}" rx="${r(e.width / 2)}" ry="${r(e.height / 2)}" fill="${e.backgroundColor}" fill-opacity="${r(op)}" transform="rotate(${r((e.angle || 0) * 57.3)} ${r(e.x + e.width / 2)} ${r(e.y + e.height / 2)})"/>`);
  }
}

const px = PX, py = Math.round(PX * H / W);
const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${px}" height="${py}" viewBox="${r(x0)} ${r(y0)} ${r(W)} ${r(H)}">
<defs>
${defs.join('\n')}
</defs>
${PAPER ? `<rect x="${r(x0)}" y="${r(y0)}" width="${r(W)}" height="${r(H)}" fill="#fbfaf6"/><rect x="${r(x0)}" y="${r(y0)}" width="${r(W)}" height="${r(H)}" filter="url(#paper)"/>` : ''}
<g id="washes" style="isolation:isolate">
${washes.join('\n')}
</g>
<g id="dots" style="mix-blend-mode:multiply">
${dots.join('\n')}
</g>
<g id="ink" filter="url(#ink)">
${ink.join('\n')}
</g>
<g id="over">
${over.join('\n')}
</g>
</svg>
`;
fs.writeFileSync(out, svg);
console.log(`${out}: ${washes.length} washes, ${ink.length} ink strokes, ${dots.length} dots, ${over.length} in front, ${(svg.length / 1024).toFixed(0)} KB`);
