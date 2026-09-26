# 0030 — Without a token, answer only to known host names

Status: accepted, 2026-09-26. Owner decision on audit A-05 (`docs/audits/NMOS-AUDIT-2026-09-26.md`,
review option A; the owner asked for it to be set from the compose environment). Amends ADR 0003.

## Context

ADR 0003 made the token optional and off by default. Without it, anything that reaches the sidecar
can read every chat, change settings, and make `/v1/config/models` or `/v1/config/test` send the stored
LLM key to a URL of its choice.

Binding to loopback does not stop a web page in the user's own browser. With DNS rebinding, a page on
`attacker.example` makes its own name resolve to `127.0.0.1` (or a LAN address). The browser then treats
requests to the sidecar as same-origin, so CORS does not apply. The one thing such a page cannot choose
is the `Host` header: it is always the attacker's domain name.

## Decision

1. **With no token, the sidecar checks `Host`.** It answers requests addressed to:
   - an IP address;
   - `localhost`;
   - a single-label name (`nmos`, `sidecar`, a container or machine name);
   - a name listed in `NMOS_ALLOWED_HOSTS` (comma-separated; `*.example.com` covers subdomains; `*`
     turns the check off).

   Anything else gets HTTP 400 naming the setting, and one warning per host in the log. A rebinding page
   needs a registered domain name, so none of the names above can be one.
2. **With a token, the token decides** and `Host` is not checked. A token already stops a page that
   cannot know it, and a user who set one may reach the sidecar by any name.
3. `NMOS_ALLOWED_HOSTS` is passed to both services by both compose files and documented in `.env.example`,
   README and the Korean guide.

## Consequences

- Loopback, LAN-by-address, Docker-network (`http://nmos:8790`) and SSH-tunnel setups need no change.
  This includes the owner's `route=server` setup.
- A setup that reaches a tokenless sidecar by a domain name gets 400 until that name is added to
  `NMOS_ALLOWED_HOSTS`: a reverse proxy that keeps the client's `Host`, or a tailnet MagicDNS name. The
  panel shows the sidecar as unreachable; the log names the host and the setting.
- Rejected:
  - Docs only (B): leaves the rebinding path open.
  - A mandatory token (C): every existing setup would have to change.
