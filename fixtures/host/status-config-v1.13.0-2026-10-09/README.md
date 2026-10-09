# Status configuration in the actual host

Executed 2026-10-09 on Linux, headless Chromium 1223, PocketRisu v1.13.0 (image in results.json),
new empty host save/profile and a dedicated isolated PostgreSQL database. The real built NMOS plugin was
installed through the host plugin picker and reloaded. No worker or provider endpoints were enabled;
no generated reply or owner chat was used. Production 6113 and existing host containers were untouched.

The final nine checks and exact plugin hash are in results.json. B's synthetic binding was seeded through
the new API; A was applied through the actual plugin iframe. The real file chooser loaded a synthetic block
rule. Preset save, page reload and selection preserved active rules. Invalid JSON and an invalid regex
preserved active state and the draft. The invalid-to-valid connection was changed on the same panel without
reopening it. Screenshots show the status card; the desktop viewport was also narrowed to 390 px. This is
not an iPhone/Safari or native-package UI check, nor a generated-answer evaluation.

The first attempt was inconclusive: connection-only Save did not reload configuration, and the disposable
sidecar's CORS origins were unset. Two isolated DOM regressions independently reproduced the product issue
and passed after its fix. Only the disposable server was given the exact http://localhost:6192 origin;
production CORS/authentication was not changed. The final run uses the corrected plugin and records nine
passes. Raw attempts and the executed local scripts remain under
/tmp/nmos-age76-evidence/status-ui-host/; profile/database contents are intentionally not repository fixtures.

To repeat: start a new empty PocketRisu v1.13.0 on a free local port, a worker-free sidecar on its own database
with that exact host origin, and install/reload the current plugin. Run the nine interactions named in the
JSON through the real panel, recording the built plugin hash and the actual target build. A bound card's
conversation-value isolation is covered by sidecar fixtures separately from this UI run.
