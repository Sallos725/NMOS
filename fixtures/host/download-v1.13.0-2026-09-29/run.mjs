import { open } from './lib.mjs';
import { createHash } from 'node:crypto';
import { readFileSync, statSync } from 'node:fs';
const acts = process.argv.slice(2);
const { ctx, p } = await open();
const downloads = [];
p.on('console', m => { if (m.text().startsWith('[NMOS-PROBE]')) console.log(m.text()); else if (/block|sandbox|download/i.test(m.text())) console.log('console:', m.text().slice(0, 300)); });
p.on('download', async d => { const path = await d.path().catch(e => 'ERR ' + e.message); downloads.push(d.suggestedFilename()); let info = ''; try { info = `size=${statSync(path).size} sha=${createHash('sha256').update(readFileSync(path)).digest('hex').slice(0, 12)}`; } catch (e) { info = String(e); } console.log('DOWNLOAD', d.suggestedFilename(), d.url().slice(0, 40), info); });
for (let i = 0; i < 3; i++) { const y = p.getByRole('button', { name: /^(Yes|예)$/ }); if (await y.count()) { await y.first().click(); await p.waitForTimeout(1000); } }
// open the probe panel from wherever the host lists plugin settings
let opened = false;
for (const tryOpen of [
  async () => { await p.getByText('NMOS probe', { exact: true }).first().click({ timeout: 1500 }); },
  async () => { await p.mouse.click(40, 23); await p.waitForTimeout(1000); await p.mouse.click(40, 84); await p.waitForTimeout(1500); await p.getByText('NMOS probe', { exact: true }).first().click({ timeout: 3000 }); },
]) { try { await tryOpen(); opened = true; break; } catch {} }
await p.waitForTimeout(1500);
const frame = p.frames().find(f => f.url() !== p.url());
const fr = await (async () => { for (const f of p.frames()) { if (await f.locator('#b-info').count().catch(() => 0)) return f; } return null; })();
console.log('opened', opened, 'frames', p.frames().length, 'probe frame', !!fr);
console.log('sandbox', await p.evaluate(() => [...document.querySelectorAll('iframe')].map(i => `${i.getAttribute('sandbox')} | ${i.getAttribute('allow')}`).join(' ;; ')));
if (!fr) { await p.screenshot({ path: 'run.png' }); await ctx.close(); process.exit(1); }
for (const a of acts) {
  const n = downloads.length;
  await fr.locator('#b-' + a).click();
  for (let i = 0; i < (a === 'info' ? 2 : 120) && downloads.length === n; i++) await p.waitForTimeout(500);
  await p.waitForTimeout(500);
  console.log(`${a}: downloads +${downloads.length - n}`, 'frames:', p.frames().map(f => f.url().slice(0, 50)).join(' | '));
}
await p.screenshot({ path: 'run.png' });
await ctx.close();
