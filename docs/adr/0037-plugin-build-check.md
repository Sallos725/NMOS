# 0037 — The sidecar tells whether the plugin in use is its own build

Status: accepted, 2026-09-27. Owner request after Phase 10 step 6 ("빌드 번호 확인 넣고"). Addresses K19. No
migration, no new extractor generation or packet policy.

## Context

The plugin runs in the PocketRisu page and the sidecar cannot see it. After an update the owner could not tell
whether the plugin file had been replaced, or whether a tab still ran the old one (H13: a plugin change needs a
page reload): on `:edge` the plugin's `//@version` does not change between releases, and a plugin from another
build fails or lacks features without saying why (K19). The owner found this a serious gap.

## Decision

1. **Build id.** The plugin's build script hashes the built file (with a placeholder where the id goes) and
   writes the first 12 hex digits into it as `nmos-build:<id>`. The same source gives the same id, so a commit
   that does not touch the plugin does not make it look outdated.
2. **The plugin says it.** Every sync (`/v1/sync/reconcile`, and the reconcile after `/v1/sync/bodies`) carries
   `plugin_build`. A request body field, not a header: older sidecars ignore unknown fields, and a header would
   need a CORS change on the direct route.
3. **The sidecar knows its own.** The image copies the plugin file of the same commit (`NMOS_PLUGIN_FILE`); a
   checkout reads the repository's `dist`. The sidecar reads the id from it.
4. **What is shown.** The sidecar keeps the last 5 builds that synced, in memory (after a restart the next
   generation shows it again). `/v1/health` returns `plugin: {expected, seen}`. The Inspector's first page says
   whether the last plugin to sync is the sidecar's build, warns when it is not (an older plugin sends no id and
   is named as such), warns when another tab or device synced with another build after it, and links the
   matching file: `GET /v1/plugin/nmos-pocketrisu.js` (auth as other routes). The Inspector is drawn by the
   sidecar, so the warning reaches a user whose plugin is too old to know about it. A plugin that has the check
   also compares on its Status tab.

Not here: refusing an outdated plugin (memory keeps working, as before), or checking versions across releases
beyond "same build or not".

## Consequences

- The first plugin with a build id has to be installed by hand once; until then the Inspector says "no build id
  (an older plugin)".
- The id follows the built file, so rebuilding with another esbuild version changes it; CI checks that `dist`
  is up to date.
- K19 stays open for other deployments (a plugin served from elsewhere, a sidecar without the file): the check
  is shown only when the sidecar knows its build.
