import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';

export async function launchBrowser() {
  const require = createRequire(import.meta.url);
  for (const name of [process.env.PLAYWRIGHT_PATH, 'playwright', 'playwright-core'].filter(Boolean)) {
    let module;
    try { module = await import(pathToFileURL(require.resolve(name)).href); }
    catch { continue; }
    const chromium = module.chromium ?? module.default?.chromium;
    if (chromium) return chromium.launch({ executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH || undefined });
  }
  throw new Error('Playwright not found. Set PLAYWRIGHT_PATH to an existing install or install playwright locally.');
}

export async function navigate(page, view) {
  const link = page.locator(`.app-navigation [data-view="${view}"]`);
  if (!await link.isVisible()) await page.locator('.mobile-menu').click();
  await link.click();
  await page.waitForFunction(id => location.hash === `#${id}`, view);
  await page.waitForFunction(id => document.querySelector('.app-nav-active')?.getAttribute('data-view') === id, view);
  await page.waitForFunction(() => !document.querySelector('.view-body .spinner'));
}
