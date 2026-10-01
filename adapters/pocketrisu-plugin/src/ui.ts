// NMOS panel, rendered inside the plugin's own sandboxed iframe (full screen): status, inspector and
// settings tabs. Plugin-side settings are PocketRisu plugin args; model/recall/parser settings live in
// the sidecar and are saved together with one request.

import type { StatusInfo } from './core';
import { budgetAdvice } from './budget';
import type { ChatSwitch } from './chatoff';
import { PLUGIN_BUILD } from './build';
import { deadlineAdvice, formatMs } from './deadline';
import { configBody, connArgs, DEFAULT_DEADLINE_MS, DEFAULT_RESERVED_TOKENS, dirtySections, fillProject, MAX_DEADLINE_MS,
  PANEL_MAX_RESERVED_TOKENS, presetMatches, VERTEX_URL, type FormValues, type Section } from './form';
import { langOf, STRING_KEYS, t, type Lang, type StringKey } from './i18n';
import { closeOutcomes, entityNamed, inspectorApiPath, inspectorConversation, inspectorEntity, linkChoices, localTime,
  previewText, repairAction, safeFragment, sectionTarget, splitChoices } from './inspector';
import type { EntityRow, Preview, RepairAction } from './inspector';
import { alpha, PALETTE, paletteVars } from './palette';
import { routeFor } from './route';
import { usageText, type UsageTotal } from './usage';

export type Tab = 'status' | 'inspector' | 'settings';

/** The progress display on the chat screen (D28). */
export interface HudControl {
  /** Asks PocketRisu for main-page access and turns the display on if granted. */
  enable(): Promise<'on' | 'denied' | 'unsupported'>;
  disable(): Promise<void>;
  /** Why the display stopped for this session, if it did. */
  problem(): string | null;
  /** Background work was queued: follow it (this conversation, or the last one seen). */
  background(conversationId?: string): void;
}

export interface PanelDeps {
  api<T>(method: 'GET' | 'POST' | 'PUT', path: string, body?: unknown, timeoutMs?: number): Promise<T>;
  status(): Promise<StatusInfo>;
  getArg(key: string): Promise<string>;
  setArg(key: string, value: string | number): Promise<void>;
  show(): Promise<void>;
  hide(): Promise<void>;
  hud: HudControl;
  /** NMOS off and on for the chat open now (ADR 0048). */
  chat: ChatSwitch;
  /** Fetch a file from the sidecar and save it under `name` (an archive, ADR 0050); its size in bytes. */
  download(path: string, name: string): Promise<number>;
}

interface ServerConfig {
  llm: { url: string; model: string; api_key_set: boolean; json_mode: boolean };
  embeddings: { url: string; model: string; api_key_set: boolean; query_instruction: string };
  recall: { threshold: number; vector_min_sim: number; top_k: number; facts_limit: number };
  extraction: { backfill: number; summaries?: boolean; canon_facts?: boolean };
  parsers: { rules: unknown; source: string; active_rules: number; errors: string[] };
  queued_jobs?: number;
}

interface Preset { label: string | StringKey; url: string; model?: string }
/** `GET /v1/conversations/<id>/memory-mode` (ADR 0035). */
interface MemoryMode { strict: boolean; narrator: string | null; characters: string[] }

const LLM_PRESETS: Preset[] = [
  { label: 'preset.off', url: '' },
  { label: 'preset.ollama', url: 'http://host.docker.internal:11434/v1' },
  { label: 'OpenRouter', url: 'https://openrouter.ai/api/v1' },
  { label: 'OpenAI', url: 'https://api.openai.com/v1', model: 'gpt-4o-mini' },
  { label: 'Google Gemini', url: 'https://generativelanguage.googleapis.com/v1beta/openai', model: 'gemini-2.5-flash' },
  { label: 'Google Vertex AI', url: VERTEX_URL, model: 'google/gemini-2.5-flash' },
  { label: 'preset.custom', url: 'custom' },
];

const EMBED_PRESETS: Preset[] = [
  { label: 'preset.off', url: '' },
  { label: 'preset.ollama', url: 'http://host.docker.internal:11434/v1', model: 'qwen3-embedding:0.6b' },
  { label: 'OpenAI', url: 'https://api.openai.com/v1', model: 'text-embedding-3-small' },
  { label: 'preset.custom', url: 'custom' },
];

const PARSER_EXAMPLE = {
  rules: [
    { id: 'roster', kind: 'block', role: 'char', start: '<status>', end: '</status>', entity_line: '\\[(?P<entity>[^\\]]+)\\]' },
    { id: 'hp', kind: 'regex', pattern: 'HP\\s*[:：]\\s*(?P<value>\\d+\\s*/\\s*\\d+)', key: 'HP' },
  ],
};

const SECTION_TITLE: Record<Section, StringKey> = {
  conn: 'conn.title', llm: 'llm.title', emb: 'emb.title', tune: 'tune.title', rules: 'rules.title',
};

// Opaque on purpose: the host settings page behind the full-screen frame must not show through.
const CSS = `
html,body{margin:0;background:${PALETTE.bg}}
.nmos{${paletteVars()}}
.nmos{position:fixed;inset:0;overflow:auto;background:var(--c-bg);font:13.5px/1.6 system-ui,-apple-system,"Noto Sans KR",sans-serif;color:var(--c-text);-webkit-font-smoothing:antialiased}
.nmos *{box-sizing:border-box}
.nmos .wrap{max-width:760px;margin:0 auto;padding:20px 16px 32px}
.nmos header{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:8px}
.nmos h1{font-size:17px;font-weight:600;letter-spacing:-0.01em;margin:0;flex:1;white-space:nowrap;color:var(--c-text-strong)}
.nmos .tabs{display:flex;gap:6px;border-bottom:1px solid var(--c-line);margin:8px 0 8px}
.nmos .tabs button{background:none;border:0;border-bottom:2px solid transparent;border-radius:0;padding:9px 14px;color:var(--c-text-muted);font-size:13px;font-weight:500;transition:all .15s ease}
.nmos .tabs button:hover:not(:disabled){background:none;border-bottom-color:transparent;color:var(--c-text)}
.nmos .tabs button.on,.nmos .tabs button.on:hover:not(:disabled){color:var(--c-text-strong);border-bottom-color:var(--c-accent)}
.nmos .card{background:var(--c-surface);border:1px solid var(--c-line);border-radius:6px;padding:18px 20px;margin:16px 0}
.nmos h2{font-size:13.5px;font-weight:600;letter-spacing:-0.005em;color:var(--c-text-strong);margin:0 0 4px}
.nmos .sub{color:var(--c-text-muted);font-size:12px;line-height:1.55;margin:0 0 14px}
.nmos label{display:block;font-size:11.5px;font-weight:500;color:var(--c-text-muted);margin:12px 0 5px;letter-spacing:0.02em}
.nmos input,.nmos select,.nmos textarea{width:100%;background:var(--c-sunken);color:var(--c-text);border:1px solid var(--c-line-strong);border-radius:4px;padding:8px 11px;font:inherit;font-size:12.5px;transition:border-color .15s ease}
.nmos input:focus,.nmos select:focus,.nmos textarea:focus{border-color:${alpha('accent', 0.6)};outline:none;box-shadow:0 0 0 2px ${alpha('accent', 0.25)}}
.nmos header select{width:auto;padding:5px 9px;font-size:12px;border-radius:4px}
.nmos textarea{min-height:160px;font-family:ui-monospace,monospace;font-size:12px;line-height:1.6}
.nmos .row{display:flex;gap:12px;flex-wrap:wrap}.nmos .row>*{flex:1;min-width:140px}
.nmos .btns{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}
.nmos button{background:var(--c-raised);color:var(--c-text);border:1px solid var(--c-line-strong);border-radius:4px;padding:6px 13px;font:inherit;font-size:12.5px;cursor:pointer;transition:all .15s ease}
.nmos button:hover:not(:disabled){background:var(--c-raised-hover);color:var(--c-text-strong);border-color:var(--c-line-hover)}
.nmos button:focus-visible{outline:2px solid ${alpha('accent', 0.6)};outline-offset:1px}
.nmos button.primary{background:var(--c-accent);border-color:var(--c-accent);color:#fff}
.nmos button.primary:hover:not(:disabled){background:var(--c-accent-hover);border-color:var(--c-accent-hover)}
.nmos button.danger{background:${alpha('err', 0.15)};border-color:${alpha('err', 0.4)};color:var(--c-err)}
.nmos button.danger:hover:not(:disabled){background:${alpha('err', 0.25)};border-color:${alpha('err', 0.55)};color:var(--c-text-strong)}
.nmos button:disabled{opacity:.4;cursor:default}
.nmos .msg{margin-top:10px;font-size:12.5px;white-space:pre-wrap}
.nmos .ok{color:var(--c-ok)}.nmos .err{color:var(--c-err)}.nmos .warn{color:var(--c-warn)}.nmos .muted{color:var(--c-text-muted)}
.nmos .check{display:flex;align-items:center;gap:8px;margin-top:10px;font-size:12.5px;color:var(--c-text-soft)}.nmos .check input{width:auto}
.nmos .preview{margin:8px 0;padding:8px 10px;border-left:3px solid var(--c-line);font-size:12.5px;line-height:1.6}.nmos .preview>b{display:block;margin-bottom:4px}
.nmos .line{display:flex;align-items:baseline;gap:8px;margin:5px 0}
.nmos .dot{flex:none;width:7px;height:7px;border-radius:50%;background:var(--c-text-ghost);transform:translateY(-1px)}
.nmos .dot.ok{background:var(--c-ok)}.nmos .dot.err{background:var(--c-err)}.nmos .dot.warn{background:var(--c-warn)}
.nmos .pills{display:flex;gap:8px;flex-wrap:wrap}
.nmos .pill{border:1px solid var(--c-line-strong);border-radius:4px;padding:3px 10px;font-size:12px;color:var(--c-text-muted)}
.nmos .pill.on{border-color:${alpha('ok', 0.4)};background:${alpha('ok', 0.08)};color:var(--c-ok)}
.nmos .mono{font-family:ui-monospace,monospace;font-size:12px;word-break:break-all}
.nmos.wide>.wrap{max-width:1100px}
.nmos .insp{margin-top:14px}.nmos .insp+.sub{margin-top:18px}
.nmos .insp h1{font-size:16px;font-weight:600;margin:4px 0;color:var(--c-text-strong)}
.nmos .insp h2{margin:22px 0 8px;font-size:13.5px;font-weight:600;color:var(--c-text-strong)}
.nmos .insp .top{display:flex;justify-content:space-between;align-items:baseline;gap:12px}.nmos .insp .top p{margin:0}
.nmos .insp a{color:var(--c-link);text-decoration:none;cursor:pointer}
.nmos .insp a:hover{text-decoration:underline}
.nmos .insp .ref{display:block;font-family:ui-monospace,monospace;font-size:10.5px;color:var(--c-text-faint)}
.nmos .insp .wrap{max-width:none;margin:0;padding:0;overflow-x:auto}
.nmos .insp table{width:100%;border-collapse:collapse;font-size:12.5px}
.nmos .insp th,.nmos .insp td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--c-line);vertical-align:top}
.nmos .insp th{font-weight:500;color:var(--c-text-faint);font-size:11.5px;letter-spacing:0.02em;white-space:nowrap}
.nmos .insp tr:hover td{background:rgba(255,255,255,0.02)}
.nmos .insp .chip{display:inline-block;padding:1px 6px;border-radius:3px;background:var(--c-raised);border:1px solid var(--c-line);font-size:11.5px;color:var(--c-text-soft)}
.nmos .insp span.rp{display:inline-flex;flex-wrap:wrap;align-items:center;gap:5px;margin-left:6px;vertical-align:middle}
.nmos .insp span.rp input,.nmos .insp span.rp select{width:auto;padding:3px 7px;font-size:11.5px;border-radius:3px}
.nmos .insp span.rp input[type=text]{width:12em}.nmos .insp span.rp input.turn{width:7em}
.nmos button.mini{padding:2px 8px;font-size:11.5px;border-radius:3px}
.nmos .inspbar{position:sticky;top:0;z-index:1;background:var(--c-bg);padding:10px 0;margin-top:4px}
.nmos .help{margin:8px 0 0}.nmos .help summary{cursor:pointer;color:var(--c-text-muted)}.nmos .help p{margin:6px 0 0}
.nmos .packet{margin:8px 0 0;max-height:420px;overflow:auto;background:var(--c-sunken);border:1px solid var(--c-line);border-radius:4px;padding:12px;font-family:ui-monospace,monospace;font-size:12px;line-height:1.6;color:var(--c-text-soft);white-space:pre-wrap;word-break:break-word}
.nmos .insp.busy{opacity:.5;transition:opacity .15s}
.nmos .insp details>summary{cursor:pointer;list-style:none}.nmos .insp details>summary::-webkit-details-marker{display:none}
.nmos .insp details>summary h2{display:inline-block}
.nmos .insp details>summary h2::before{content:"▸ ";color:var(--c-text-ghost)}.nmos .insp details[open]>summary h2::before{content:"▾ "}
.nmos .insp .n{color:var(--c-text-muted);font-weight:400;font-size:11.5px}
.nmos .insp .toc{font-size:12.5px;line-height:1.9;margin:8px 0}.nmos .insp a.warn{color:var(--c-warn)}
.nmos .insp .who{display:flex;align-items:center;gap:8px;margin:10px 0}.nmos .insp .who select{width:auto;min-width:180px;padding:5px 8px}
.nmos .insp details.meta{font-size:11.5px;margin-top:2px;color:var(--c-text-muted)}.nmos .insp details.meta p{margin:4px 0}
.nmos .bar{position:sticky;bottom:0;background:${alpha('surface', 0.95)};backdrop-filter:blur(12px);border-top:1px solid var(--c-line-strong);padding:12px max(16px,calc((100% - 760px) / 2 + 16px));display:flex;align-items:center;gap:10px;flex-wrap:wrap;z-index:10}
.nmos .bar .text{flex:1;min-width:160px;font-size:12.5px}
`;

type Attrs = Record<string, string | number | boolean | undefined>;

function el<K extends keyof HTMLElementTagNameMap>(tag: K, attrs: Attrs = {}, ...children: (Node | string)[]): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === undefined || v === false) continue;
    if (k === 'class') node.className = String(v);
    else if (k === 'text') node.textContent = String(v);
    else node.setAttribute(k, v === true ? '' : String(v));
  }
  for (const child of children) node.append(child);
  return node;
}

/** An archive's file name: what it holds and when, in local time (`nmos-chat-20260929-181500.nmos.zip`). */
export function archiveName(kind: string, at: Date): string {
  const p = (n: number) => String(n).padStart(2, '0');
  const stamp = `${at.getFullYear()}${p(at.getMonth() + 1)}${p(at.getDate())}-${p(at.getHours())}${p(at.getMinutes())}${p(at.getSeconds())}`;
  return `nmos-${kind}-${stamp}.nmos.zip`;
}

function say(target: HTMLElement, text: string, kind: 'ok' | 'err' | 'warn' | 'muted' = 'muted'): void {
  target.className = `${target.classList.contains('text') ? 'text' : 'msg'} ${kind}`;
  target.textContent = text;
}

function field(labelText: string, input: HTMLElement): HTMLElement {
  return el('div', {}, el('label', { text: labelText }), input);
}

function presetIndex(presets: Preset[], url: string): number {
  if (!url) return 0;
  const i = presets.findIndex((p) => presetMatches(p.url, url));
  return i >= 0 ? i : presets.length - 1;
}

function errorText(lang: Lang, error: unknown): string {
  const text = error instanceof Error ? error.message : String(error);
  return text.replace(/^\/v1\/\S+ -> HTTP 422: /, t(lang, 'invalid')).replace(/^\/v1\/\S+ -> /, t(lang, 'sidecar_error'));
}

let current: { root: HTMLElement; select(tab: Tab): void } | null = null;

/** Open the NMOS panel on `tab` (or switch tabs if it is already open). */
export async function openPanel(deps: PanelDeps, tab: Tab): Promise<void> {
  if (current && document.body.contains(current.root)) {
    current.select(tab);
    await deps.show();
    return;
  }
  if (!document.getElementById('nmos-style')) document.head.append(el('style', { id: 'nmos-style', text: CSS }));
  const lang = langOf(await deps.getArg('language'));
  current = await render(deps, lang, tab);
  await deps.show();
}

async function render(deps: PanelDeps, lang: Lang, tab: Tab): Promise<{ root: HTMLElement; select(tab: Tab): void }> {
  const L = (key: StringKey, vars?: Record<string, string | number>) => t(lang, key, vars);
  const root = el('div', { class: 'nmos', id: 'nmos-panel' });
  const wrap = el('div', { class: 'wrap' });
  root.append(wrap);

  // --- header: title, language, close, tabs ---------------------------------------------------
  const language = el('select', { 'aria-label': L('language') },
    el('option', { value: 'ko', text: '한국어' }), el('option', { value: 'en', text: 'English' }));
  language.value = lang;
  const close = el('button', { text: L('close') });
  const tabStatus = el('button', { text: L('tab.status') });
  const tabInspector = el('button', { text: L('tab.inspector') });
  const tabSettings = el('button', { text: L('tab.settings') });
  wrap.append(el('header', {}, el('h1', { text: L('title') }), language, close),
    el('nav', { class: 'tabs' }, tabStatus, tabInspector, tabSettings));
  const statusView = el('div');
  const inspectorView = el('div');
  const settingsView = el('div');
  wrap.append(statusView, inspectorView, settingsView);
  let shown: Tab = tab;

  // --- status tab ------------------------------------------------------------------------------
  let usageRound = 0; // a refresh or another chat's card makes an older answer stale
  async function refreshStatus(): Promise<void> {
    statusView.replaceChildren(el('div', { class: 'card muted', text: L('status.checking') }));
    const s = await deps.status();
    const base = s.sidecarUrl.replace(/\/+$/, '');
    const conn = el('div', { class: 'card' }, el('h2', { text: L('status.sidecar') }));
    if (s.connected) {
      conn.append(el('div', { class: 'line' }, el('span', { class: 'dot ok' }),
        el('span', { text: `${L('status.connected')} · NMOS ${s.version ?? ''}` })),
      el('div', { class: 'mono muted', text: base }));
      // A plugin from another build than the sidecar's (ADR 0037): features on one side are missing on the other.
      if (s.pluginExpected && s.pluginExpected !== PLUGIN_BUILD) {
        conn.append(el('div', { class: 'line warn' }, el('span', { class: 'dot warn' }),
          el('span', { text: L('status.plugin_mismatch', { mine: PLUGIN_BUILD, theirs: s.pluginExpected }) })));
      } else if (s.pluginExpected) {
        conn.append(el('div', { class: 'muted', text: L('status.plugin_ok', { b: PLUGIN_BUILD }) }));
      }
    } else {
      conn.append(el('div', { class: 'line' }, el('span', { class: 'dot err' }),
        el('span', { class: 'err', text: `${L('status.unreachable')}: ${base}` })),
      el('div', { class: 'muted', text: s.error ?? '' }), el('p', { class: 'sub', text: L('status.fix') }));
    }
    if (!s.enabled) conn.append(el('div', { class: 'line warn' }, el('span', { class: 'dot warn' }),
      el('span', { text: L('status.memory_off') })));

    const features = el('div', { class: 'card' }, el('h2', { text: L('status.features') }));
    const pills = el('div', { class: 'pills' });
    for (const [key, name] of [['state', 'feature.state'], ['extraction', 'feature.extraction'], ['vectors', 'feature.vectors']] as const) {
      const on = Boolean(s.features?.[key]);
      pills.append(el('span', { class: on ? 'pill on' : 'pill', text: `${L(name)} ${on ? L('on') : L('off')}` }));
    }
    features.append(s.connected ? pills : el('div', { class: 'muted', text: '—' }));

    const lastCard = el('div', { class: 'card' }, el('h2', { text: L('status.last') }));
    if (s.last) {
      const kind = s.last.outcome === 'injected' ? 'ok' : s.last.outcome === 'failed' ? 'err' : 'muted';
      const what = s.last.outcome === 'injected' ? L('outcome.injected', { n: s.last.packetChars })
        : s.last.outcome === 'nothing-relevant' ? L('outcome.nothing') : L('outcome.failed');
      lastCard.append(el('div', { class: 'line' }, el('span', { class: `dot ${kind}` }), el('span', { text: what })),
        el('div', { class: 'muted', text: `${L('status.ago', { n: Math.round((Date.now() - s.last.at) / 1000) })} · ${s.last.ms}ms` }));
      if (s.last.packet) lastCard.append(el('details', { class: 'help' },
        el('summary', { text: L('status.packet') }), el('pre', { class: 'packet', text: s.last.packet })));
      if (s.last.error) lastCard.append(el('div', { class: 'mono muted', text: s.last.error }));
    } else {
      lastCard.append(el('div', { class: 'muted', text: L('status.none') }));
    }

    const cards: HTMLElement[] = [conn, features, lastCard];
    // A long chat that runs out of time gets no memory at all (fail open), silently: say it first, with
    // the value to set, and warn before it happens (owner decision on audit A-09).
    const advice = deadlineAdvice(s.last);
    if (advice) {
      const open = el('button', { text: L('deadline.open_settings') });
      open.addEventListener('click', () => select('settings'));
      const took = advice.tookMs === null ? '' : L('deadline.took', { n: formatMs(advice.tookMs) });
      const text = advice.level === 'over'
        ? L('deadline.over', { d: formatMs(advice.deadlineMs), took, s: formatMs(advice.suggestMs) })
        : L('deadline.near', { d: formatMs(advice.deadlineMs), n: formatMs(advice.tookMs ?? 0), s: formatMs(advice.suggestMs) });
      cards.unshift(el('div', { class: 'card' },
        el('h2', { class: advice.level === 'over' ? 'err' : 'warn', text: L(`deadline.${advice.level}.title`) }),
        el('p', { class: 'sub', text }), el('div', { class: 'btns' }, open)));
    }
    // Memory the budget left out (ADR 0036): say how much, and offer the budget that holds it all.
    const current = Number(await deps.getArg('reserved_memory_tokens')) || DEFAULT_RESERVED_TOKENS;
    const budget = budgetAdvice(s.last, current);
    if (budget) {
      const apply = el('button', { class: 'primary', text: L('budget.apply', { n: budget.suggest }) });
      const msg = el('div', { class: 'msg' });
      apply.addEventListener('click', async () => {
        apply.disabled = true;
        try {
          await deps.setArg('reserved_memory_tokens', budget.suggest);
          say(msg, L('budget.applied', { n: budget.suggest, d: budget.suggest - current }), 'ok');
        } catch (error) { apply.disabled = false; say(msg, errorText(lang, error), 'err'); }
      });
      const text = L(budget.all ? 'budget.text' : 'budget.text_more', { m: budget.offered, c: budget.cut, b: budget.budget,
        s: budget.suggest, d: budget.suggest - current });
      cards.splice(1, 0, el('div', { class: 'card' }, el('h2', { class: 'warn', text: L('budget.title', { c: budget.cut }) }),
        el('p', { class: 'sub', text }), el('div', { class: 'btns' }, apply), msg));
    }
    // Recall without vectors (PHASE-15 Q5, K34): on the owner's production 70 % of requests were, silently.
    if (s.last?.vectors === 'fallback') {
      cards.splice(1, 0, el('div', { class: 'card' }, el('h2', { class: 'warn', text: L('vectors.title') }),
        el('p', { class: 'sub', text: L('vectors.text') })));
    }
    const problem = deps.hud.problem();
    if (Number(await deps.getArg('hud')) !== 1) {
      const turnOn = el('button', { text: L('hud.enable') });
      const msg = el('div', { class: 'msg' });
      turnOn.addEventListener('click', async () => {
        turnOn.disabled = true;
        const result = await deps.hud.enable();
        if (result === 'on') return void refreshStatus();
        turnOn.disabled = false;
        say(msg, L(result === 'denied' ? 'hud.denied' : 'hud.unsupported'), 'warn');
      });
      cards.push(el('div', { class: 'card' }, el('h2', { text: L('hud.title') }),
        el('div', { class: 'muted', text: L('hud.hint') }), el('div', { class: 'btns' }, turnOn), msg));
    } else if (problem) {
      cards.push(el('div', { class: 'card' }, el('h2', { text: L('hud.title') }),
        el('div', { class: 'warn', text: L('hud.broken', { e: problem }) })));
    }
    // This chat first (ADR 0048): the switch is what the owner opened the panel for, often from the sidebar.
    cards.unshift(await chatCard(s.enabled, s.connected));
    const refresh = el('button', { text: L('refresh') });
    refresh.addEventListener('click', () => void refreshStatus());
    statusView.replaceChildren(...cards, el('div', { class: 'btns' }, refresh));
  }

  /** "This chat": whether NMOS is on for the chat open now, and the switch. */
  async function chatCard(enabled: boolean, connected: boolean): Promise<HTMLElement> {
    const card = el('div', { class: 'card' }, el('h2', { text: L('chat.title') }));
    let state;
    try {
      state = await deps.chat.current();
    } catch (error) {
      card.append(el('div', { class: 'err', text: errorText(lang, error) }));
      return card;
    }
    if (state.id === null) {
      card.append(el('div', { class: 'muted', text: L('chat.none') }));
      return card;
    }
    const id = state.id;
    const off = state.off;
    const flip = el('button', { class: off ? 'primary' : '', text: L(off ? 'chat.turn_on' : 'chat.turn_off') });
    const msg = el('div', { class: 'msg' });
    flip.addEventListener('click', async () => {
      flip.disabled = true;
      try {
        await deps.chat.set(id, !off);
        await refreshStatus();
      } catch (error) { flip.disabled = false; say(msg, errorText(lang, error), 'err'); }
    });
    card.append(el('div', { class: off ? 'line warn' : 'line' }, el('span', { class: off ? 'dot warn' : 'dot ok' }),
      el('span', { text: L(off ? 'chat.off' : 'chat.on') })),
    el('p', { class: 'sub', text: L(off ? 'chat.off_sub' : 'chat.on_sub') }), el('div', { class: 'btns' }, flip), msg);
    // What this chat's memory cost (PHASE-17 Q4) arrives after the card: the switch is never kept waiting for it.
    if (connected) {
      const shownFor = ++usageRound;
      void usageLine(id).then((spent) => {
        if (spent && shownFor === usageRound && card.isConnected) card.insertBefore(spent, card.querySelector('p.sub'));
      });
    }
    // The global switch wins (ADR 0048 §5): say so rather than show this chat as working.
    if (!enabled) card.insertBefore(el('div', { class: 'line warn' }, el('span', { class: 'dot warn' }),
      el('span', { text: L('chat.all_off') })), card.children[1] ?? null);
    return card;
  }

  /** What this chat's memory cost in NMOS's own model calls (PHASE-17 Q4), and the facts a re-extraction dropped
   * (PHASE-22 Q6). Nothing when the sidecar does not know the chat or does not answer: the card is about the switch. */
  async function usageLine(hostChatId: string): Promise<HTMLElement | null> {
    try {
      const chats = await deps.api<{ id: string; host_chat_ref: string }[]>('GET',
        `/v1/conversations?host=pocketrisu&host_chat_ref=${encodeURIComponent(hostChatId)}`, undefined, 5000);
      const chat = chats.find((c) => c.host_chat_ref === hostChatId);
      if (!chat) return null;
      const cov = await deps.api<{ usage?: { total?: UsageTotal }; dropped?: number }>('GET',
        `/v1/conversations/${encodeURIComponent(chat.id)}/coverage?usage=true`, undefined, 5000);
      const lines = [cov.usage?.total ? el('div', { class: 'muted', text: usageText(cov.usage.total, lang) }) : null,
        // the facts a re-extraction dropped (PHASE-22 Q6), when there are any
        typeof cov.dropped === 'number' && cov.dropped > 0
          ? el('div', { class: 'muted', text: L('chat.dropped', { n: cov.dropped }) }) : null].filter((x): x is HTMLDivElement => x !== null);
      return lines.length ? el('div', {}, ...lines) : null;
    } catch {
      return null;
    }
  }

  // --- inspector tab ---------------------------------------------------------------------------
  // The sidecar's own inspector pages, shown in place: the plugin frame cannot open a tab (H15).
  // Links are handled here; following one would navigate the plugin frame itself.
  let inspectorPath = '/v1/inspector';
  let shownPath: string | null = null; // the page on screen, once it has loaded
  let loads = 0; // the latest load wins: an answer to an older one is dropped
  // Pages read before this one and where the reader was on them, for the Back button.
  interface Place { path: string; scroll: number; open: string[] }
  const visited: Place[] = [];
  const inspectorBody = el('div', { class: 'insp' });
  const inspectorBack = el('button', { text: L('insp.back') });
  const inspectorRefresh = el('button', { text: L('refresh') });
  const inspectorAddress = el('p', { class: 'sub mono' });
  // Per-chat actions (D22, ADR 0009) on a conversation page: they run in the sidecar.
  const historyButton = el('button', { text: L('act.history') });
  const rebuildButton = el('button', { text: L('act.rebuild') });
  const deleteButton = el('button', { text: L('act.delete') });
  const exportButton = el('button', { text: L('exp.chat') });
  const actionMsg = el('div', { class: 'msg' });
  const actions = el('div', {}, el('div', { class: 'btns' }, historyButton, rebuildButton, exportButton, deleteButton),
    el('details', { class: 'sub help' }, el('summary', { text: L('act.help') }), el('p', { text: L('act.sub') })));
  // The message sits outside the actions so a result stays visible after a delete returns to the list.
  // Back and Refresh stay in reach while reading far down a page.
  // On an entity's page: the owner joins it with another entity of its type, or undoes a join (ADR 0025).
  const linkCard = el('div', { class: 'card', style: 'display:none' });
  // On a conversation's page: how memory treats what only some characters know (ADR 0035).
  const modeCard = el('div', { class: 'card', style: 'display:none' });
  // The owner's repairs (ADR 0044): the threads picked for closing together, and the close controls on the page now,
  // by thread (one can show twice: under Threads and under Needs attention; its controls stay in step).
  const picked = new Set<string>();
  const chosen = new Map<string, string>(); // the outcome picked for a thread, kept through a refresh
  let closers = new Map<string, { first?: string; boxes: HTMLInputElement[]; selects: HTMLSelectElement[] }>();
  const bulkClose = el('button');
  const bulkBar = el('div', { class: 'btns', style: 'display:none' }, bulkClose);
  inspectorView.append(el('div', { class: 'btns inspbar' }, inspectorBack, inspectorRefresh), actions, actionMsg,
    bulkBar, modeCard, linkCard, inspectorBody, inspectorAddress);
  function updateBulk(): void {
    bulkBar.style.display = picked.size ? '' : 'none';
    bulkClose.textContent = L('rp.bulk', { n: picked.size });
  }
  /** The outcome a close of this thread sends: the one picked on the page, else its kind's default. */
  function outcomeOf(item: string): Record<string, string> {
    const c = closers.get(item);
    const outcome = c?.selects[0]?.value ?? c?.first;
    return outcome ? { outcome } : {};
  }
  /** The controls for one repair the page marks. */
  function repairControls(action: RepairAction): Node[] {
    if (action.kind === 'thread_close') return closeControls(action);
    const n = action.kind === 'fact_correct' ? L(action.extra === 'object' ? 'rp.field_object' : 'rp.field_value')
      : action.extra ?? '';
    const button = el('button', { class: 'mini', text: L(`rp.${action.kind}` as StringKey, { n }) });
    const spot = el('div');
    button.addEventListener('click', () => {
      if (action.kind === 'fact_correct') correctForm(action, button);
      else if (action.kind === 'undo' && action.extra === 'name_split') void undoSplit(action, button, spot);
      else void repairNow(action, button);
    });
    return [button, spot];
  }
  /** A close: the outcomes of the thread's kind (the default first), a box to close several at once, the button. */
  function closeControls(action: RepairAction): Node[] {
    const item = action.item;
    const choices = closeOutcomes(action.extra);
    let c = closers.get(item);
    if (!c) closers.set(item, c = { first: choices[0], boxes: [], selects: [] });
    const group = c;
    const nodes: Node[] = [];
    const box = el('input', { type: 'checkbox', 'aria-label': L('rp.select') });
    box.checked = picked.has(item);
    box.addEventListener('change', () => {
      if (box.checked) picked.add(item); else picked.delete(item);
      for (const other of group.boxes) other.checked = box.checked;
      updateBulk();
    });
    group.boxes.push(box);
    nodes.push(box);
    if (choices.length > 1) {
      const select = el('select', { class: 'mini', 'aria-label': L('rp.outcome') },
        ...choices.map((o) => el('option', { value: o, text: outcomeLabel(o) })));
      const was = chosen.get(item);
      if (was && choices.includes(was)) select.value = was;
      select.addEventListener('change', () => {
        chosen.set(item, select.value);
        for (const other of group.selects) other.value = select.value;
      });
      group.selects.push(select);
      nodes.push(select);
    }
    const button = el('button', { class: 'mini', text: L('rp.thread_close') });
    button.addEventListener('click', () => void repairNow(action, button, outcomeOf(item)));
    nodes.push(button);
    return nodes;
  }
  function outcomeLabel(outcome: string): string {
    const key = `oc.${outcome}` as StringKey;
    return STRING_KEYS.includes(key) ? L(key) : outcome;
  }
  /** A correction's form in place of its button (PHASE-13 Q5): the new object or value, and the turn it takes effect
   * (empty: the fact's own turn). */
  function correctForm(action: RepairAction, button: HTMLButtonElement): void {
    const spot = button.parentElement;
    if (!spot) return;
    const field = action.extra === 'object' ? 'object' : 'value';
    const text = el('input', { type: 'text', placeholder: L('rp.correct_prompt', { f: L(`rp.field_${field}`) }),
      'aria-label': L(`rp.field_${field}`) });
    const turn = el('input', { type: 'number', min: '0', step: '1', class: 'turn', placeholder: L('rp.turn_hint'),
      'aria-label': L('rp.turn') });
    const save = el('button', { class: 'mini', text: L('save') });
    const cancel = el('button', { class: 'mini', text: L('cancel') });
    cancel.addEventListener('click', () => spot.replaceChildren(...repairControls(action)));
    save.addEventListener('click', () => {
      const next = text.value.trim();
      if (!next) return void text.focus();
      const body: Record<string, unknown> = { [field === 'object' ? 'new_object' : 'new_value']: next };
      const at = turn.value.trim();
      if (at) {
        const n = Number(at);
        if (!Number.isInteger(n) || n < 0) return void say(actionMsg, L('rp.bad_turn'), 'err');
        body.turn = n;
      }
      void repairNow(action, save, body);
    });
    spot.replaceChildren(el('span', { class: 'rpform' }, text, turn, save, cancel));
    text.focus();
  }
  /** The undo of a name split, previewed like a join (PHASE-20 Q2). */
  async function undoSplit(action: RepairAction, button: HTMLButtonElement, spot: HTMLElement): Promise<void> {
    const conversation = inspectorConversation(inspectorPath);
    if (!conversation) return;
    const base = `/v1/conversations/${conversation}/repairs/${action.item}`;
    await withPreview(spot, button, `${base}/remove/preview`, {}, 'pv.confirm_undo', async (expect) => {
      await deps.api('POST', `${base}/remove`, { expect }, 15_000);
      say(actionMsg, L('rp.undone'), 'ok');
      await showInspector();
    });
  }
  async function repairNow(action: RepairAction, button: HTMLButtonElement, extra: Record<string, unknown> = {}):
    Promise<void> {
    const conversation = inspectorConversation(inspectorPath);
    if (!conversation) return;
    let path = `/v1/conversations/${conversation}/repairs`;
    let body: Record<string, unknown> = { kind: action.kind, item: action.item, ...extra };
    if (action.kind === 'undo') {
      path = `${path}/${action.item}/remove`;
      body = {};
    } else if (action.kind === 'secret_found_out' || action.kind === 'secret_keep') {
      body.character = action.extra;
    }
    button.disabled = true;
    try {
      await deps.api('POST', path, body, 15_000);
      picked.delete(action.item);
      updateBulk();
      say(actionMsg, L(action.kind === 'undo' ? 'rp.undone' : 'rp.done'), 'ok');
      await showInspector();
    } catch (error) {
      say(actionMsg, errorText(lang, error), 'err');
      button.disabled = false;
    }
  }
  bulkClose.addEventListener('click', async () => {
    const conversation = inspectorConversation(inspectorPath);
    if (!conversation || !picked.size) return;
    bulkClose.disabled = true;
    let done = 0;
    let failed = 0;
    let firstError: unknown = null;
    for (const item of Array.from(picked)) { // one refusal does not stop the others
      try {
        await deps.api('POST', `/v1/conversations/${conversation}/repairs`,
          { kind: 'thread_close', item, ...outcomeOf(item) }, 15_000);
        picked.delete(item);
        done += 1;
      } catch (error) {
        failed += 1;
        firstError ??= error;
      }
    }
    if (failed) {
      say(actionMsg, `${L('rp.bulk_done', { n: done })} ${L('rp.bulk_failed', { n: failed })} ${errorText(lang, firstError)}`,
        'err');
    } else {
      say(actionMsg, L('rp.bulk_done', { n: done }), 'ok');
    }
    bulkClose.disabled = false;
    updateBulk();
    await showInspector();
  });
  let actionConversation: string | null = null;
  function place(): Place {
    const open = Array.from(inspectorBody.querySelectorAll<HTMLDetailsElement>('details[id]')).filter((d) => d.open);
    return { path: inspectorPath, scroll: root.scrollTop, open: open.map((d) => d.id) };
  }
  function restore(at: Place): void {
    for (const d of Array.from(inspectorBody.querySelectorAll<HTMLDetailsElement>('details[id]'))) d.open = at.open.includes(d.id);
    root.scrollTop = at.scroll;
  }
  /** Adapt a page to the panel: times in the viewer's zone, the character links as a drop-down. */
  function enhance(page: DocumentFragment): void {
    closers = new Map();
    for (const spot of Array.from(page.querySelectorAll('span.rp[data-repair]'))) {
      const action = repairAction(spot.getAttribute('data-repair'));
      if (action) spot.replaceChildren(...repairControls(action));
    }
    for (const item of Array.from(picked)) if (!closers.has(item)) picked.delete(item); // closed or gone since
    updateBulk();
    for (const span of Array.from(page.querySelectorAll('span.ts[title]'))) {
      const shown = localTime(span.getAttribute('title') ?? '', lang);
      if (!shown) continue;
      span.textContent = shown.text;
      span.setAttribute('title', shown.title);
    }
    const who = page.querySelector('p.who');
    if (!who) return;
    const name = who.querySelector('span')?.textContent ?? '';
    const picker = el('select', { 'aria-label': name });
    for (const choice of Array.from(who.querySelectorAll('a, b'))) {
      const path = choice.tagName === 'B' ? inspectorPath : inspectorApiPath(choice.getAttribute('href'));
      if (path) picker.append(el('option', { value: path, text: choice.textContent ?? '', selected: choice.tagName === 'B' }));
    }
    picker.addEventListener('change', () => go(picker.value));
    who.replaceChildren(el('span', { class: 'muted', text: name }), picker);
  }
  function go(path: string): void {
    if (path === inspectorPath) return void showInspector();
    if (shownPath) visited.push(place());
    if (visited.length > 30) visited.shift();
    void showInspector(path);
  }
  async function showInspector(path = inspectorPath, at?: Place): Promise<void> {
    const load = ++loads;
    const again = path === shownPath; // a refresh keeps the reader's place and open sections
    const keep = at ?? (again ? place() : undefined);
    inspectorPath = path;
    inspectorBack.style.display = visited.length ? '' : 'none';
    const conversation = inspectorConversation(path);
    if (conversation !== actionConversation) {
      actionConversation = conversation;
      say(actionMsg, '');
      disarm();
      picked.clear();
      updateBulk();
    }
    actions.style.display = conversation ? '' : 'none';
    const shownEntity = inspectorEntity(path);
    if (!shownEntity) linkCard.style.display = 'none';
    if (!conversation || shownEntity) modeCard.style.display = 'none';
    if (again) {
      inspectorBody.classList.add('busy'); // the old page stays until the new one is there
    } else {
      shownPath = null;
      inspectorBody.replaceChildren(el('div', { class: 'card muted', text: L('insp.loading') }));
    }
    // Only a sidecar the browser reaches itself can be opened in a tab; a server-routed one (Docker
    // name, LAN address behind HTTPS) is reachable from the PocketRisu server only.
    const base = ((await deps.getArg('sidecar_url')) || 'http://127.0.0.1:8790').replace(/\/+$/, '');
    const direct = routeFor(base, await deps.getArg('route')) === 'direct';
    inspectorAddress.textContent = direct ? L('insp.browser', { url: `${base}/inspector${lang === 'en' ? '?lang=en' : ''}` }) : '';
    try {
      const r = await deps.api<{ html: string }>('GET', `${path}${lang === 'en' ? '?lang=en' : ''}`, undefined, 15_000);
      if (load !== loads) return;
      const page = safeFragment(r.html);
      enhance(page);
      inspectorBody.replaceChildren(page);
      shownPath = path;
      if (keep) restore(keep);
      else root.scrollTop = 0;
      if (shownEntity) void showLinks(shownEntity.conversation, shownEntity.entity, load);
      else if (conversation) void showMode(conversation, load);
    } catch (error) {
      if (load !== loads) return;
      shownPath = null;
      inspectorBody.replaceChildren(el('div', { class: 'card err', text: errorText(lang, error) }));
    } finally {
      if (load === loads) inspectorBody.classList.remove('busy');
    }
  }
  async function showMode(conversation: string, load: number): Promise<void> {
    let mode: MemoryMode;
    try {
      mode = await deps.api<MemoryMode>('GET', `/v1/conversations/${conversation}/memory-mode`, undefined, 15_000);
    } catch {
      modeCard.style.display = 'none'; // an older sidecar has no memory mode
      return;
    }
    if (load !== loads) return;
    const strict = el('input', { type: 'checkbox' });
    strict.checked = mode.strict;
    const narrators: [string, string][] = [['', L('mode.narrator_none')], ['{{user}}', L('mode.narrator_user')],
      ...mode.characters.map((n): [string, string] => [n, n])];
    if (mode.narrator && !narrators.some(([v]) => v === mode.narrator)) narrators.push([mode.narrator, mode.narrator]);
    const narrator = el('select', { 'aria-label': L('mode.narrator') },
      ...narrators.map(([value, text]) => el('option', { value, text })));
    narrator.value = mode.narrator ?? '';
    const save = el('button', { class: 'primary', text: L('mode.save') });
    const msg = el('div', { class: 'msg' });
    save.addEventListener('click', async () => {
      save.disabled = true;
      try {
        const r = await deps.api<MemoryMode>('PUT', `/v1/conversations/${conversation}/memory-mode`,
          { strict: strict.checked, narrator: narrator.value || null }, 15_000);
        say(msg, L('mode.saved', { s: L(r.strict ? 'mode.on' : 'mode.off'), n: r.narrator ?? L('mode.narrator_none') }), 'ok');
      } catch (error) { say(msg, errorText(lang, error), 'err'); } finally { save.disabled = false; }
    });
    modeCard.replaceChildren(el('h2', { text: L('mode.title') }), el('p', { class: 'sub', text: L('mode.sub') }),
      el('div', { class: 'check' }, strict, el('span', { text: L('mode.strict') })),
      el('p', { class: 'sub', text: L('mode.strict_sub') }),
      el('div', { class: 'row' }, field(L('mode.narrator'), narrator)), el('p', { class: 'sub', text: L('mode.narrator_sub') }),
      el('div', { class: 'btns' }, save), msg);
    modeCard.style.display = '';
  }
  /** A join, split or undo shown before it is made (PHASE-20 Q9): the preview in `spot`, then the owner's confirm
   * sends the preview's fingerprint; a 409 (memory changed since) shows the new preview instead. `reextract`, for an
   * undo of a join: a box to re-extract the turns extracted while it held (Q7, off by default). */
  const previewRound = new WeakMap<HTMLElement, number>();
  /** A new preview round for `spot`: an answer of an earlier round (the owner picked another name, or cancelled)
   * is dropped instead of replacing what is shown. */
  function nextRound(spot: HTMLElement): number {
    const n = (previewRound.get(spot) ?? 0) + 1;
    previewRound.set(spot, n);
    return n;
  }
  async function withPreview(spot: HTMLElement, button: HTMLButtonElement, previewPath: string,
    previewBody: Record<string, unknown>, confirmKey: StringKey,
    commit: (expect: string, reextract: number[] | null) => Promise<void>, changed = false): Promise<void> {
    const round = nextRound(spot);
    button.disabled = true;
    let p: Preview;
    try {
      p = await deps.api<Preview>('POST', previewPath, previewBody, 15_000);
    } catch (error) {
      if (previewRound.get(spot) !== round) return;
      say(actionMsg, errorText(lang, error), 'err');
      button.disabled = false;
      return;
    }
    if (previewRound.get(spot) !== round) return;
    const lines = previewText(p, (key, vars) => L(key, vars), outcomeLabel);
    const box = el('div', { class: 'preview' }, el('b', { text: L('pv.title') }),
      ...(changed ? [el('div', { class: 'warn', text: L('pv.changed') })] : []),
      ...lines.map((text) => el('div', { class: /^(주의|Note):/.test(text) ? 'warn' : '', text })));
    // Offered only when the undo leaves two entities (else the names stay one and nothing is re-extracted).
    const list = p.after.length > 1 ? p.reextract?.list ?? [] : [];
    const turns = list.length;
    const again = el('input', { type: 'checkbox', 'aria-label': L('pv.reextract', { n: turns }) });
    if (turns > 0) box.append(el('div', { class: 'check' }, again, el('span', { text: L('pv.reextract', { n: turns }) })));
    const ok = el('button', { class: 'mini', text: L(confirmKey) });
    const cancel = el('button', { class: 'mini', text: L('cancel') });
    cancel.addEventListener('click', () => { nextRound(spot); spot.replaceChildren(); button.disabled = false; });
    ok.addEventListener('click', async () => {
      ok.disabled = true;
      try {
        await commit(p.fingerprint, again.checked ? list : null);
        spot.replaceChildren();
      } catch (error) {
        if (/HTTP 409\b/.test(String((error as Error)?.message ?? error))) {
          void withPreview(spot, button, previewPath, previewBody, confirmKey, commit, true);
          return;
        }
        say(actionMsg, errorText(lang, error), 'err');
        ok.disabled = false;
      }
    });
    box.append(el('div', { class: 'btns' }, ok, cancel));
    spot.replaceChildren(box);
  }
  async function showLinks(conversation: string, entity: string, load: number): Promise<void> {
    let entities: EntityRow[];
    try {
      entities = await deps.api<EntityRow[]>('GET', `/v1/conversations/${conversation}/entities`, undefined, 15_000);
    } catch {
      entities = []; // the page itself already reports a failing sidecar
    }
    if (load !== loads) return;
    const choices = linkChoices(entities, entity);
    if (!choices) {
      linkCard.style.display = 'none';
      return;
    }
    const { self, others } = choices;
    const msg = el('div', { class: 'msg' });
    const rows: HTMLElement[] = [];
    for (const link of self.links ?? []) {
      const undo = el('button', { text: L('link.remove') });
      const spot = el('div');
      const base = `/v1/conversations/${conversation}/entity-links/${link.id}`;
      undo.addEventListener('click', () => void withPreview(spot, undo, `${base}/remove/preview`, {}, 'pv.confirm_undo',
        async (expect, reextract) => {
          await deps.api('POST', `${base}/remove`, { expect }, 15_000);  // a 409 here re-previews the undo
          // The undo is made: from here on nothing may look like a stale undo (Copilot review of step 4).
          let failed: unknown = null;
          let queued = 0;
          if (reextract) {
            try {
              queued = (await deps.api<{ turns: number[] }>('POST', `${base}/reextract`, { turns: reextract }, 15_000))
                .turns.length;
            } catch (error) { failed = error; }
          }
          try {
            const now = await deps.api<EntityRow[]>('GET', `/v1/conversations/${conversation}/entities`, undefined, 15_000);
            const next = entityNamed(now, self.type, self.name);
            if (next && next.id !== entity) go(`/v1/inspector/c/${conversation}/e/${next.id}`);
            else await showInspector();
          } catch { /* the undo stands; the page reports a failing sidecar itself */ }
          if (failed && reextract) {
            say(actionMsg, L('pv.reextract_failed', { e: errorText(lang, failed) }), 'err');
            const retry = el('button', { class: 'mini', text: L('pv.retry') });
            retry.addEventListener('click', async () => {
              retry.disabled = true;
              try {
                const r = await deps.api<{ turns: number[] }>('POST', `${base}/reextract`, { turns: reextract }, 15_000);
                say(actionMsg, L('pv.reextracted', { n: r.turns.length }), 'ok');
              } catch (error) {
                say(actionMsg, L('pv.reextract_failed', { e: errorText(lang, error) }), 'err');
                actionMsg.append(' ', retry);
                retry.disabled = false;
              }
            });
            actionMsg.append(' ', retry);
          } else {
            say(actionMsg, reextract ? `${L('link.removed')} ${L('pv.reextracted', { n: queued })}` : L('link.removed'), 'ok');
          }
        }));
      rows.push(el('div', { class: 'btns' }, el('span', { text: `${link.name} = ${link.same_as}` }), undo), spot);
    }
    const card: (Node | string)[] = [el('h2', { text: L('link.title') }), el('p', { class: 'sub', text: L('link.sub') }), ...rows];
    const splits: HTMLElement[] = [];
    for (const alias of splitChoices(self)) {
      const split = el('button', { text: L('split.do') });
      const spot = el('div');
      const body = { kind: 'name_split', item: alias.name, other: alias.other, entity_type: self.type };
      split.addEventListener('click', () => void withPreview(spot, split, `/v1/conversations/${conversation}/repairs/preview`,
        body, 'pv.confirm_split', async (expect) => {
          await deps.api('POST', `/v1/conversations/${conversation}/repairs`, { ...body, expect }, 15_000);
          const now = await deps.api<EntityRow[]>('GET', `/v1/conversations/${conversation}/entities`, undefined, 15_000);
          const next = entityNamed(now, self.type, self.name);
          say(actionMsg, L('split.done', { a: alias.name, b: alias.other }), 'ok');
          if (next && next.id !== entity) go(`/v1/inspector/c/${conversation}/e/${next.id}`);
          else await showInspector();
        }));
      splits.push(el('div', { class: 'btns' }, el('span', { text: `${alias.name} ~ ${alias.other}` }), split), spot);
    }
    if (others.length) {
      const pick = el('select', { 'aria-label': L('link.pick') },
        ...others.map((e) => el('option', { value: e.name, text: `${e.name} (${e.mentions})` })));
      const join = el('button', { text: L('link.join') });
      const spot = el('div');
      const path = `/v1/conversations/${conversation}/entity-links`;
      join.addEventListener('click', () => {
        const body = { entity_type: self.type, name: self.name, same_as: pick.value };
        void withPreview(spot, join, `${path}/preview`, body, 'pv.confirm_join', async (expect) => {
          const r = await deps.api<{ entity: EntityRow | null }>('POST', path, { ...body, expect }, 15_000);
          say(actionMsg, L('link.done', { a: body.name, b: body.same_as }), 'ok');
          if (r.entity && r.entity.id !== entity) go(`/v1/inspector/c/${conversation}/e/${r.entity.id}`);
          else await showInspector();
        });
      });
      pick.addEventListener('change', () => { nextRound(spot); spot.replaceChildren(); join.disabled = false; });
      card.push(el('div', { class: 'row' }, field(L('link.pick'), pick), el('div', { class: 'btns' }, join)), spot);
    } else {
      card.push(el('div', { class: 'muted', text: L('link.none') }));
    }
    if (splits.length) card.push(el('h2', { text: L('split.title') }), el('p', { class: 'sub', text: L('split.sub') }), ...splits);
    linkCard.replaceChildren(...card, msg);
    linkCard.style.display = '';
  }
  inspectorBody.addEventListener('click', (event) => {
    const link = event.target instanceof Element ? event.target.closest('a') : null;
    if (!link) return;
    event.preventDefault();
    const href = link.getAttribute('href');
    const section = sectionTarget(href);
    const target = section ? inspectorBody.querySelector<HTMLElement>(`#${section}`) : null;
    if (target) {
      if (target instanceof HTMLDetailsElement) target.open = true;
      target.scrollIntoView({ block: 'start', behavior: 'smooth' });
      return;
    }
    const path = inspectorApiPath(href);
    if (path) go(path);
  });
  inspectorBack.addEventListener('click', () => {
    const at = visited.pop();
    if (at) void showInspector(at.path, at);
  });
  inspectorRefresh.addEventListener('click', () => void showInspector());
  // Destructive actions take two clicks: the first arms the button for 6 s.
  const confirmable: [HTMLButtonElement, StringKey, string][] = [
    [rebuildButton, 'act.rebuild', 'primary'], [deleteButton, 'act.delete', 'danger']];
  let armed: HTMLButtonElement | null = null;
  let armTimer = 0;
  function disarm(): void {
    window.clearTimeout(armTimer);
    armed = null;
    for (const [button, label] of confirmable) {
      button.textContent = L(label);
      button.className = '';
    }
  }
  function confirmed(button: HTMLButtonElement, confirm: StringKey, cls: string): boolean {
    if (armed === button) {
      disarm();
      return true;
    }
    disarm();
    armed = button;
    button.textContent = L(confirm);
    button.className = cls;
    armTimer = window.setTimeout(disarm, 6000);
    return false;
  }
  function actionError(error: unknown): string {
    return /HTTP 409/.test(error instanceof Error ? error.message : String(error)) ? L('act.off') : errorText(lang, error);
  }
  interface ActionResult { queued: { extract?: number; embed?: number }; discarded?: number }
  historyButton.addEventListener('click', async () => {
    const conversation = actionConversation;
    if (!conversation) return;
    disarm();
    historyButton.disabled = true;
    say(actionMsg, L('act.working'));
    try {
      const r = await deps.api<ActionResult>('POST', `/v1/conversations/${conversation}/extract-history`, {}, 30_000);
      const n = (r.queued.extract ?? 0) + (r.queued.embed ?? 0);
      say(actionMsg, n ? L('act.history_done', { t: r.queued.extract ?? 0, m: r.queued.embed ?? 0 }) : L('act.history_none'), 'ok');
      if (n) deps.hud.background(conversation);
      await showInspector();
    } catch (error) { say(actionMsg, actionError(error), 'err'); } finally { historyButton.disabled = false; }
  });
  rebuildButton.addEventListener('click', async () => {
    const conversation = actionConversation;
    // Two clicks: the chat's facts disappear until they are extracted again.
    if (!conversation || !confirmed(rebuildButton, 'act.rebuild_confirm', 'primary')) return;
    rebuildButton.disabled = true;
    say(actionMsg, L('act.working'));
    try {
      const r = await deps.api<ActionResult>('POST', `/v1/conversations/${conversation}/rebuild`, {}, 30_000);
      say(actionMsg, L('act.rebuild_done', { d: r.discarded ?? 0, t: r.queued.extract ?? 0 }), 'ok');
      deps.hud.background(conversation);
      await showInspector();
    } catch (error) { say(actionMsg, actionError(error), 'err'); } finally { rebuildButton.disabled = false; }
  });
  deleteButton.addEventListener('click', async () => {
    const conversation = actionConversation;
    // Two clicks: everything NMOS recorded for this chat is deleted and cannot be restored (ADR 0009).
    if (!conversation || !confirmed(deleteButton, 'act.delete_confirm', 'danger')) return;
    deleteButton.disabled = true;
    say(actionMsg, L('act.working'));
    try {
      const r = await deps.api<{ deleted: { messages?: number } }>('POST', `/v1/conversations/${conversation}/delete`, {}, 60_000);
      visited.length = 0; // the deleted conversation's pages are gone
      await showInspector('/v1/inspector');
      say(actionMsg, L('act.delete_done', { m: r.deleted.messages ?? 0 }), 'ok');
    } catch (error) { say(actionMsg, errorText(lang, error), 'err'); } finally { deleteButton.disabled = false; }
  });

  exportButton.addEventListener('click', async () => {
    const conversation = actionConversation;
    if (!conversation) return;
    await exportTo(exportButton, actionMsg, `/v1/archive?conversation=${conversation}`, 'chat');
  });
  /** Fetch an archive from the sidecar and save it (ADR 0050, H21), saying how it went under the button. */
  async function exportTo(button: HTMLButtonElement, msg: HTMLElement, path: string, kind: string): Promise<void> {
    button.disabled = true;
    say(msg, L('exp.working'));
    try {
      const size = await deps.download(path, archiveName(kind, new Date()));
      say(msg, L('exp.saved', { mb: (size / 1_048_576).toFixed(1) }), 'ok');
    } catch (error) {
      say(msg, errorText(lang, error), 'err');
    } finally {
      button.disabled = false;
    }
  }

  // --- settings tab: progress display (applied at once: it may ask PocketRisu for a permission) --
  const hudBox = el('input', { type: 'checkbox' });
  const hudMsg = el('div', { class: 'msg' });
  hudBox.addEventListener('change', async () => {
    hudBox.disabled = true;
    try {
      if (!hudBox.checked) {
        await deps.hud.disable();
        return say(hudMsg, L('hud.off'), 'muted');
      }
      const result = await deps.hud.enable();
      hudBox.checked = result === 'on';
      if (result === 'on') say(hudMsg, L('hud.on'), 'ok');
      else say(hudMsg, L(result === 'denied' ? 'hud.denied' : 'hud.unsupported'), 'warn');
    } catch (error) {
      say(hudMsg, errorText(lang, error), 'err');
    } finally {
      hudBox.disabled = false;
    }
  });
  settingsView.append(el('div', { class: 'card' },
    el('h2', { text: L('hud.title') }), el('p', { class: 'sub', text: L('hud.sub') }),
    el('div', { class: 'check' }, hudBox, el('span', { text: L('hud.toggle') })), hudMsg));

  // --- settings tab: fields ---------------------------------------------------------------------
  const url = el('input', { spellcheck: 'false' });
  const route = el('select', {}, ...['auto', 'direct', 'server'].map((v) => el('option', { value: v, text: v })));
  const enabled = el('input', { type: 'checkbox' });
  const reserved = el('input', { type: 'number', min: 100, max: PANEL_MAX_RESERVED_TOKENS });
  const deadline = el('input', { type: 'number', min: 200, max: MAX_DEADLINE_MS, step: 100 });
  settingsView.append(el('div', { class: 'card' },
    el('h2', { text: L('conn.title') }), el('p', { class: 'sub', text: L('conn.sub') }),
    field(L('conn.url'), url),
    el('div', { class: 'row' }, field(L('conn.route'), route), field(L('conn.budget'), reserved), field(L('conn.deadline'), deadline)),
    el('div', { class: 'check' }, enabled, el('span', { text: L('conn.enabled') })),
    el('p', { class: 'sub', text: L('conn.hint') }), el('p', { class: 'sub', text: L('conn.deadline_hint') })));

  function modelSection(kind: 'llm' | 'embeddings', title: StringKey, sub: StringKey, presets: Preset[]) {
    const preset = el('select', {}, ...presets.map((p, i) => el('option', { value: String(i),
      text: p.label.includes('.') ? L(p.label as StringKey) : p.label })));
    const endpoint = el('input', { placeholder: 'https://…/v1', spellcheck: 'false' });
    const model = el('input', { placeholder: L(kind === 'llm' ? 'model.llm_placeholder' : 'model.emb_placeholder'), spellcheck: 'false' });
    const list = el('select', { style: 'display:none' });
    const key = el('input', { type: 'password', placeholder: L('model.key_placeholder'), autocomplete: 'off' });
    const msg = el('div', { class: 'msg' });
    const load = el('button', { text: L('model.load') });
    const test = el('button', { text: L('model.test') });
    preset.addEventListener('change', () => {
      const p = presets[Number(preset.value)] as Preset;
      if (p.url !== 'custom') endpoint.value = fillProject(p.url, key.value);
      if (p.model) model.value = p.model;
      if (!p.url) model.value = '';
      say(msg, p.url.includes('{project}') ? L('model.vertex_hint') : '');
      update();
    });
    key.addEventListener('input', () => { endpoint.value = fillProject(endpoint.value, key.value); });
    list.addEventListener('change', () => { model.value = list.value; update(); });
    load.addEventListener('click', async () => {
      say(msg, L('model.loading'));
      try {
        const r = await deps.api<{ ok: boolean; models: string[]; error?: string }>('POST', '/v1/config/models',
          { kind, url: endpoint.value.trim(), api_key: key.value.trim() || undefined });
        if (!r.ok) return say(msg, L('model.list_failed', { e: r.error ?? '' }), 'err');
        list.replaceChildren(el('option', { value: '', text: L('model.pick', { n: r.models.length }) }),
          ...r.models.map((m) => el('option', { value: m, text: m })));
        list.style.display = '';
        say(msg, L('model.found', { n: r.models.length }), 'ok');
      } catch (error) { say(msg, errorText(lang, error), 'err'); }
    });
    test.addEventListener('click', async () => {
      test.disabled = true;
      say(msg, L('model.testing'));
      try {
        const r = await deps.api<{ ok: boolean; ms: number; dimensions?: number; error?: string }>('POST', '/v1/config/test',
          { kind, url: endpoint.value.trim(), model: model.value.trim(), api_key: key.value.trim() || undefined });
        say(msg, r.ok ? L('model.test_ok', { ms: r.ms }) + (r.dimensions ? L('model.dims', { n: r.dimensions }) : '')
          : L('model.test_failed', { e: r.error ?? '' }), r.ok ? 'ok' : 'err');
      } catch (error) { say(msg, errorText(lang, error), 'err'); } finally { test.disabled = false; }
    });
    settingsView.append(el('div', { class: 'card' },
      el('h2', { text: L(title) }), el('p', { class: 'sub', text: L(sub) }),
      field(L('model.provider'), preset), field(L('model.endpoint'), endpoint),
      field(L('model.model'), model), list, field(L('model.key'), key),
      el('div', { class: 'btns' }, load, test), msg));
    return {
      values: () => ({ url: endpoint.value, model: model.value, key: key.value }),
      fill(cfg: { url: string; model: string; api_key_set: boolean }) {
        preset.value = String(presetIndex(presets, cfg.url));
        endpoint.value = cfg.url;
        model.value = cfg.model;
        key.value = '';
        key.placeholder = L(cfg.api_key_set ? 'model.key_saved' : 'model.key_placeholder');
      },
    };
  }
  const llm = modelSection('llm', 'llm.title', 'llm.sub', LLM_PRESETS);
  const emb = modelSection('embeddings', 'emb.title', 'emb.sub', EMBED_PRESETS);

  const threshold = el('input', { type: 'number', step: 0.05, min: 0.05, max: 1 });
  const minSim = el('input', { type: 'number', step: 0.01, min: 0, max: 1 });
  const topK = el('input', { type: 'number', min: 0, max: 20 });
  const factsLimit = el('input', { type: 'number', min: 0, max: 30 });
  const backfill = el('input', { type: 'number', min: 0, max: 5000 });
  const summaries = el('input', { type: 'checkbox' });  // scene summaries and the story so far (ADR 0042, 0043)
  const canonFacts = el('input', { type: 'checkbox' });  // facts read from the canon (ADR 0047)
  settingsView.append(el('div', { class: 'card' },
    el('h2', { text: L('tune.title') }), el('p', { class: 'sub', text: L('tune.sub') }),
    el('div', { class: 'row' }, field(L('tune.threshold'), threshold), field(L('tune.min_sim'), minSim)),
    el('div', { class: 'row' }, field(L('tune.top_k'), topK), field(L('tune.facts'), factsLimit), field(L('tune.backfill'), backfill)),
    el('div', { class: 'check' }, summaries, el('span', { text: L('tune.summaries') })),
    el('p', { class: 'sub', text: L('tune.summaries_hint') }),
    el('div', { class: 'check' }, canonFacts, el('span', { text: L('tune.canon_facts') })),
    el('p', { class: 'sub', text: L('tune.canon_facts_hint') })));

  const rules = el('textarea', { spellcheck: 'false' });
  const example = el('button', { text: L('rules.example') });
  example.addEventListener('click', () => { rules.value = JSON.stringify(PARSER_EXAMPLE, null, 2); update(); });
  settingsView.append(el('div', { class: 'card' },
    el('h2', { text: L('rules.title') }), el('p', { class: 'sub', text: L('rules.sub') }),
    rules, el('div', { class: 'btns' }, example)));

  // --- settings tab: export (applied at once; ADR 0050) ------------------------------------------
  const exportEmbeddings = el('input', { type: 'checkbox' });
  const exportAll = el('button', { text: L('exp.all') });
  const exportMsg = el('div', { class: 'msg' });
  exportAll.addEventListener('click', () => void exportTo(exportAll, exportMsg,
    `/v1/archive${exportEmbeddings.checked ? '?embeddings=true' : ''}`, 'all'));
  settingsView.append(el('div', { class: 'card' },
    el('h2', { text: L('exp.title') }), el('p', { class: 'sub', text: L('exp.sub') }),
    el('div', { class: 'check' }, exportEmbeddings, el('span', { text: L('exp.embeddings') })),
    el('div', { class: 'btns' }, exportAll), exportMsg));

  // --- settings tab: one save bar ---------------------------------------------------------------
  const barText = el('span', { class: 'text muted' });
  const revert = el('button', { text: L('revert') });
  const save = el('button', { class: 'primary', text: L('save') });
  const bar = el('div', { class: 'bar' }, barText, revert, save);
  root.append(bar);

  function values(): FormValues {
    return {
      conn: { url: url.value, route: route.value, enabled: enabled.checked, reserved: reserved.value, deadline: deadline.value },
      llm: llm.values(), emb: emb.values(),
      tune: { threshold: threshold.value, minSim: minSim.value, topK: topK.value, facts: factsLimit.value, backfill: backfill.value,
        summaries: summaries.checked, canonFacts: canonFacts.checked },
      rules: rules.value,
    };
  }
  let baseline: FormValues = values();
  let closing = false;
  const dirty = () => dirtySections(baseline, values());

  function update(message?: { text: string; kind: 'ok' | 'err' | 'warn' | 'muted' }): void {
    const d = dirty();
    save.disabled = d.length === 0;
    revert.disabled = d.length === 0;
    if (message) say(barText, message.text, message.kind);
    else if (d.length) say(barText, L('unsaved', { s: d.map((s) => L(SECTION_TITLE[s])).join(', ') }), 'warn');
    else say(barText, '', 'muted');
  }
  settingsView.addEventListener('input', () => update());
  settingsView.addEventListener('change', () => update());

  async function loadConn(): Promise<void> {
    url.value = (await deps.getArg('sidecar_url')) || 'http://127.0.0.1:8790';
    route.value = (await deps.getArg('route')) || 'auto';
    enabled.checked = Number(await deps.getArg('disabled')) !== 1;
    reserved.value = String(Number(await deps.getArg('reserved_memory_tokens')) || DEFAULT_RESERVED_TOKENS);
    deadline.value = String(Number(await deps.getArg('deadline_ms')) || DEFAULT_DEADLINE_MS);
    hudBox.checked = Number(await deps.getArg('hud')) === 1;
  }

  function fillServer(cfg: ServerConfig): void {
    llm.fill(cfg.llm); emb.fill(cfg.embeddings);
    threshold.value = String(cfg.recall.threshold);
    minSim.value = String(cfg.recall.vector_min_sim);
    topK.value = String(cfg.recall.top_k);
    factsLimit.value = String(cfg.recall.facts_limit);
    backfill.value = String(cfg.extraction.backfill);
    summaries.checked = cfg.extraction.summaries !== false;
    canonFacts.checked = cfg.extraction.canon_facts !== false;
    rules.value = cfg.parsers.source === 'ui' ? JSON.stringify(cfg.parsers.rules, null, 2) : '';
    rules.placeholder = cfg.parsers.source === 'file' ? L('rules.from_file', { n: cfg.parsers.active_rules }) : L('rules.none');
  }

  async function loadAll(): Promise<void> {
    await loadConn();
    try { fillServer(await deps.api<ServerConfig>('GET', '/v1/config', undefined, 5000)); } catch { /* the status tab shows why */ }
    baseline = values();
    update();
  }

  async function saveAll(): Promise<boolean> {
    const d = dirty();
    if (!d.length) { update({ text: L('no_changes'), kind: 'muted' }); return true; }
    save.disabled = true;
    say(barText, L('saving'));
    const v = values();
    if (d.includes('conn')) {
      // First, so the server update below already goes to a changed sidecar address.
      const args = connArgs(v.conn);
      for (const [k, value] of Object.entries(args)) await deps.setArg(k, value);
      // Show what was stored: the budget is capped at PANEL_MAX_RESERVED_TOKENS, the deadline kept in range.
      reserved.value = String(args.reserved_memory_tokens);
      deadline.value = String(args.deadline_ms);
      baseline = { ...baseline, conn: values().conn };
    }
    const body = configBody(d, v);
    if (!Object.keys(body).length) { update({ text: L('saved'), kind: 'ok' }); return true; }
    try {
      const r = await deps.api<ServerConfig>('PUT', '/v1/config', body);
      fillServer(r);
      baseline = values();
      const parts = [r.queued_jobs ? L('saved_queued', { n: r.queued_jobs }) : L('saved')];
      if (r.queued_jobs) deps.hud.background();
      if (d.includes('rules') && r.parsers.active_rules) parts.push(L('saved_rules', { n: r.parsers.active_rules }));
      update({ text: parts.join(' '), kind: 'ok' });
      return true;
    } catch (error) {
      const text = errorText(lang, error);
      update({ text: d.includes('conn') ? L('conn_saved_server_failed', { e: text }) : text, kind: 'err' });
      return false;
    }
  }

  save.addEventListener('click', () => void saveAll());
  revert.addEventListener('click', () => void loadAll());

  // --- closing, language, tabs ------------------------------------------------------------------
  function shut(): void {
    root.remove();
    current = null;
    void deps.hide();
  }
  close.addEventListener('click', () => {
    if (!dirty().length || closing) return shut();
    closing = true;
    const saveClose = el('button', { class: 'primary', text: L('save_and_close') });
    const discard = el('button', { text: L('discard_and_close') });
    const cancel = el('button', { text: L('cancel') });
    const restore = () => { closing = false; bar.replaceChildren(barText, revert, save); update(); };
    saveClose.addEventListener('click', async () => { if (await saveAll()) shut(); else restore(); });
    discard.addEventListener('click', shut);
    cancel.addEventListener('click', restore);
    select('settings');
    bar.replaceChildren(el('span', { class: 'text warn', text: L('close_unsaved') }), cancel, discard, saveClose);
  });

  language.addEventListener('change', async () => {
    if (dirty().length) {
      language.value = lang;
      select('settings');
      update({ text: L('lang_unsaved'), kind: 'warn' });
      return;
    }
    const next = langOf(language.value);
    await deps.setArg('language', next);
    root.remove();
    current = await render(deps, next, shown);
  });

  function select(next: Tab): void {
    shown = next;
    const views: [Tab, HTMLElement, HTMLElement][] = [
      ['status', statusView, tabStatus], ['inspector', inspectorView, tabInspector], ['settings', settingsView, tabSettings]];
    for (const [name, view, button] of views) {
      view.style.display = name === next ? '' : 'none';
      button.className = name === next ? 'on' : '';
    }
    bar.style.display = next === 'settings' ? '' : 'none';
    root.classList.toggle('wide', next === 'inspector');
    if (next === 'status') void refreshStatus();
    if (next === 'inspector') void showInspector();
  }
  tabStatus.addEventListener('click', () => select('status'));
  tabInspector.addEventListener('click', () => select('inspector'));
  tabSettings.addEventListener('click', () => select('settings'));

  document.body.append(root);
  select(tab);
  await loadAll();
  return { root, select };
}
