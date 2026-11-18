# NMOS logo files

The NMOS mark is a one-stroke N with a memory node. Its shape is defined in code in three places, which these files
copy: `adapters/pocketrisu-plugin/src/icon.ts` (the plugin icon), `tools/native/make_icon.py` (the native bundle
icon) and `FAVICON` in `apps/sidecar/src/nmos_sidecar/inspector.py` (the Inspector favicon). If the mark changes
there, regenerate these files.

| File | Look | Colours |
|---|---|---|
| `nmos-mark.svg` | the mark alone, transparent | `currentColor` |
| `nmos-icon-dark.svg` | dark tile (same as the native bundle icon) | `#0a0b0e` / `#f4f4f7` |
| `nmos-icon-light.svg` | light tile | `#fbfbfa` / `#0a0b0e` |
| `nmos-icon-accent.svg` | accent tile | `#4a6af5` / `#ffffff` |
| `nmos-icon-accent-dark.svg` | Inspector favicon colours, dark | `#18181a` / `#8ea2ff` |
| `nmos-icon-accent-light.svg` | Inspector favicon colours, light | `#fbfbfa` / `#3b5bdb` |

Each look also comes as PNG at 64, 128, 256, 512 and 1024 px (`nmos-<look>-<px>.png`). The transparent mark comes as
`mark-black`, `mark-white` and `mark-accent` (`#4a6af5`). Colours are from `adapters/pocketrisu-plugin/src/palette.ts`.
The tiles use the native bundle icon's geometry (the full mark, corner radius 22 %); the Inspector favicon insets the
mark to 80 % so it reads at tab size.

PNGs were rendered from the SVGs with headless Chromium, transparent background, device scale factor 1.
