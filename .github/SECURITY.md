# Security policy

NMOS stores your chats in a local database and is meant to run on your own machine. Its security model (what is
protected, what is not, and how to expose it safely) is described in the README's
[Security](../README.md#security) section.

## Supported versions

Only the [latest release](https://github.com/Sallos725/NMOS/releases) receives fixes. NMOS is in beta; please update
before reporting.

## Reporting a vulnerability

Please **do not open a public issue** for a vulnerability. Use GitHub's private reporting instead:
**Security → Report a vulnerability** on this repository. Include the NMOS version, how it is deployed (Docker or the
portable bundle, loopback or LAN, with or without `NMOS_AUTH_TOKEN`) and the steps to reproduce.

Never include real API keys, chat contents you do not want to share, or your `.env` file in a report.
