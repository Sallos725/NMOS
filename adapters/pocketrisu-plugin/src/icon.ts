// NMOS's icon: a one-stroke N with a memory node. A line icon in `currentColor`, so it takes the text colour of wherever
// it is drawn. PocketRisu passes `html` icons through DOMPurify without `style` or `class` (v1.13.0
// `PluginDefinedIcon.svelte`), so everything is a presentation attribute; it fills the box the host gives it.
export const NMOS_ICON = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="100%" height="100%" fill="none"'
  + ' stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
  + '<path d="M6 19V5l12 14V9.5"/><circle cx="18" cy="5.5" r="1.75" fill="currentColor"/></svg>';
