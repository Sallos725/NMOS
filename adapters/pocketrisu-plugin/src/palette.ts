// The one colour set for the panel and the chat-screen display: neutrals carry the interface, the
// accent and the three state colours only mark action, selection and status.

export const PALETTE = {
  // Surfaces, darkest to lightest (soft charcoal for long reading sessions).
  bg: '#16181e',
  sunken: '#12141a',
  surface: '#1e212a',
  raised: '#262a35',
  raisedHover: '#303543',
  // Hairlines on any surface.
  line: 'rgba(255,255,255,0.08)',
  lineStrong: 'rgba(255,255,255,0.13)',
  lineHover: 'rgba(255,255,255,0.2)',
  // Text, strongest to faintest. `textFaint` still passes 4.5:1 on `surface`; `textGhost` is for marks only.
  textStrong: '#eef1f7',
  text: '#dce1ec',
  textSoft: '#b6bece',
  textMuted: '#9294a0',
  textFaint: '#878b99',
  textGhost: '#676c7d',
  // White text on `accent` passes 4.5:1.
  accent: '#4a6af5',
  accentHover: '#3f5ee6',
  link: '#85a6ff',
  ok: '#4fd18b',
  err: '#f05d5e',
  warn: '#e8ac43',
  violet: '#a78bfa',
  cyan: '#38bdf8',
} as const;

export type PaletteKey = keyof typeof PALETTE;

/** A palette hex colour at the given opacity, for tints and rings. */
export function alpha(key: PaletteKey, a: number): string {
  const hex = PALETTE[key];
  if (!hex.startsWith('#')) throw new Error(`palette ${key} is not a hex colour`);
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${a})`;
}

/** `--c-<key>` declarations for the panel's root rule. */
export function paletteVars(): string {
  return Object.entries(PALETTE).map(([k, v]) => `--c-${k.replace(/[A-Z]/g, (m) => '-' + m.toLowerCase())}:${v}`).join(';');
}
