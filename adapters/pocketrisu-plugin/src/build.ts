// This plugin build's id (ADR 0037): a hash of the built file, set by scripts/build.mjs. The sidecar ships the
// plugin file of its own commit and compares, so it can tell an outdated plugin (K19). "dev" outside a build.

declare const __NMOS_BUILD__: string | undefined;

export const PLUGIN_BUILD: string = typeof __NMOS_BUILD__ === 'string' ? __NMOS_BUILD__.replace('nmos-build:', '') : 'dev';
