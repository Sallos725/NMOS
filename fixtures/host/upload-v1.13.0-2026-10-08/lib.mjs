import { chromium, firefox } from 'playwright-core';
export async function open() {
  // FF=1: Firefox 1543 instead of Chromium 1223, each with its own persistent profile.
  const ff = process.env.FF === '1';
  const ctx = await (ff ? firefox : chromium).launchPersistentContext(new URL(ff ? './profile-ff' : './profile', import.meta.url).pathname, {
    executablePath: process.env.HOME + (ff ? '/.cache/ms-playwright/firefox-1543/firefox/firefox'
      : '/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome'),
    viewport: { width: 1280, height: 800 },
  });
  const p = ctx.pages()[0] || await ctx.newPage();
  p.on('console', m => { if (/NMOS/i.test(m.text())) console.log('console:', m.text().slice(0, 200)); });
  p.on('dialog', d => { console.log('dialog:', d.message()); d.accept(); });
  await p.goto('http://localhost:6191/');
  await p.waitForTimeout(4000);
  const pw = p.locator('input[type="password"], .fixed input').first();
  if (await p.getByText(/password/i).count() && await p.locator('input').count()) {
    await p.locator('input').first().fill('nmos-test-pw');
    await p.getByRole('button', { name: 'Confirm' }).click();
    await p.waitForTimeout(4000);
  }
  return { ctx, p };
}
export const buttons = (p) => p.evaluate(() => [...document.querySelectorAll('button')].map(b => (b.getAttribute('aria-label') || b.innerText).trim()).filter(Boolean).slice(0, 80).join(' | '));
