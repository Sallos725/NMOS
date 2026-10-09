// Opens the upload probe from Settings and clicks each action named on the command line, waiting for its "done" line.
//   node run.mjs info server-binary-1 direct-base64-30 …      (FF=1 for Firefox)
import { open } from './lib.mjs';
const acts = process.argv.slice(2);
const { ctx, p } = await open();
const done = new Set();
p.on('console', m => {
  const t = m.text();
  if (t.startsWith('[NMOS-PROBE] ')) { console.log(t); if (t.startsWith('[NMOS-PROBE] done ')) done.add(t.slice(18)); }
});
for (let i = 0; i < 3; i++) { const y = p.getByRole('button', { name: /^(Yes|예)$/ }); if (await y.count()) { await y.first().click(); await p.waitForTimeout(1000); } }
let opened = false;
for (const tryOpen of [
  async () => { await p.getByText('NMOS upload probe', { exact: true }).first().click({ timeout: 1500 }); },
  async () => { await p.mouse.click(40, 23); await p.waitForTimeout(1000); await p.mouse.click(40, 84); await p.waitForTimeout(1500); await p.getByText('NMOS upload probe', { exact: true }).first().click({ timeout: 3000 }); },
]) { try { await tryOpen(); opened = true; break; } catch {} }
await p.waitForTimeout(1500);
const fr = await (async () => { for (const f of p.frames()) { if (await f.locator('#b-info').count().catch(() => 0)) return f; } return null; })();
console.log('opened', opened, 'probe frame', !!fr);
console.log('sandbox', await p.evaluate(() => [...document.querySelectorAll('iframe')].map(i => `${i.getAttribute('sandbox')} | ${i.getAttribute('allow')}`).join(' ;; ')));
if (!fr) { await p.screenshot({ path: 'run.png' }); await ctx.close(); process.exit(1); }
for (const a of acts) {
  await fr.locator('#b-' + a).click();
  for (let i = 0; i < 400 && !done.has(a); i++) await p.waitForTimeout(500);
  if (!done.has(a)) console.log(`${a}: no "done" within 200 s`);
}
await ctx.close();
