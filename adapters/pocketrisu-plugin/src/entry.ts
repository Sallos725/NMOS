import { createAdapter } from './core';
import { createRisuHud, onPluginUnload, registerHooks, risuHost } from './host';
import type { PanelTarget } from './hud';
import type { PromptMessage } from './types';

(async () => {
  let openStatus: (target?: PanelTarget) => void = () => {};
  const hud = createRisuHud({
    coverage: (conversationId) => adapter.api('GET', `/v1/conversations/${conversationId}/coverage`, undefined, 5000),
    openPanel: (target) => openStatus(target),
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
    (path) => adapter.file(path),
    hud,
  );
  // After the hooks: the host shows its "db" permission dialog (if it has not been answered) after the
  // replacer one, at load rather than during a request.
  adapter.warmPersonas();
  // Whether the sidecar extracts a reply right after it (G6): read now and every few minutes, never on a request.
  adapter.warmConfig();
  // Its timers (and a waiting background sync) go with the plugin when it is unloaded or re-imported, where the host
  // says so; the sandbox frame the host removes then takes them anyway.
  onPluginUnload(() => {
    adapter.dispose();
    hud.dispose();
  });
  console.log('[NMOS] adapter loaded', { version: __NMOS_VERSION__ });
})().catch((error) => console.error('[NMOS] adapter failed to load', error));

declare const __NMOS_VERSION__: string;
