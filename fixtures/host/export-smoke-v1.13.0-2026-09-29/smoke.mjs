// Phase 16 step 5: the panel's Export buttons on PocketRisu v1.13.0 against a sidecar on a synthetic database.
import { open } from './lib.mjs';
import { createHash } from 'node:crypto';
import { readFileSync, statSync, copyFileSync } from 'node:fs';
const route = process.argv[2] || 'server';
const { ctx, p } = await open();
const saved = [];
p.on('download', async (d) => {
  const path = await d.path();
  const size = statSync(path).size;
  const sha = createHash('sha256').update(readFileSync(path)).digest('hex').slice(0, 12);
  copyFileSync(path, `./got-${saved.length}.nmos.zip`);
  saved.push(d.suggestedFilename());
  console.log('DOWNLOAD', d.suggestedFilename(), size, sha);
});
const answer = async () => { for (let i = 0; i < 3; i++) { const y = p.getByRole('button', { name: /^(Yes|예)$/ }); if (await y.count()) { await y.first().click(); await p.waitForTimeout(800); } } };
await answer();
console.log('args', await p.evaluate(async (route) => {
  const a = globalThis.__pluginApis__;
  a.setArg('nmos_memory::sidecar_url', 'http://127.0.0.1:8841');
  a.setArg('nmos_memory::route', route);
  return [a.getArg('nmos_memory::sidecar_url'), a.getArg('nmos_memory::route')];
}, route));
await p.reload(); await p.waitForTimeout(4000); await answer();
await p.mouse.click(40, 23); await p.waitForTimeout(1000); await p.mouse.click(40, 84); await p.waitForTimeout(1500);
await p.getByText('NMOS 기억', { exact: true }).first().click();
await p.waitForTimeout(2000);
let fr = null;
for (const f of p.frames()) if (await f.locator('#nmos-panel').count().catch(() => 0)) fr = f;
console.log('panel', !!fr);
const wait = async (n) => {
  for (let i = 0; i < 60 && saved.length < n; i++) await p.waitForTimeout(500);
  if (saved.length < n) throw new Error(`expected ${n} download(s), saw ${saved.length}`);
};
await fr.getByRole('button', { name: '설정', exact: true }).click(); await p.waitForTimeout(1500);
const url = fr.locator('#nmos-panel input[spellcheck="false"]').first();
const routeSelect = fr.locator('#nmos-panel select:has(option[value="server"])').first();
if ((await url.inputValue()) !== 'http://127.0.0.1:8841' || (await routeSelect.inputValue()) !== route) {
  await url.fill('http://127.0.0.1:8841');
  await routeSelect.selectOption(route);
  await fr.locator('#nmos-panel button.primary').click(); await p.waitForTimeout(2500);
  console.log('saved settings; url now', await url.inputValue());
}
await fr.getByRole('button', { name: '전부 내보내기' }).click();
await wait(1); await p.waitForTimeout(500);
console.log('settings text:', (await fr.locator('#nmos-panel').innerText()).slice(-600).replace(/\n/g, ' / '));
await fr.getByRole('button', { name: '인스펙터', exact: true }).click(); await p.waitForTimeout(2500);
await p.screenshot({ path: 'insp.png' }); console.log('insp text:', (await fr.locator('#nmos-panel').innerText()).slice(0, 300).replace(/\n/g, ' / ')); await fr.locator('#nmos-panel a').first().click(); await p.waitForTimeout(2500);
await fr.getByRole('button', { name: '이 대화 내보내기' }).click();
await wait(2); await p.waitForTimeout(500);
console.log('inspector msg:', (await fr.locator('#nmos-panel').innerText()).match(/[^\n]*MB[^\n]*/)?.[0]);
await p.screenshot({ path: `smoke-${route}.png` });
console.log('saved', saved);
await ctx.close();
