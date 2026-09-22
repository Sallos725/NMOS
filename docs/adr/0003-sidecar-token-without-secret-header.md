# 0003 — Sidecar token without `saveSecretHeader`

Status: accepted, 2026-09-22; **amended 2026-09-22 by owner: the token is optional and off by default.**

## Context

PHASE-0 asks for the auth token to be stored via `saveSecretHeader`. In PocketRisu `a14c911`
`saveSecretHeader` is a stub that only logs "not implemented yet"
(`src/ts/plugins/apiV3/v3.svelte.ts:1609`). `nativeFetch` passes request headers through
(it only warns on authorization-like names) and fetches directly from the browser, falling back
to the PocketRisu server proxy.

## Decision

The token is a plugin argument (`auth_token`) and is sent as `Authorization: Bearer <token>` on
every sidecar call. The sidecar answers CORS preflight for the configured PocketRisu origin(s).

## Consequences

- The token is visible to anyone who can open the plugin settings or read the PocketRisu database.
  It protects the sidecar from other LAN clients, not from the PocketRisu user.
- When PocketRisu implements `saveSecretHeader`, switch to it without changing the sidecar.

## Amendment (owner, 2026-09-22)

A token between the plugin and a loopback-only sidecar adds setup friction without protection.
`NMOS_AUTH_TOKEN` is now optional: empty (the default) disables auth. The sidecar port binds to
`127.0.0.1` by default. Set a token (and the plugin's `auth_token`) only when binding
`NMOS_SIDECAR_BIND` to a LAN/Tailscale address.
