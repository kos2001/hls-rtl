/**
 * Responsive gate for the workbench shell.
 *
 * Browser zoom shrinks the CSS viewport, so resizing the viewport is the
 * faithful way to reproduce it. Do NOT test with the CSS `zoom` property: it
 * scales boxes without moving the media queries, and reports failures that real
 * zoom never hits (and hides ones it does).
 *
 * Fails if, at any size, the shell overflows the viewport, the page itself
 * scrolls, the work area collapses, or a side dock degrades to a sliver instead
 * of hiding cleanly.
 *
 * Usage: start the api-server, then
 *   node frontend/scripts/responsive-check.mjs
 *   WORKBENCH_URL=http://127.0.0.1:5173/ node frontend/scripts/responsive-check.mjs
 */
// Real-viewport responsive sweep. Browser zoom shrinks the CSS viewport, so
// resizing the viewport is the faithful way to reproduce it — CSS `zoom` does
// not move the media queries and reports failures that real zoom never hits.
// Playwright is not a dependency of this project — the check is a manual gate,
// not part of `npm run build`. Resolve it wherever it happens to live so the
// script runs from an npx cache without pulling ~300MB of browsers into the repo.
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';

// ESM `import` ignores NODE_PATH, so resolve through CommonJS (which honours it
// and the npx cache) and import the resolved file URL. PLAYWRIGHT_PATH is the
// explicit escape hatch.
async function loadChromium() {
  const attempts = [];
  if (process.env.PLAYWRIGHT_PATH) attempts.push(process.env.PLAYWRIGHT_PATH);
  attempts.push('playwright', 'playwright-core');
  const require = createRequire(import.meta.url);
  for (const name of attempts) {
    try {
      const entry = require.resolve(name);
      const mod = await import(pathToFileURL(entry).href);
      const pw = mod.chromium ?? mod.default?.chromium;
      if (pw) return pw;
    } catch { /* try the next candidate */ }
  }
  return null;
}

const chromium = await loadChromium();
if (!chromium) {
  console.error(
    'playwright not found. This check is a manual gate, so playwright is not a\n' +
    'dependency of this project. Run it with an existing install, e.g.\n' +
    '  NODE_PATH="$(npm root -g)" node frontend/scripts/responsive-check.mjs\n' +
    '  PLAYWRIGHT_PATH=/path/to/node_modules/playwright node frontend/scripts/responsive-check.mjs');
  process.exit(2);
}

const SIZES = [
  [2560, 1440, '27" @100%'],
  [1680, 1000, 'laptop @100%'],
  [1280,  800, 'laptop @133% zoom'],
  [1120,  667, 'laptop @150% zoom'],
  [ 840,  500, 'laptop @200% zoom'],
  [ 672,  400, 'laptop @250% zoom'],
  [ 560,  333, 'laptop @300% zoom'],
  [ 420,  250, 'laptop @400% zoom'],
];
const VIEWS = ['Overview', 'Scoreboard', 'Waveform', 'Schematic', 'Quality',
               'Knowledge', 'Assistant', 'Manual'];

const URL = process.env.WORKBENCH_URL || 'http://127.0.0.1:8012/';
const browser = await chromium.launch();
const page = await browser.newPage();
await page.goto(URL);
await page.waitForSelector('.workbench');
await page.evaluate(() => localStorage.removeItem('wb-panes'));

const problems = [];
const table = [];
for (const [w, h, label] of SIZES) {
  await page.setViewportSize({ width: w, height: h });
  await page.waitForTimeout(320);
  for (const v of VIEWS) {
    await page.click(`.view-tab:has-text("${v}")`).catch(() => {});
    await page.waitForTimeout(260);
    const m = await page.evaluate(() => {
      const q = s => document.querySelector(s);
      const vis = e => e && getComputedStyle(e).display !== 'none';
      const r = e => e ? e.getBoundingClientRect() : { width: 0, height: 0 };
      const wb = q('.workbench');
      return {
        shellH: Math.round(r(wb).height),
        vh: window.innerHeight, vw: window.innerWidth,
        body: [Math.round(r(q('.view-body')).width), Math.round(r(q('.view-body')).height)],
        nav: vis(q('.navigator')) ? Math.round(r(q('.navigator')).width) : 0,
        props: vis(q('.properties')) ? Math.round(r(q('.properties')).width) : 0,
        consoleH: Math.round(r(q('.console')).height),
        pageScrollsY: document.documentElement.scrollHeight > window.innerHeight + 1,
        pageScrollsX: document.documentElement.scrollWidth > window.innerWidth + 1,
      };
    });
    const bad = [];
    if (m.shellH > m.vh + 1) bad.push('shell overflows viewport');
    if (m.pageScrollsX) bad.push('horizontal page scroll');
    if (m.pageScrollsY) bad.push('vertical page scroll');
    if (m.body[1] < 60) bad.push(`view body only ${m.body[1]}px tall`);
    if (m.body[0] < 180) bad.push(`view body only ${m.body[0]}px wide`);
    if (m.nav && m.nav < 130) bad.push(`navigator sliver ${m.nav}px`);
    if (m.props && m.props < 130) bad.push(`properties sliver ${m.props}px`);
    if (bad.length) problems.push({ size: label, view: v, issues: bad });
    if (v === 'Scoreboard') {
      table.push(`  ${label.padEnd(20)} ${String(w + 'x' + h).padEnd(10)} ` +
        `body ${String(m.body[0] + 'x' + m.body[1]).padEnd(10)} ` +
        `nav ${String(m.nav || '—').padEnd(5)} props ${String(m.props || '—').padEnd(5)} ` +
        `console ${m.consoleH}`);
    }
  }
}
console.log('viewport sweep (Scoreboard row shown):');
console.log(table.join('\n'));
console.log(`\nchecked ${SIZES.length} sizes x ${VIEWS.length} views = ${SIZES.length * VIEWS.length} combinations`);
console.log(problems.length ? '\nPROBLEMS:\n' + JSON.stringify(problems, null, 2) : '\nno problems found');
await browser.close();
process.exit(problems.length ? 1 : 0);
