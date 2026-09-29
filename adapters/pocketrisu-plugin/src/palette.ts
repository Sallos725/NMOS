// The one colour set for the panel and the chat-screen display: neutrals carry the interface, the
// accent and the three state colours only mark action, selection and status.

export const PALETTE = {
  // Surfaces, darkest to lightest.
  bg: '#0a0b0e',
  sunken: '#0d0e13',
  surface: '#121318',
  raised: '#1a1b22',
  raisedHover: '#23242e',
  // Hairlines on any surface.
  line: 'rgba(255,255,255,0.07)',
  lineStrong: 'rgba(255,255,255,0.10)',
  lineHover: 'rgba(255,255,255,0.16)',
  // Text, strongest to faintest. `textFaint` still passes 4.5:1 on `surface`; `textGhost` is for marks only.
  textStrong: '#f4f4f7',
  text: '#e2e2e8',
  textSoft: '#c0c3d0',
  textMuted: '#9294a0',
  textFaint: '#7c7e8b',
  textGhost: '#5c5e6b',
  // White text on `accent` passes 4.5:1.
  accent: '#4a6af5',
  accentHover: '#3f5ee6',
  link: '#7ca0ff',
  ok: '#4fd18b',
  err: '#f05d5e',
  warn: '#e8ac43',
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
