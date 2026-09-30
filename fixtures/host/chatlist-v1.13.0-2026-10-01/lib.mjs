import { chromium } from 'playwright-core';
// PORT (PocketRisu) and PROFILE (browser profile dir) select the instance.
export async function open() {
  const port = process.env.PORT, profile = process.env.PROFILE;
  if (!port || !profile) throw new Error('PORT and PROFILE are required');
  const ctx = await chromium.launchPersistentContext(profile, {
    executablePath: process.env.HOME + '/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome',
    viewport: { width: 1280, height: 800 },
  });
  const p = ctx.pages()[0] || await ctx.newPage();
  p.on('console', m => { if (process.env.V === '1' || /NMOS.*(error|fail)|request done/i.test(m.text())) console.log('console:', m.text().slice(0, 200)); });
  p.on('dialog', d => { console.log('dialog:', d.message()); d.accept(); });
  await p.goto(`http://localhost:${port}/`);
  await p.waitForTimeout(4000);
  if (await p.getByText(/password/i).count() && await p.locator('input').count()) {
    await p.locator('input').first().fill('nmos-test-pw');
    await p.getByRole('button', { name: 'Confirm' }).click();
    await p.waitForTimeout(4000);
  }
  return { ctx, p };
}
export const yesAll = async (p, n = 3) => { for (let i = 0; i < n; i++) { const y = p.getByRole('button', { name: 'Yes', exact: true }); if (await y.count()) { await y.first().click(); await p.waitForTimeout(900); } else await p.waitForTimeout(400); } };
