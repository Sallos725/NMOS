// Phase 14 step 2: canon observations at each request on PocketRisu v1.13.0 (synthetic data).
import { open } from './lib.mjs';
import { toChat } from './chat.mjs';
import { appendFileSync, writeFileSync } from 'node:fs';
const { ctx, p } = await open();
writeFileSync('observations-10k.jsonl', '');
p.on('console', (m) => {
  const t = m.text();
  if (t.startsWith('[NMOS-CANON] request ')) appendFileSync('observations-10k.jsonl', t.slice('[NMOS-CANON] request '.length) + '\n');
});
const answer = async () => {
  for (let i = 0; i < 4; i++) {
    const body = await p.evaluate(() => document.body.innerText);
    const m = body.match(/[^\n]*(database|데이터베이스)[^\n]*/i);
    const y = p.getByRole('button', { name: /^(Yes|예)$/ });
    if (await y.count()) { console.log('permission dialog:', m ? m[0].slice(0, 160) : '(no text)'); await y.first().click(); await p.waitForTimeout(1200); }
    else break;
  }
};
await toChat(p);
const send = async (text) => {
  const before = await p.evaluate(() => document.body.innerText.split('Stub reply #').length);
  await p.locator('textarea').first().fill(text); await p.keyboard.press('Enter');
  for (let i = 0; i < 40; i++) { await p.waitForTimeout(500); await answer(); if (await p.evaluate((b) => document.body.innerText.split('Stub reply #').length > b, before)) break; }
  await p.waitForTimeout(1500);
  console.log('sent:', text);
};
await send('카이토는 어디 있어?');
await send('어시장에 가 보자.');
await send('비밀 통로 이야기를 해 줘.');
await p.screenshot({ path: 'probe.png' });
await ctx.close();
