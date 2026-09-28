// open the chat of the character created earlier
export async function toChat(p) {
  if (await p.locator('textarea').count()) return;
  const btns = await p.evaluate(() => [...document.querySelectorAll('button, div[role=button], img')].slice(0, 30).map(b => { const r = b.getBoundingClientRect(); return `${b.tagName}@${Math.round(r.x)},${Math.round(r.y)}:${(b.getAttribute('aria-label') || b.getAttribute('alt') || b.innerText || '').slice(0, 20)}`; }));
  for (const [x, y] of [[40, 132], [40, 196], [40, 260]]) {
    await p.mouse.click(x, y); await p.waitForTimeout(1500);
    if (await p.locator('textarea').count()) return;
    if (await p.getByText('Create from Scratch').count()) { await p.keyboard.press('Escape'); await p.waitForTimeout(500); }
  }
  console.log('no chat found; buttons:', btns.join(' | '));
}
export async function panel(p) {
  await p.locator('button[aria-label="menu"]').first().click(); await p.waitForTimeout(800);
  await p.getByText('NMOS 기억').first().click(); await p.waitForTimeout(2000);
  for (const fr of p.frames()) { if (await fr.locator('#nmos-panel').count().catch(() => 0)) return fr; }
  throw new Error('panel frame not found');
}
