import { createAdapter } from './core';
import { createRisuHud, registerHooks, risuHost } from './host';
import type { PromptMessage } from './types';

(async () => {
  let openStatus = (): void => {};
  const hud = createRisuHud({
    coverage: (conversationId) => adapter.api('GET', `/v1/conversations/${conversationId}/coverage`, undefined, 5000),
    openPanel: () => openStatus(),
  });
  const adapter = createAdapter(risuHost, (event) => hud.event(event));
  openStatus = await registerHooks(
    async (prompt, mode) => {
      try {
        return await adapter.beforeRequest(prompt as PromptMessage[], mode);
      } catch {
        return prompt; // fail open, whatever happened
      }
    },
    (arg) => adapter.onOutput(arg as Parameters<typeof adapter.onOutput>[0]),
    () => adapter.status(),
    (method, path, body, timeoutMs) => adapter.api(method, path, body, timeoutMs),
    hud,
  );
  // After the hooks: the host shows its "db" permission dialog (if it has not been answered) after the
  // replacer one, at load rather than during a request.
  adapter.warmPersonas();
  console.log('[NMOS] adapter loaded', { version: __NMOS_VERSION__ });
})().catch((error) => console.error('[NMOS] adapter failed to load', error));

declare const __NMOS_VERSION__: string;
