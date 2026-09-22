import { createAdapter } from './core';
import { registerHooks, risuHost } from './host';
import type { PromptMessage } from './types';

(async () => {
  const adapter = createAdapter(risuHost);
  await registerHooks(
    async (prompt, mode) => {
      try {
        return await adapter.beforeRequest(prompt as PromptMessage[], mode);
      } catch {
        return prompt; // fail open, whatever happened
      }
    },
    (arg) => adapter.onOutput(arg as Parameters<typeof adapter.onOutput>[0]),
    () => adapter.statusText(),
    (method, path, body, timeoutMs) => adapter.api(method, path, body, timeoutMs),
  );
  console.log('[NMOS] adapter loaded', { version: __NMOS_VERSION__ });
})().catch((error) => console.error('[NMOS] adapter failed to load', error));

declare const __NMOS_VERSION__: string;
