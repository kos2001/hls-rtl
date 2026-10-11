/** Behavior checks run with isolated API fixtures; no simulator jobs or gateway calls. */
import assert from 'node:assert/strict';
import { readFile, mkdir } from 'node:fs/promises';
import { launchBrowser, navigate } from './browser-test-utils.mjs';

const snapshot = JSON.parse(await readFile(new URL('../public/results.json', import.meta.url), 'utf8'));
const browser = await launchBrowser();
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
await context.addInitScript(() => { localStorage.setItem('wb-lang', 'en'); });
const page = await context.newPage();
const errors = [];
page.on('pageerror', error => errors.push(error.message));
let offline = false;
let verification = structuredClone(snapshot);
let signoffFails = false;
let signoffCalls = 0;
const report = { verdict: 'CONDITIONAL', score: 90, grade: 'A', module: 'gamma', stages: [
  { name: 'lint', status: 'pass', gating: true, detail: 'Lint complete' },
  { name: 'systemc', status: 'skip', gating: false, detail: 'SystemC evidence unavailable' },
] };
await page.route('**/api/**', async route => {
  const path = new URL(route.request().url()).pathname.replace('/api', '');
  if (offline) return route.fulfill({ status: 503, body: 'backend unavailable' });
  const fixtures = {
    '/health': { ok: true, model: 'test-gateway', has_key: false, verilator: true },
    '/verification': verification,
    '/analyze': { module: 'gamma', score: 95, grade: 'A', lint_tool: 'verilator', metrics: { synth_cells: 200, synth_flops: 32, synth_latches: 0, synthesizable: true, reset_kind: 'async', reset_active: 'low', hdl_dialect: 'Verilog-2001' }, checks: [{ id: 'no_latches', ok: true, severity: 'error', detail: 'No latches' }] },
    '/skills': { profile: 'test', active: [], skills: [], missing: [] },
    '/telemetry/signoff': { kind: 'signoff', count: 2, mean_score: 90, history: [] },
    '/kb/stats': { chunks: 32, pinned: 3, terms: 100 },
  };
  if (path === '/signoff') {
    signoffCalls++;
    assert.equal(route.request().method(), 'POST');
    assert.deepEqual(route.request().postDataJSON(), { run_regression: true });
    await new Promise(resolve => setTimeout(resolve, 400));
    return route.fulfill({ status: signoffFails ? 502 : 200, contentType: 'application/json', body: signoffFails ? '{"detail":"simulator unavailable"}' : JSON.stringify(report) });
  }
  return route.fulfill({ status: fixtures[path] ? 200 : 503, contentType: 'application/json', body: JSON.stringify(fixtures[path] ?? { detail: 'Fixture unavailable' }) });
});
const base = process.env.WORKBENCH_URL || 'http://127.0.0.1:5183/';
const ready = () => page.waitForFunction(() => !document.querySelector('.refresh-button')?.disabled);
const has = async (selector, text) => assert.ok((await page.locator(selector).innerText()).includes(text), `${selector} should contain ${text}`);
try {
  await page.goto(base);
  await ready();
  await has('.verification-banner', 'Your reference model is ready.');
  assert.equal(await page.locator('.evidence-status-pass').count(), 0, 'Reference data cannot imply measured passes');
  await page.locator('#gamma-input').fill('0');
  assert.equal((await page.locator('.chart-output b').allTextContents()).join(','), '0,0,0');
  await page.locator('#gamma-input').fill('255');
  assert.equal((await page.locator('.chart-output b').allTextContents()).join(','), '255,255,255');
  await page.keyboard.press('Control+k');
  await page.getByRole('combobox').fill('gradient');
  await page.getByRole('combobox').press('Enter');
  await page.waitForSelector('.scoreboard-panel');
  await has('.prop-head', 'gradient');
  assert.equal(await page.locator('.command-dialog').isVisible(), false);
  assert.equal(await page.locator('.badge-pass').count(), 0);
  assert.equal(await page.locator('.scoreboard-panel .badge-expected').count(), 13);
  await page.getByLabel('Filter patterns', { exact: true }).fill('colorbar');
  assert.equal(await page.locator('.scoreboard-panel tbody tr').count(), 1);
  await page.getByLabel('Filter patterns', { exact: true }).fill('does-not-exist');
  await has('.scoreboard-panel', 'No patterns match');
  await page.getByRole('button', { name: 'Reset filters' }).click();
  assert.equal(await page.locator('.scoreboard-panel tbody tr').count(), 13);
  await page.getByRole('button', { name: 'Inspector', exact: true }).click();
  const resultDownload = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export results', exact: true }).click();
  const result = await resultDownload;
  const exported = JSON.parse(await readFile(await result.path(), 'utf8'));
  assert.equal(exported.evidence_kind, 'reference');
  assert.equal(exported.patterns.length, 13);
  await navigate(page, 'signoff');
  await page.locator('.page-actions .primary-button').click();
  assert.equal(await page.locator('.page-actions .primary-button').isDisabled(), true);
  await page.waitForSelector('.verdict-CONDITIONAL');
  assert.equal(await page.locator('.view-body .badge-skip').count(), 1);
  assert.equal(signoffCalls, 1);
  signoffFails = true;
  await page.locator('.page-actions .primary-button').click();
  await page.waitForSelector('[role="alert"]');
  await has('[role="alert"]', 'Sign-off could not complete');
  assert.equal(await page.locator('.verdict-CONDITIONAL').count(), 0, 'Failed run must not show stale success');
  const transcriptDownload = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export transcript…', exact: true }).click();
  const transcript = await readFile(await (await transcriptDownload).path(), 'utf8');
  assert.ok(transcript.includes('simulator unavailable'));
  assert.ok(transcript.includes('reload --all'), 'Export must include full unfiltered transcript');
  verification = structuredClone(snapshot);
  verification.evidence_kind = 'regression';
  verification.summary.failed = 1;
  verification.summary.passed--;
  verification.patterns[0].status = 'fail';
  verification.patterns[0].mismatches = 1;
  verification.patterns[0].rtl_sha256 = 'f'.repeat(64);
  await page.locator('.refresh-button').click(); await ready();
  await navigate(page, 'overview');
  await has('.verification-banner', 'Patterns need your attention.');
  await navigate(page, 'scoreboard');
  await page.getByLabel('status', { exact: true }).selectOption('fail');
  assert.equal(await page.locator('tbody tr').count(), 1);
  await has('tbody', 'edge_cases');
  offline = true;
  await page.locator('.refresh-button').click(); await ready();
  await navigate(page, 'overview');
  await has('.snapshot-notice', 'saved snapshot');
  await has('.connection-status', 'Offline');
  offline = false; verification = structuredClone(snapshot);
  await page.getByRole('button', { name: 'Reconnect' }).click(); await ready();
  assert.equal(await page.locator('.snapshot-notice').count(), 0);
  await page.locator('#gamma-input').fill('128');
  const screenshotDir = process.env.SCREENSHOT_DIR;
  if (screenshotDir) { await mkdir(screenshotDir, { recursive: true }); await page.screenshot({ path: `${screenshotDir}/desktop-dark.png` }); }
  await page.getByRole('button', { name: 'Light theme', exact: true }).click();
  assert.equal(await page.locator('html').getAttribute('data-theme'), 'light');
  await page.reload(); await ready();
  assert.equal(await page.locator('html').getAttribute('data-theme'), 'light');
  await page.getByRole('button', { name: '한국어로 전환', exact: true }).click();
  assert.equal(await page.locator('html').getAttribute('lang'), 'ko');
  await has('.page-heading h1', '개요');
  if (screenshotDir) await page.screenshot({ path: `${screenshotDir}/desktop-light-ko.png` });
  await page.getByRole('button', { name: 'Switch to English', exact: true }).click();
  await page.getByRole('button', { name: 'Dark theme', exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('button', { name: 'Open navigation', exact: true }).click();
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('.sidebar-open').count(), 0);
  await navigate(page, 'scoreboard');
  assert.equal(await page.locator('.sidebar-open').count(), 0);
  assert.ok((await page.locator('.page-heading h1').innerText()).includes('Scoreboard'));
  await page.goBack();
  await page.waitForFunction(() => location.hash === '#overview');
  await has('.page-heading h1', 'Overview');
  assert.ok((await page.locator('.verification-banner-copy').boundingBox()).width > 180, 'Mobile banner text must retain a readable column width');
  if (screenshotDir) await page.screenshot({ path: `${screenshotDir}/mobile-dark.png` });
  assert.deepEqual(errors, []);
  console.log('PASS: provenance, LUT endpoints, command search, pattern filters, inspector, downloads, sign-off state, failure handling, offline recovery, themes, Korean, mobile navigation, browser history; no runtime errors.');
} finally { await browser.close(); }
