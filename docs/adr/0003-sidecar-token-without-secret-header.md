# 0003 — Sidecar token without `saveSecretHeader`

Status: accepted, 2026-09-22 (implementation constraint from the target host build).

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
