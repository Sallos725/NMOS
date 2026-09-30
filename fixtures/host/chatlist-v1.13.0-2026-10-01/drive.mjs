import { open, yesAll } from './lib.mjs';
const [cmd, arg, reps] = process.argv.slice(2);
const { ctx, p } = await open();
const lines = [];
p.on('console', (m) => { const s = m.text(); if (s.startsWith('[AGE4]')) { lines.push(s); console.log(s.length > 1500 ? s.slice(0, 1500) + '…' : s); } });
await p.waitForTimeout(3000);
if (cmd === 'install') {
  await p.mouse.click(40, 23); await p.waitForTimeout(1000);
  await p.mouse.click(40, 84); await p.waitForTimeout(1500);
  await p.getByText(/^(Plugins?|플러그인)$/).first().click(); await p.waitForTimeout(1500);
  const [chooser] = await Promise.all([p.waitForEvent('filechooser'), p.getByText('Import plugin').click()]);
  await chooser.setFiles(arg);
  await p.waitForTimeout(3000); await yesAll(p, 4);
  await p.reload(); await p.waitForTimeout(6000); await yesAll(p, 4);
  await p.screenshot({ path: 'install.png' });
} else if (cmd === 'measure') {
  await p.evaluate(() => { window.__lt = []; new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__lt.push([Math.round(e.startTime), Math.round(e.duration)]); }).observe({ type: 'longtask', buffered: false }); });
  const t0 = await p.evaluate(() => performance.now());
  await p.evaluate(([a]) => globalThis.__pluginApis__.setArg('age4_probe::go', a), [arg + ':' + (reps || 5) + ':' + Date.now()]);
  const t1 = Date.now();
  while (Date.now() - t1 < 180000 && !lines.some((l) => l.includes('"done":true'))) { await yesAll(p, 1); await p.waitForTimeout(500); }
  const lt = await p.evaluate((t) => window.__lt.filter(([s]) => s >= t), t0);
  console.log('[LONGTASKS] ' + JSON.stringify(lt));
} else if (cmd === 'open') {
  // arg = character icon index (0-based), reps = chat name; opens each in turn (comma lists)
  const icons = arg.split(','), names = (reps || '').split(',');
  for (let i = 0; i < icons.length; i++) {
    await p.mouse.click(40, 133 + 72 * Number(icons[i])); await p.waitForTimeout(3000);
    if (names[i]) { await p.getByText(names[i], { exact: true }).first().click(); }
    const t = Date.now(); await p.waitForTimeout(1000);
    for (let k = 0; k < 120; k++) { if (await p.locator('.default-chat-screen').count()) break; await p.waitForTimeout(500); }
    await p.waitForTimeout(8000);
    console.log('opened', icons[i], names[i], Date.now() - t, 'ms');
    await p.screenshot({ path: `open-${i}.png` });
  }
  await p.evaluate(() => { window.__lt = []; new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__lt.push([Math.round(e.startTime), Math.round(e.duration)]); }).observe({ type: 'longtask', buffered: false }); });
  const t0 = await p.evaluate(() => performance.now());
  await p.evaluate(([a]) => globalThis.__pluginApis__.setArg('age4_probe::go', a), [process.argv[5] + ':5:' + Date.now()]);
  const t1 = Date.now();
  while (Date.now() - t1 < 300000 && !lines.some((l) => l.includes('"done":true'))) { await yesAll(p, 1); await p.waitForTimeout(500); }
  const lt = await p.evaluate((t) => window.__lt.filter(([s]) => s >= t), t0);
  console.log('[LONGTASKS] ' + JSON.stringify(lt));
} else if (cmd === 'shot') {
  await p.screenshot({ path: arg || 'shot.png' });
}
await ctx.close();
