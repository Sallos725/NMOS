import { open } from './lib.mjs';
const file = process.argv[2];
const { ctx, p } = await open();
await p.mouse.click(40, 23); await p.waitForTimeout(1000);
await p.mouse.click(40, 84); await p.waitForTimeout(1500);
await p.getByText(/^(Plugins?|플러그인)$/).first().click(); await p.waitForTimeout(1500);
const [chooser] = await Promise.all([p.waitForEvent('filechooser'), p.getByText('Import plugin').click()]);
await chooser.setFiles(file);
await p.waitForTimeout(2500);
for (let i = 0; i < 3; i++) { const y = p.getByRole('button', { name: 'Yes', exact: true }); if (await y.count()) { await y.first().click(); await p.waitForTimeout(1200); } }
await p.screenshot({ path: 'reinstall.png' });
await p.reload(); await p.waitForTimeout(5000);
for (let i = 0; i < 3; i++) { const y = p.getByRole('button', { name: 'Yes', exact: true }); if (await y.count()) { await y.first().click(); await p.waitForTimeout(1200); } }
console.log('installed');
await ctx.close();
