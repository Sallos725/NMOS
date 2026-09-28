import { open } from './lib.mjs';
const { ctx, p } = await open();
await p.waitForTimeout(6000);
await p.screenshot({ path: 'first.png' });
await ctx.close();
