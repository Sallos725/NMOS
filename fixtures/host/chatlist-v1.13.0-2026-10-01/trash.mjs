import { open, yesAll } from './lib.mjs';
const { ctx, p } = await open();
await p.waitForTimeout(3000);
await p.mouse.click(40, 133 + 72 * 2); await p.waitForTimeout(5000);
await p.getByRole('button', { name: 'Character', exact: true }).click(); await p.waitForTimeout(2000);
let found = false;
for (const x of [268, 236, 300, 204]) {
  await p.mouse.click(x, 68); await p.waitForTimeout(1500);
  if (await p.getByText('Move to trash', { exact: true }).count()) { found = true; console.log('tab x', x); break; }
}
if (!found) { console.log('not found'); await ctx.close(); process.exit(1); }
const b = p.getByText('Move to trash', { exact: true }).first();
await b.scrollIntoViewIfNeeded(); await b.click(); await p.waitForTimeout(1500);
await p.screenshot({ path: 'trash-confirm.png' });
await yesAll(p, 3); await p.waitForTimeout(6000);
await p.screenshot({ path: 'trash-done.png' });
console.log(await p.evaluate(() => document.body.innerText.match(/Moved to the trash[^\n]*/)?.[0] ?? 'no toast'));
await ctx.close();
