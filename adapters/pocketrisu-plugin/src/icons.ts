// Lightweight inline SVG icons (PHASE-59): zero external fonts, zero runtime deps, DOM-created via createElementNS.

export type IconName =
  | 'brand'
  | 'home'
  | 'book'
  | 'feather'
  | 'sliders'
  | 'chat'
  | 'chevronDown'
  | 'alert'
  | 'map'
  | 'terminal'
  | 'refresh'
  | 'close'
  | 'copy'
  | 'sparkles'
  | 'power'
  | 'plug'
  | 'cpu'
  | 'database'
  | 'shield'
  | 'eye'
  | 'archive'
  | 'check'
  | 'search'
  | 'edit'
  | 'lock'
  | 'undo'
  | 'eyeOff'
  | 'arrowUp';

const SVG_NS = 'http://www.w3.org/2000/svg';

// Each entry is a list of SVG element descriptors: [tag, attrs]. All stroke-based on a 24x24 viewBox.
type Shape = readonly [string, Record<string, string>];

const SHAPES: Record<IconName, readonly Shape[]> = {
  // Official NMOS mark from icon.ts: one-stroke N with a memory node.
  brand: [
    ['path', { d: 'M6 19V5l12 14V9.5', 'stroke-width': '1.75' }],
    ['circle', { cx: '18', cy: '5.5', r: '1.75', fill: 'currentColor', stroke: 'none' }],
  ],
  home: [
    ['path', { d: 'M3 10.5 12 3l9 7.5' }],
    ['path', { d: 'M5.5 9.5V20a1 1 0 0 0 1 1h4v-6h3v6h4a1 1 0 0 0 1-1V9.5' }],
  ],
  book: [
    ['path', { d: 'M4 5.5A2.5 2.5 0 0 1 6.5 3H12v18H6.5A2.5 2.5 0 0 0 4 21Z' }],
    ['path', { d: 'M20 5.5A2.5 2.5 0 0 0 17.5 3H12v18h5.5a2.5 2.5 0 0 1 2.5 0Z' }],
  ],
  feather: [
    ['path', { d: 'M20.24 12.24a6 6 0 0 0-8.49-8.49L5 10.5V19h8.5Z' }],
    ['line', { x1: '16', y1: '8', x2: '2', y2: '22' }],
    ['line', { x1: '17.5', y1: '15', x2: '9', y2: '15' }],
  ],
  sliders: [
    ['line', { x1: '4', y1: '6', x2: '20', y2: '6' }],
    ['line', { x1: '4', y1: '12', x2: '20', y2: '12' }],
    ['line', { x1: '4', y1: '18', x2: '20', y2: '18' }],
    ['circle', { cx: '9', cy: '6', r: '2', fill: 'var(--c-bg)' }],
    ['circle', { cx: '15', cy: '12', r: '2', fill: 'var(--c-bg)' }],
    ['circle', { cx: '10', cy: '18', r: '2', fill: 'var(--c-bg)' }],
  ],
  chat: [
    ['path', { d: 'M21 11.5a8.5 8.5 0 0 1-8.5 8.5 8.6 8.6 0 0 1-3.8-.9L3 21l1.9-5.7a8.5 8.5 0 1 1 16.1-3.8Z' }],
  ],
  chevronDown: [
    ['path', { d: 'm6 9 6 6 6-6' }],
  ],
  alert: [
    ['path', { d: 'M10.3 3.9 1.8 18.2A2 2 0 0 0 3.5 21h17a2 2 0 0 0 1.7-2.8L13.7 3.9a2 2 0 0 0-3.4 0Z' }],
    ['line', { x1: '12', y1: '9', x2: '12', y2: '13.5' }],
    ['line', { x1: '12', y1: '17', x2: '12.01', y2: '17' }],
  ],
  map: [
    ['circle', { cx: '6', cy: '7', r: '2.5' }],
    ['circle', { cx: '18', cy: '7', r: '2.5' }],
    ['circle', { cx: '12', cy: '18', r: '2.5' }],
    ['line', { x1: '8.2', y1: '7', x2: '15.8', y2: '7' }],
    ['line', { x1: '7.3', y1: '9.1', x2: '10.7', y2: '15.8' }],
    ['line', { x1: '16.7', y1: '9.1', x2: '13.3', y2: '15.8' }],
  ],
  terminal: [
    ['polyline', { points: '4 17 10 11 4 5' }],
    ['line', { x1: '12', y1: '19', x2: '20', y2: '19' }],
  ],
  refresh: [
    ['path', { d: 'M21 12a9 9 0 1 1-2.64-6.36' }],
    ['polyline', { points: '21 3 21 9 15 9' }],
  ],
  close: [
    ['line', { x1: '18', y1: '6', x2: '6', y2: '18' }],
    ['line', { x1: '6', y1: '6', x2: '18', y2: '18' }],
  ],
  copy: [
    ['rect', { x: '9', y: '9', width: '13', height: '13', rx: '2' }],
    ['path', { d: 'M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1' }],
  ],
  sparkles: [
    ['path', { d: 'M12 3l1.6 4.4L18 9l-4.4 1.6L12 15l-1.6-4.4L6 9l4.4-1.6Z' }],
    ['path', { d: 'M19 15l.9 2.1L22 18l-2.1.9L19 21l-.9-2.1L16 18l2.1-.9Z' }],
  ],
  power: [
    ['path', { d: 'M18.36 6.64a9 9 0 1 1-12.73 0' }],
    ['line', { x1: '12', y1: '2', x2: '12', y2: '12' }],
  ],
  plug: [
    ['path', { d: 'M12 22v-5' }],
    ['path', { d: 'M9 8V2' }],
    ['path', { d: 'M15 8V2' }],
    ['path', { d: 'M18 8v5a4 4 0 0 1-4 4h-4a4 4 0 0 1-4-4V8Z' }],
  ],
  cpu: [
    ['rect', { x: '6', y: '6', width: '12', height: '12', rx: '2' }],
    ['rect', { x: '9.5', y: '9.5', width: '5', height: '5', rx: '0.5' }],
    ['path', { d: 'M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4' }],
  ],
  database: [
    ['ellipse', { cx: '12', cy: '5', rx: '8', ry: '3' }],
    ['path', { d: 'M4 5v14c0 1.66 3.58 3 8 3s8-1.34 8-3V5' }],
    ['path', { d: 'M4 12c0 1.66 3.58 3 8 3s8-1.34 8-3' }],
  ],
  shield: [
    ['path', { d: 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z' }],
  ],
  eye: [
    ['path', { d: 'M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z' }],
    ['circle', { cx: '12', cy: '12', r: '3' }],
  ],
  archive: [
    ['rect', { x: '3', y: '4', width: '18', height: '4', rx: '1' }],
    ['path', { d: 'M5 8v11a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8' }],
    ['line', { x1: '10', y1: '13', x2: '14', y2: '13' }],
  ],
  check: [
    ['polyline', { points: '20 6 9 17 4 12' }],
  ],
  search: [
    ['circle', { cx: '11', cy: '11', r: '7' }],
    ['line', { x1: '20', y1: '20', x2: '16.65', y2: '16.65' }],
  ],
  edit: [
    ['path', { d: 'M12 20h9' }],
    ['path', { d: 'M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z' }],
  ],
  lock: [
    ['rect', { x: '5', y: '11', width: '14', height: '10', rx: '2' }],
    ['path', { d: 'M8 11V7a4 4 0 0 1 8 0v4' }],
  ],
  undo: [
    ['path', { d: 'M9 14 4 9l5-5' }],
    ['path', { d: 'M20 20v-7a4 4 0 0 0-4-4H4' }],
  ],
  eyeOff: [
    ['path', { d: 'M10.7 5.1A10.9 10.9 0 0 1 12 5c6.5 0 10 7 10 7a18.5 18.5 0 0 1-2.2 3.2' }],
    ['path', { d: 'M6.6 6.6A18.2 18.2 0 0 0 2 12s3.5 7 10 7a10.6 10.6 0 0 0 5.4-1.6' }],
    ['line', { x1: '2', y1: '2', x2: '22', y2: '22' }],
  ],
  arrowUp: [
    ['path', { d: 'M12 19V5' }],
    ['polyline', { points: '5 12 12 5 19 12' }],
  ],
};

/** Create an inline decorative SVG icon (aria-hidden) with clean stroke geometry. */
export function icon(name: IconName, size = 16, cls = 'ic'): SVGSVGElement {
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('width', String(size));
  svg.setAttribute('height', String(size));
  svg.setAttribute('fill', 'none');
  svg.setAttribute('stroke', 'currentColor');
  svg.setAttribute('stroke-width', '1.9');
  svg.setAttribute('stroke-linecap', 'round');
  svg.setAttribute('stroke-linejoin', 'round');
  svg.setAttribute('aria-hidden', 'true');
  if (cls) svg.setAttribute('class', cls);
  for (const [tag, attrs] of SHAPES[name]) {
    const child = document.createElementNS(SVG_NS, tag);
    for (const [k, v] of Object.entries(attrs)) child.setAttribute(k, v);
    svg.appendChild(child);
  }
  return svg;
}
