// NMOS panel, rendered inside the plugin's own sandboxed iframe (full screen): status, inspector and
// settings tabs. Plugin-side settings are PocketRisu plugin args. The sidecar saves model/recall settings
// together; status rules have a separate explicit card-bound Apply (PHASE-39 amendment 2).

import type { StatusInfo } from './core';
import { budgetAdvice } from './budget';
import type { ChatSwitch } from './chatoff';
import { PLUGIN_BUILD } from './build';
import { deadlineAdvice, formatMs } from './deadline';
import { configBody, connArgs, DEFAULT_DEADLINE_MS, DEFAULT_EMBED_MAX_CHUNKS, DEFAULT_KEEP_RECENT_TURNS, DEFAULT_RESERVED_TOKENS,
  dirtySections, EMBED_CHUNK_CHARS, embedChunkChars, embedWaitTooLong, MAX_EMBED_MAX_CHUNKS, MIN_EMBED_MAX_CHUNKS,
  endpointForKey, fillProject, isVertexEndpoint, MAX_DEADLINE_MS, MAX_KEEP_RECENT_TURNS, MAX_RERANK_TIMEOUT_MS,
  MIN_KEEP_RECENT_TURNS, MIN_RERANK_TIMEOUT_MS, modelChange, OLLAMA_DOCKER, PANEL_MAX_RESERVED_TOKENS, presetMatches, presetUrl,
  serviceAccountProject, trimArgs, VERTEX_URL, type FormValues, type Section } from './form';
import { bodyOf, EFFORTS, effortOf, isOpenRouter, showBody, withEffort } from './extrabody';
import { failureKind } from './failure';
import { parserBindings, parserDraft, presetRules, type ParserPreset } from './parser-form';
import { langOf, STRING_KEYS, t, type Lang, type StringKey } from './i18n';
import { icon, type IconName } from './icons';
import { aliasPair, closeOutcomes, entityNamed, inspectorApiPath, inspectorConversation, inspectorEntity, linkChoices,
  bulkMark, localTime, markDetail, placeMarks, previewText, repairAction, safeFragment, sectionTarget, splitChoices } from './inspector';
import type { PanelTarget } from './hud';
import { copyText, loadNotePresets, PROMPT_MAX, saveNotePresets, splitNoteSections, type NotePreset } from './notes';
import { drawGraph, parseGraph } from './graph';
import type { BulkMark, BulkRequest, EntityRow, ExcludePreview, Preview, RepairAction } from './inspector';
import { alpha, PALETTE, paletteVars } from './palette';
import { routeFor } from './route';
import { coverageLine, trimStatusLine } from './trimtext';
import { workerLines, type WorkerStatus } from './workertext';
import {
  CARRY_MAX_NAMES, carryCountsLine, carryCutoffLabel, carryErrorText, carryRefusal, carrySourceLabel,
  isCarryConflict, isCarryNotFound, parseCutoffTurn,
  type CarryMode, type CarryPreview, type CarryRequestBody, type CarryState,
} from './carrytext';
import { uploadArchive, waitFor, type ArchiveSummary, type Method } from './restore';
import { chunkIds, formatOrphanDate, orphanLabel, selectionSummary,
  type BatchDeleteResult, type HostChatScan, type OrphanPreview, type OrphanRow } from './orphans';
import { usageText, type UsageTotal } from './usage';

export type Tab = 'status' | 'inspector' | 'settings';
type PrimaryTab = 'home' | 'memory' | 'notes' | 'settings';
type MemorySub = 'story' | 'explore' | 'attention' | 'map' | 'diag';

interface HubChatItem { id: string; name: string; character?: string; title?: string; turns?: number }
interface HubMeta {
  conv?: HubChatItem | null;
  working?: { state?: string; queued?: number; failed?: number } | null;
  attention?: number;
  chats?: HubChatItem[];
}

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
  api<T>(method: Method, path: string, body?: unknown, timeoutMs?: number): Promise<T>;
  status(): Promise<StatusInfo>;
  getArg(key: string): Promise<string>;
  setArg(key: string, value: string | number): Promise<void>;
  show(): Promise<void>;
  hide(): Promise<void>;
  hud: HudControl;
  /** NMOS off and on for the chat open now (ADR 0048). */
  chat: ChatSwitch;
  /** On-demand read of PocketRisu's active chat IDs for orphan cleanup (PHASE-68, H22). */
  scanHostChats?: () => Promise<HostChatScan>;
  /** Fetch a file from the sidecar and save it under `name` (an archive, ADR 0050); its size in bytes. */
  download(path: string, name: string): Promise<number>;
}

interface ServerConfig {
  /** `extra_body` and `no_temperature` from PHASE-61 on (ADR 0088). */
  llm: { url: string; model: string; api_key_set: boolean; json_mode: boolean; extra_body?: Record<string, unknown>;
    no_temperature?: boolean };
  /** `max_chunks` (ADR 0062) only from a sidecar that lets the panel change it. */
  embeddings: { url: string; model: string; api_key_set: boolean; query_instruction: string; max_chunks?: number };
  rerank?: { url: string; model: string; timeout_ms: number; format: string; key_set: boolean; configured: boolean;
    note?: string };
  recall: { threshold: number; vector_min_sim: number; embed_timeout_ms?: number; top_k: number; facts_limit: number;
    pin_at_mentions?: boolean };
  /** `on_output` (PHASE-67) only from a sidecar that has the switch. */
  extraction: { backfill: number; summaries?: boolean; canon_facts?: boolean; on_output?: boolean };
  parsers: { rules: unknown; source: string; active_rules: number; errors: string[];
    spec?: unknown; presets?: ParserPreset[] };
  queued_jobs?: number;
  install?: string | null;
}

/** An entities row with what pins add (ADR 0087): `pinned` is the pin's repair id, only on a pinned row; `excluded`
 *  marks a character the owner left out of memory, which is never pinned. */
type PinRow = EntityRow & { excluded?: boolean; pinned?: string };

/** `minSim`: the vector similarity bar measured for the preset's model (`docs/perf/embedders.md`); `hint`: said when
 *  the preset is picked. */
interface Preset { label: string | StringKey; url: string; model?: string; minSim?: number; hint?: StringKey }
/** `GET /v1/conversations/<id>/status/candidates` (PHASE-43 S2): status windows found by their shape in the chat. */
interface StatusCandidates {
  card: string | null;
  card_name?: string | null;
  candidates: { keys: string[]; count: number; values: Record<string, string>; tracked: boolean; rule_id: string | null }[];
  pins: string[];
}
/** `GET /v1/conversations/<id>/memory-mode` (ADR 0035). */
interface MemoryMode { strict: boolean; narrator: string | null; characters: string[] }

const LLM_PRESETS: Preset[] = [
  { label: 'preset.off', url: '' },
  { label: 'preset.ollama', url: OLLAMA_DOCKER },
  { label: 'OpenRouter', url: 'https://openrouter.ai/api/v1' },
  { label: 'OpenAI', url: 'https://api.openai.com/v1', model: 'gpt-4o-mini' },
  { label: 'Google Gemini', url: 'https://generativelanguage.googleapis.com/v1beta/openai', model: 'gemini-2.5-flash' },
  { label: 'Google Vertex AI', url: VERTEX_URL, model: 'google/gemini-3.8-flash' },  // checked on real Vertex (ADR 0022)
  { label: 'preset.custom', url: 'custom' },
];

const EMBED_PRESETS: Preset[] = [
  { label: 'preset.off', url: '' },
  { label: 'preset.ollama', url: OLLAMA_DOCKER, model: 'qwen3-embedding:0.6b', minSim: 0.42 },
  { label: 'OpenAI', url: 'https://api.openai.com/v1', model: 'text-embedding-3-small' },
  { label: 'Voyage AI', url: 'https://api.voyageai.com/v1', model: 'voyage-4-large', minSim: 0.3, hint: 'emb.voyage_hint' },
  { label: 'preset.custom', url: 'custom' },
];

const PARSER_EXAMPLE = {
  rules: [
    { id: 'roster', kind: 'block', role: 'char', start: '<status>', end: '</status>', entity_line: '\\[(?P<entity>[^\\]]+)\\]' },
    { id: 'hp', kind: 'regex', pattern: 'HP\\s*[:：]\\s*(?P<value>\\d+\\s*/\\s*\\d+)', key: 'HP' },
  ],
};

const SECTION_TITLE: Record<Section, StringKey> = {
  conn: 'conn.title', llm: 'llm.title', emb: 'emb.title', rerank: 'rerank.title', tune: 'tune.title', trim: 'trimset.title',
};

// Opaque on purpose: the host settings page behind the full-screen frame must not show through.
const CSS = `
html,body{margin:0;background:${PALETTE.bg}}
.nmos{${paletteVars()}}
.nmos{position:fixed;inset:0;overflow:auto;background:var(--c-bg);font:15px/1.6 system-ui,-apple-system,"Apple SD Gothic Neo","Malgun Gothic","Noto Sans KR",sans-serif;color:var(--c-text);-webkit-font-smoothing:antialiased}
.nmos *{box-sizing:border-box}
.nmos svg.ic{flex:none;display:inline-block;vertical-align:-2px}
.nmos .wrap{max-width:760px;margin:0 auto;padding:20px 16px 32px}
.nmos.shell-on .wrap{max-width:1120px;padding:18px 22px 48px}
.nmos header{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:8px}
.nmos h1{font-size:20px;font-weight:600;letter-spacing:-0.01em;margin:0;flex:1;white-space:nowrap;color:var(--c-text-strong)}
.nmos .tabs{display:flex;gap:6px;border-bottom:1px solid var(--c-line);margin:8px 0 8px}
.nmos .tabs button{background:none;border:0;border-bottom:2px solid transparent;border-radius:0;padding:9px 14px;color:var(--c-text-muted);font-size:15px;font-weight:500;transition:all .15s ease}
.nmos .tabs button:hover:not(:disabled){background:none;border-bottom-color:transparent;color:var(--c-text)}
.nmos .tabs button.on,.nmos .tabs button.on:hover:not(:disabled){color:var(--c-text-strong);border-bottom-color:var(--c-accent)}
.nmos .card{background:var(--c-surface);border:1px solid var(--c-line);border-radius:12px;padding:18px 20px;margin:14px 0}
.nmos h2{font-size:16.5px;font-weight:650;letter-spacing:-0.01em;color:var(--c-text-strong);margin:0 0 4px}
.nmos .sub{color:var(--c-text-muted);font-size:13.5px;line-height:1.55;margin:0 0 12px}
.nmos label{display:block;font-size:13px;font-weight:500;color:var(--c-text-muted);margin:12px 0 5px;letter-spacing:0.01em}
.nmos input,.nmos select,.nmos textarea{width:100%;background:var(--c-sunken);color:var(--c-text);border:1px solid var(--c-line-strong);border-radius:8px;padding:9px 12px;font:inherit;font-size:15px;transition:border-color .15s ease,box-shadow .15s ease}
.nmos input:focus,.nmos select:focus,.nmos textarea:focus{border-color:${alpha('accent', 0.7)};outline:none;box-shadow:0 0 0 3px ${alpha('accent', 0.22)}}
.nmos header select,.nmos .nmos-top-right select{width:auto;padding:5px 9px;font-size:13px;border-radius:8px}
.nmos textarea{min-height:150px;font-family:ui-monospace,monospace;font-size:13.5px;line-height:1.6}
.nmos .row{display:flex;gap:12px;flex-wrap:wrap}.nmos .row>*{flex:1;min-width:140px}
.nmos .btns{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px;align-items:center}
.nmos button{background:var(--c-raised);color:var(--c-text);border:1px solid var(--c-line-strong);border-radius:8px;padding:8px 14px;font:inherit;font-size:14px;font-weight:500;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;gap:6px;transition:background .15s ease,border-color .15s ease,color .15s ease}
.nmos button:hover:not(:disabled){background:var(--c-raised-hover);color:var(--c-text-strong);border-color:var(--c-line-hover)}
.nmos button:focus-visible{outline:2px solid ${alpha('accent', 0.65)};outline-offset:1px}
.nmos button.primary{background:var(--c-accent);border-color:var(--c-accent);color:#fff}
.nmos button.primary:hover:not(:disabled){background:var(--c-accent-hover);border-color:var(--c-accent-hover)}
.nmos button.danger{background:${alpha('err', 0.14)};border-color:${alpha('err', 0.42)};color:var(--c-err)}
.nmos button.danger:hover:not(:disabled){background:${alpha('err', 0.24)};border-color:${alpha('err', 0.6)};color:var(--c-text-strong)}
.nmos button.ghost{background:transparent;border-color:transparent;color:var(--c-text-muted)}
.nmos button.ghost:hover:not(:disabled){background:var(--c-raised);color:var(--c-text-strong);border-color:var(--c-line)}
.nmos button:disabled{opacity:.42;cursor:default}
.nmos .msg{margin-top:10px;font-size:13.5px;white-space:pre-wrap}.nmos .msg:empty{display:none}
.nmos .ok{color:var(--c-ok)}.nmos .err{color:var(--c-err)}.nmos .warn{color:var(--c-warn)}.nmos .muted{color:var(--c-text-muted)}
.nmos .check{display:flex;align-items:center;gap:8px;margin-top:10px;font-size:14px;color:var(--c-text-soft)}.nmos .check input{width:auto}
.nmos .preview{margin:8px 0;padding:10px 12px;border-left:3px solid var(--c-accent);background:var(--c-sunken);border-radius:0 8px 8px 0;font-size:13.5px;line-height:1.6}.nmos .preview>b{display:block;margin-bottom:4px;color:var(--c-text-strong)}
.nmos .line{display:flex;align-items:center;gap:8px;margin:5px 0}
.nmos .dot{flex:none;width:8px;height:8px;border-radius:50%;background:var(--c-text-ghost)}
.nmos .dot.ok{background:var(--c-ok);box-shadow:0 0 0 3px ${alpha('ok', 0.18)}}
.nmos .dot.err{background:var(--c-err);box-shadow:0 0 0 3px ${alpha('err', 0.18)}}
.nmos .dot.warn{background:var(--c-warn);box-shadow:0 0 0 3px ${alpha('warn', 0.18)}}
.nmos .pills{display:flex;gap:8px;flex-wrap:wrap}
.nmos .pill{border:1px solid var(--c-line-strong);border-radius:999px;padding:3px 10px;font-size:12.5px;color:var(--c-text-muted);background:var(--c-sunken)}
.nmos .pill.on{border-color:${alpha('ok', 0.4)};background:${alpha('ok', 0.1)};color:var(--c-ok)}
.nmos .badge{display:inline-flex;align-items:center;gap:4px;padding:2px 8px;border-radius:999px;font-size:11.5px;font-weight:600;border:1px solid var(--c-line-strong);background:var(--c-raised);color:var(--c-text-soft);white-space:nowrap}
.nmos .badge.b-llm{background:${alpha('violet', 0.14)};border-color:${alpha('violet', 0.36)};color:var(--c-violet)}
.nmos .badge.b-free{background:${alpha('ok', 0.12)};border-color:${alpha('ok', 0.34)};color:var(--c-ok)}
.nmos .badge.b-warn{background:${alpha('warn', 0.14)};border-color:${alpha('warn', 0.38)};color:var(--c-warn)}
.nmos .badge.b-danger{background:${alpha('err', 0.14)};border-color:${alpha('err', 0.4)};color:var(--c-err)}
.nmos .badge.b-info{background:${alpha('cyan', 0.12)};border-color:${alpha('cyan', 0.34)};color:var(--c-cyan)}
.nmos .mono{font-family:ui-monospace,monospace;font-size:12.5px;word-break:break-all}
.nmos.wide>.wrap{max-width:1120px}

/* PHASE-59: persistent top chrome + chat switcher + mobile bottom nav */
.nmos .nmos-topbar{position:sticky;top:0;z-index:30;background:${alpha('bg', 0.9)};backdrop-filter:blur(16px);border-bottom:1px solid var(--c-line)}
.nmos .nmos-topbar-in{max-width:1120px;margin:0 auto;padding:10px 22px;display:flex;align-items:center;gap:12px}
.nmos .nmos-brand{background:none;border:0;padding:4px 6px 4px 2px;border-radius:9px;display:inline-flex;align-items:center;gap:8px;color:var(--c-text-strong);font-size:16px;font-weight:750;letter-spacing:-0.02em}
.nmos .nmos-brand:hover:not(:disabled){background:var(--c-raised);border-color:transparent}
.nmos .nmos-logo{width:28px;height:28px;border-radius:7px;display:inline-flex;align-items:center;justify-content:center;background:var(--c-raised);border:1px solid var(--c-line-strong);color:var(--c-text-strong)}
.nmos .chat-picker{position:relative;flex:0 1 240px;min-width:120px}
.nmos .chat-btn{width:100%;justify-content:space-between;padding:6px 10px;border-radius:9px;background:var(--c-surface);border-color:var(--c-line-strong);color:var(--c-text-strong);font-size:13.5px}
.nmos .chat-btn .chat-lbl{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;text-align:left}
.nmos .chat-pop{position:absolute;top:calc(100% + 6px);left:0;width:300px;max-width:calc(100vw - 24px);background:var(--c-surface);border:1px solid var(--c-line-strong);border-radius:12px;padding:10px;box-shadow:0 16px 40px rgba(0,0,0,0.52);z-index:40}
.nmos .chat-pop input{padding:7px 10px;font-size:13.5px;margin-bottom:8px}
.nmos .chat-list{max-height:260px;overflow:auto;display:flex;flex-direction:column;gap:3px}
.nmos .chat-opt{width:100%;justify-content:space-between;text-align:left;padding:8px 10px;border-radius:8px;background:transparent;border-color:transparent;font-size:13.5px;color:var(--c-text)}
.nmos .chat-opt:hover:not(:disabled){background:var(--c-raised);border-color:var(--c-line)}
.nmos .chat-opt.on{background:${alpha('accent', 0.16)};border-color:${alpha('accent', 0.38)};color:var(--c-text-strong)}
.nmos .chat-opt .chat-meta{font-size:11.5px;color:var(--c-text-muted);flex:none}
.nmos .chat-pop-foot{margin-top:8px;padding-top:8px;border-top:1px solid var(--c-line);display:flex;justify-content:flex-end}
.nmos .nmos-nav{display:flex;align-items:center;gap:4px;padding:3px;background:var(--c-sunken);border:1px solid var(--c-line);border-radius:11px;margin:0 auto}
.nmos .nmos-nav button{background:transparent;border:1px solid transparent;border-radius:8px;padding:6px 12px;font-size:13.5px;font-weight:550;color:var(--c-text-muted)}
.nmos .nmos-nav button:hover:not(:disabled){color:var(--c-text-strong);background:var(--c-raised);border-color:transparent}
.nmos .nmos-nav button.on{background:var(--c-raised-hover);color:var(--c-text-strong);border-color:var(--c-line-strong);box-shadow:0 1px 4px rgba(0,0,0,0.28)}
.nmos .nav-badge{display:inline-flex;align-items:center;justify-content:center;min-width:18px;height:18px;padding:0 5px;border-radius:999px;background:var(--c-warn);color:#120d02;font-size:11px;font-weight:750;line-height:1}
.nmos .nmos-top-right{display:flex;align-items:center;gap:8px;margin-left:auto}
.nmos .status-pill{display:inline-flex;align-items:center;gap:6px;padding:5px 10px;border-radius:999px;background:var(--c-surface);border:1px solid var(--c-line);font-size:12.5px;font-weight:550;color:var(--c-text-soft);white-space:nowrap}
.nmos .status-pill.ok{border-color:${alpha('ok', 0.35)};background:${alpha('ok', 0.08)};color:var(--c-ok)}
.nmos .status-pill.warn{border-color:${alpha('warn', 0.4)};background:${alpha('warn', 0.1)};color:var(--c-warn)}
.nmos .status-pill.err{border-color:${alpha('err', 0.4)};background:${alpha('err', 0.1)};color:var(--c-err)}
.nmos .nmos-close{padding:6px 9px;border-radius:8px}
.nmos .nmos-bottomnav{display:none}

/* PHASE-59: Home inline quick bar + advisories */
.nmos .home-quick{display:flex;flex-direction:column;gap:10px;margin:0 0 14px}
.nmos .chat-strip{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;padding:12px 16px;border-radius:12px;background:var(--c-surface);border:1px solid var(--c-line)}
.nmos .chat-strip.off{border-color:${alpha('warn', 0.38)};background:linear-gradient(90deg,${alpha('warn', 0.1)},var(--c-surface) 55%)}
.nmos .chat-strip-info{display:flex;align-items:center;gap:10px;min-width:0;flex:1}
.nmos .chat-strip-title{font-size:14.5px;font-weight:600;color:var(--c-text-strong)}
.nmos .chat-strip-sub{font-size:12.5px;color:var(--c-text-muted)}
.nmos .adv-card{padding:12px 16px;border-radius:12px;background:var(--c-surface);border:1px solid ${alpha('warn', 0.4)};display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
.nmos .adv-card.err{border-color:${alpha('err', 0.45)};background:${alpha('err', 0.08)}}
.nmos .adv-card p{margin:3px 0 0;font-size:13px;color:var(--c-text-muted)}

/* PHASE-59: Memory workspace sub-tab bar */
.nmos .mem-subbar{margin:0 0 14px;padding:12px 14px;border-radius:12px;background:var(--c-surface);border:1px solid var(--c-line)}
.nmos .mem-subtabs{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.nmos .mem-subtabs button{background:transparent;border:1px solid transparent;border-radius:8px;padding:6px 12px;font-size:13.5px;color:var(--c-text-muted)}
.nmos .mem-subtabs button:hover:not(:disabled){background:var(--c-raised);color:var(--c-text-strong)}
.nmos .mem-subtabs button.on{background:${alpha('accent', 0.16)};border-color:${alpha('accent', 0.4)};color:var(--c-text-strong)}
.nmos .mem-subhead{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;margin-top:8px;padding-top:8px;border-top:1px solid var(--c-line)}
.nmos .mem-subtext{margin:0;font-size:13px;color:var(--c-text-muted)}
.nmos .diag-toggle{display:inline-flex;gap:3px;padding:2px;background:var(--c-sunken);border:1px solid var(--c-line);border-radius:8px}
.nmos .diag-toggle button{padding:4px 10px;font-size:12.5px;border-radius:6px;background:transparent;border:0;color:var(--c-text-muted)}
.nmos .diag-toggle button.on{background:var(--c-raised-hover);color:var(--c-text-strong)}

/* PHASE-59: Dedicated Author's Note Studio */
.nmos .studio-head{margin-bottom:14px}
.nmos .notes-studio{display:grid;grid-template-columns:minmax(310px,420px) minmax(0,1fr);gap:18px;align-items:start}
.nmos .studio-col{background:var(--c-surface);border:1px solid var(--c-line);border-radius:14px;padding:18px 20px}
.nmos .studio-col h3{margin:0 0 12px;font-size:14px;font-weight:650;color:var(--c-text-soft);letter-spacing:0.01em}
.nmos .note-opt{display:flex;align-items:flex-start;gap:10px;padding:11px 12px;margin:0 0 8px;border-radius:10px;background:var(--c-sunken);border:1px solid var(--c-line);cursor:pointer;transition:border-color .15s ease,background .15s ease}
.nmos .note-opt:hover{border-color:var(--c-line-hover)}
.nmos .note-opt.on{background:${alpha('accent', 0.08)};border-color:${alpha('accent', 0.45)}}
.nmos .note-opt input[type=checkbox]{width:auto;margin-top:3px;flex:none}
.nmos .note-opt-body{flex:1;min-width:0}
.nmos .note-opt-top{display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap}
.nmos .note-opt-title{font-size:14px;font-weight:600;color:var(--c-text-strong)}
.nmos .note-opt-desc{font-size:12.5px;color:var(--c-text-muted);margin-top:3px;line-height:1.45}
.nmos .notes-est{margin:12px 0 0;padding:8px 12px;border-radius:8px;background:var(--c-sunken);border:1px solid var(--c-line);font-size:12.5px;color:var(--c-text-soft);display:flex;align-items:center;gap:6px}
.nmos .studio-empty{padding:42px 20px;text-align:center;color:var(--c-text-muted);font-size:14px;border:1px dashed var(--c-line-strong);border-radius:10px;background:var(--c-sunken)}

/* PHASE-59: 2-column Settings + Chat Maintenance rows */
.nmos .settings-shell{display:grid;grid-template-columns:236px minmax(0,1fr);gap:20px;align-items:start}
.nmos .settings-shell .groups{position:sticky;top:72px;display:flex;flex-direction:column;gap:4px;margin:0;padding:10px;background:var(--c-surface);border:1px solid var(--c-line);border-radius:14px}
.nmos .grp-label{font-size:11.5px;font-weight:650;letter-spacing:.04em;color:var(--c-text-faint);padding:8px 10px 4px;text-transform:uppercase}
.nmos .grp-label:first-child{padding-top:2px}
.nmos .settings-shell .groups button.group{display:flex;flex-direction:row;align-items:center;justify-content:flex-start;gap:10px;text-align:left;padding:9px 11px;border-radius:9px;background:transparent;border:1px solid transparent;font-size:14px;color:var(--c-text-soft)}
.nmos .settings-shell .groups button.group:hover:not(:disabled){background:var(--c-raised);color:var(--c-text-strong);border-color:transparent}
.nmos .settings-shell .groups button.group.on{background:${alpha('accent', 0.16)};border-color:${alpha('accent', 0.42)};color:var(--c-text-strong)}
.nmos .settings-shell .groups button.group .grp-txt{display:flex;flex-direction:column;min-width:0}
.nmos .settings-shell .groups button.group .sub{font-size:11.5px;margin:1px 0 0;color:var(--c-text-muted);display:none}
.nmos .settings-pane{min-width:0}
.nmos .settings-pane>.card:first-child,.nmos .settings-pane>[data-group]>.card:first-child{margin-top:0}
.nmos .maint-list{display:flex;flex-direction:column;gap:8px;margin-top:10px}
.nmos .maint-row{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;padding:12px 14px;border-radius:10px;background:var(--c-sunken);border:1px solid var(--c-line)}
.nmos .maint-row.danger-row{border-color:${alpha('err', 0.3)}}
.nmos .maint-info{flex:1;min-width:200px}
.nmos .maint-title{display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:14px;font-weight:600;color:var(--c-text-strong)}
.nmos .maint-desc{font-size:12.5px;color:var(--c-text-muted);margin-top:3px}

/* Inspector & Timeline (kept intact, refined surfaces) */
.nmos .insp{margin-top:8px}.nmos .insp+.sub{margin-top:18px}
.nmos .insp h1{font-size:16px;font-weight:600;margin:4px 0;color:var(--c-text-strong)}
.nmos .insp h2{margin:22px 0 8px;font-size:13.5px;font-weight:600;color:var(--c-text-strong)}
.nmos .insp .top{display:flex;justify-content:space-between;align-items:baseline;gap:12px}.nmos .insp .top p{margin:0}
.nmos .insp a{color:var(--c-link);text-decoration:none;cursor:pointer}
.nmos .insp a:hover{text-decoration:underline}
.nmos .insp .tl{margin:6px 0 16px}.nmos .insp .tl .tl-h{font-size:13px;font-weight:500;letter-spacing:.04em;color:var(--c-text-muted);margin:16px 0 4px;cursor:pointer;list-style:none}
.nmos .insp .tl .tl-h::-webkit-details-marker{display:none}.nmos .insp .tl .tl-h::before{content:"\\25BE  "}.nmos .insp .tl details:not([open])>.tl-h::before{content:"\\25B8  "}
.nmos .insp .tl-switch{font-size:14px;margin:0 0 8px}.nmos .insp .tl-span{color:var(--c-link);cursor:pointer}
.nmos .insp .tl-hint{font-size:13px;color:var(--c-text-faint);margin:0 0 8px}
.nmos .insp .tl-row{display:grid;grid-template-columns:112px minmax(0,1fr);gap:8px;align-items:center;padding:3px 0;color:inherit}.nmos .insp a.tl-line{text-decoration:none;border-radius:6px}
.nmos .insp .tl-cast .tl-row{display:block}
.nmos .insp .tl-lab{display:block;font-size:14px;line-height:1.3;color:var(--c-text);overflow:hidden;text-overflow:ellipsis;max-height:2.6em}
.nmos .insp .tl-cast .tl-lab{white-space:nowrap;margin-bottom:2px}
.nmos .insp .tl-lab .tl-k{display:block;font-size:13px;color:var(--c-text-muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.nmos .insp .tl-lab .tl-val{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.nmos .insp .tl-lab .tl-val.canon{color:var(--c-text-muted)}
.nmos .insp .tl-last{color:var(--c-text-faint);font-size:13px}.nmos .insp .tl-end{display:none}
.nmos .insp .tl-me{font-size:13px;color:var(--c-link);margin-left:6px}
.nmos .insp .tl-track{display:block;position:relative;height:26px}
.nmos .insp .tl-rule{position:absolute;left:0;right:0;top:13px;height:1px;background:var(--c-line)}
.nmos .insp .tl-bar{position:absolute;top:5px;height:16px;min-width:6px;border-radius:4px;overflow:hidden;box-sizing:border-box;background:var(--c-raised);border:1px solid var(--c-text-faint);cursor:pointer}
.nmos .insp .tl-bar.short{z-index:2}
.nmos .insp .tl-bar.past{background:transparent;border-color:var(--c-line-hover)}.nmos .insp .tl-bar.neg{border-style:dotted}
.nmos .insp .tl-bar.open{border-right-style:dashed}.nmos .insp .tl-bar.canon{border-left:2px dotted var(--c-text-muted)}
.nmos .insp .tl-bar.owner{border-color:var(--c-warn)}
.nmos .insp .tl .sel{background:var(--c-accent);border-color:var(--c-accent);color:#fff}
.nmos .insp .tl-dot{position:absolute;top:2px;bottom:2px;width:10px;margin-left:-5px;cursor:pointer}
.nmos .insp .tl-dot::after{content:"";position:absolute;left:4px;bottom:2px;width:2px;height:10px;border-radius:1px;background:var(--c-text-muted)}
.nmos .insp .tl-dot.s-major::after{height:18px;background:var(--c-text-strong)}.nmos .insp .tl-dot.s-minor::after{height:6px}
.nmos .insp .tl-dot.n1{transform:translateX(4px)}.nmos .insp .tl-dot.n2{transform:translateX(8px)}.nmos .insp .tl-dot.n3{transform:translateX(12px)}
.nmos .insp .tl .tl-dot.sel{background:transparent}.nmos .insp .tl .tl-dot.sel::after{background:var(--c-accent)}
.nmos .insp .tl-tick{position:absolute;top:5px;width:2px;height:16px;margin-left:-1px;border-radius:1px;background:var(--c-text-soft)}
.nmos .insp .tl-axis .tl-track{height:18px}
.nmos .insp .tl-axis .tl-track span{position:absolute;top:0;font-size:13px;color:var(--c-text-faint);transform:translateX(-50%);white-space:nowrap}
.nmos .insp .tl-axis .tl-track span.first{transform:none}.nmos .insp .tl-axis .tl-track span.last{transform:translateX(-100%)}
.nmos .insp .tl-axis .tl-track span.odd,.nmos .insp .tl-axis .tl-track span.near{display:none}
.nmos .insp .tl-card{margin:6px 0 10px;padding:10px 12px;border-radius:8px;background:var(--c-raised);font-size:14px}
.nmos .insp .tl-card p{margin:2px 0}.nmos .insp .tl-card .v{font-size:17px;font-weight:600;line-height:1.35;color:var(--c-text-strong);overflow-wrap:anywhere}
.nmos .insp .tl-hist{margin-top:8px;color:var(--c-text-muted)}.nmos .insp .tl-hist .cur{color:var(--c-text-strong)}
.nmos .insp .tl-more{font-size:13px;color:var(--c-text-faint);margin:2px 0}
.nmos .insp .tl-fold>summary,.nmos .insp .tl-others>summary{font-size:13px;color:var(--c-text-muted);margin:8px 0 2px;cursor:pointer}
.nmos .insp .ref{display:block;font-family:ui-monospace,monospace;font-size:12.5px;color:var(--c-text-faint)}
.nmos .insp .wrap{max-width:none;margin:0;padding:0;overflow-x:auto}
.nmos .insp table{width:100%;border-collapse:collapse;font-size:14px}
.nmos .insp th,.nmos .insp td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--c-line);vertical-align:top}
.nmos .insp th{font-weight:500;color:var(--c-text-faint);font-size:13px;letter-spacing:0.02em;white-space:nowrap}
.nmos .insp tr:hover td{background:rgba(255,255,255,0.02)}
.nmos .insp .chip{display:inline-block;padding:1px 7px;border-radius:999px;background:var(--c-raised);border:1px solid var(--c-line);font-size:12.5px;color:var(--c-text-soft)}
.nmos .insp span.rp{display:inline-flex;flex-wrap:wrap;align-items:center;gap:5px;margin-left:6px;vertical-align:middle}
.nmos .insp span.rp input,.nmos .insp span.rp select{width:auto;padding:3px 7px;font-size:13px;border-radius:6px}
.nmos .insp span.rp input[type=text]{width:12em}.nmos .insp span.rp input.turn{width:7em}
.nmos button.mini{padding:4px 9px;font-size:12.5px;border-radius:6px}
.nmos .groups{display:flex;flex-direction:column;gap:8px;margin:8px 0}
.nmos .groups button.group{display:flex;flex-direction:column;align-items:flex-start;gap:2px;text-align:left;padding:14px 16px;border-radius:12px;font-size:16px}
.nmos .groups button.group .sub{margin:0}
.nmos .inspbar{position:sticky;top:0;z-index:5;background:var(--c-bg);padding:8px 0;margin-top:0}
.nmos.shell-on .inspbar{position:static;background:transparent;padding:0 0 10px}
.nmos .help{margin:8px 0 0}.nmos .help summary{cursor:pointer;color:var(--c-text-muted)}.nmos .help p{margin:6px 0 0}
.nmos .packet{margin:8px 0 0;max-height:420px;overflow:auto;background:var(--c-sunken);border:1px solid var(--c-line);border-radius:8px;padding:12px;font-family:ui-monospace,monospace;font-size:13px;line-height:1.6;color:var(--c-text-soft);white-space:pre-wrap;word-break:break-word}
.nmos .insp.busy{opacity:.5;transition:opacity .15s}
.nmos .insp details>summary{cursor:pointer;list-style:none}.nmos .insp details>summary::-webkit-details-marker{display:none}
.nmos .insp details>summary h2{display:inline-block}
.nmos .insp details>summary h2::before{content:"▸ ";color:var(--c-text-ghost)}.nmos .insp details[open]>summary h2::before{content:"▾ "}
.nmos .insp .n{color:var(--c-text-muted);font-weight:400;font-size:13px}
.nmos .insp .toc{font-size:14px;line-height:1.9;margin:8px 0}.nmos .insp a.warn{color:var(--c-warn)}
.nmos .insp .who{display:flex;align-items:center;gap:8px;margin:10px 0}.nmos .insp .who select{width:auto;min-width:180px;padding:5px 8px}
.nmos .insp details.meta{font-size:13px;margin-top:2px;color:var(--c-text-muted)}.nmos .insp details.meta p{margin:4px 0}
.nmos .bulk-card{padding:10px 14px;border-radius:10px;background:var(--c-surface);border:1px solid var(--c-line);margin:0 0 12px}
.nmos .bulk-card .btns{margin-top:0}.nmos .bulk-card .btns+.btns{margin-top:8px}
.nmos .bar{position:sticky;bottom:0;background:${alpha('surface', 0.96)};backdrop-filter:blur(12px);border-top:1px solid var(--c-line-strong);padding:12px max(16px,calc((100% - 760px) / 2 + 16px));display:flex;align-items:center;gap:10px;flex-wrap:wrap;z-index:20}
.nmos.shell-on .bar{padding:12px max(22px,calc((100% - 1120px) / 2 + 22px))}
.nmos .bar .text{flex:1;min-width:160px;font-size:14px}
.nmos .bar .model-change{flex:1;display:flex;flex-direction:column;gap:2px;font-size:14px}.nmos .bar .model-change p{margin:0}
.nmos .bar .model-change .btns{justify-content:flex-end;margin-top:8px}
.nmos .bar.modal-open{position:fixed;inset:0;bottom:0;z-index:60;background:rgba(8,10,14,0.72);backdrop-filter:blur(4px);display:flex;align-items:center;justify-content:center;padding:16px;border:0}
.nmos .bar.modal-open .model-change{flex:0 1 460px;width:100%;max-width:460px;background:var(--c-surface);border:1px solid var(--c-line-strong);border-radius:14px;padding:18px 20px;box-shadow:0 22px 60px rgba(0,0,0,0.65);gap:8px}
.nmos .bar.modal-open .model-change label.check{margin:0;padding:9px 11px;border-radius:9px;background:var(--c-sunken);border:1px solid var(--c-line);cursor:pointer}
.nmos .status-pill{cursor:pointer}
.nmos .status-pill:hover{border-color:var(--c-line-hover)}
.nmos .dirty-dot{display:inline-block;width:7px;height:7px;border-radius:50%;background:var(--c-warn);margin-left:auto;flex:none}
.nmos .other-chat-banner{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;padding:12px 15px;border-radius:12px;border:1px solid ${alpha('cyan', 0.4)};background:linear-gradient(90deg,${alpha('cyan', 0.12)},var(--c-surface) 60%);margin-bottom:10px}
.nmos .worker-home{padding:14px 16px;border-radius:12px;background:var(--c-surface);border:1px solid var(--c-line-strong)}
.nmos .worker-home.trouble{border-color:${alpha('warn', 0.48)};background:linear-gradient(135deg,${alpha('warn', 0.08)},var(--c-surface) 58%)}
.nmos .worker-home-head{display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap;margin-bottom:8px}
.nmos .worker-home-title{display:inline-flex;align-items:center;gap:8px;font-weight:650;font-size:14.5px;color:var(--c-text-strong)}
.nmos .worker-home-lines{display:flex;flex-direction:column;gap:4px;font-size:13px}
.nmos .onboard-card{padding:16px 18px;border-radius:13px;background:var(--c-surface);border:1px solid ${alpha('accent', 0.36)}}
.nmos .onboard-step{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;padding:10px 12px;border-radius:10px;background:var(--c-sunken);border:1px solid var(--c-line);margin-top:8px}
.nmos .doc-search-bar{margin:0 0 12px}
.nmos .doc-search-bar input{width:100%}
.nmos .filter-chips{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 10px}
.nmos .filter-chip{padding:4px 10px;border-radius:999px;font-size:12px;background:var(--c-sunken);border:1px solid var(--c-line);color:var(--c-text-soft)}
.nmos .filter-chip.on{background:${alpha('accent', 0.18)};border-color:${alpha('accent', 0.48)};color:var(--c-text-strong)}
.nmos .insp tr.call-fail td{background:${alpha('err', 0.06)}}
.nmos .g-toolbar{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-bottom:8px}
.nmos .g-toolbar .g-search{flex:1 1 160px;min-width:140px;padding:6px 10px;font-size:13px}
.nmos .g-chips{display:flex;flex-wrap:wrap;gap:5px}
.nmos .g-chip{padding:4px 9px;border-radius:999px;font-size:12px;background:var(--c-sunken);border:1px solid var(--c-line);color:var(--c-text-soft)}
.nmos .g-chip.on{background:${alpha('accent', 0.18)};border-color:${alpha('accent', 0.48)};color:var(--c-text-strong)}
.nmos .g-stage{position:relative}
.nmos .g-zoom{position:absolute;right:10px;bottom:10px;display:flex;gap:4px}
.nmos svg.g-panel .g-node.dim{opacity:.18}
.nmos .g-drawer{margin-top:10px;padding:12px 14px;border-radius:11px;background:var(--c-raised);border:1px solid ${alpha('accent', 0.36)}}
.nmos .g-drawer-head{display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap;margin-bottom:8px}
.nmos .g-drawer-head b{color:var(--c-text-strong);font-size:14.5px}
.nmos .g-drawer-acts{display:flex;gap:6px;flex-wrap:wrap}
.nmos .g-drawer-list{display:flex;flex-direction:column;gap:4px}
.nmos .g-drawer-row{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:4px 6px;border-radius:6px;font-size:13px;color:var(--c-text-soft)}
.nmos .g-drawer-row.clickable{cursor:pointer}
.nmos .g-drawer-row.clickable:hover{background:var(--c-surface);color:var(--c-text-strong)}
.nmos .nmos-toast{position:sticky;bottom:16px;z-index:50;max-width:520px;margin:12px auto 0;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 14px;border-radius:11px;background:var(--c-raised-hover);border:1px solid ${alpha('accent', 0.52)};box-shadow:0 12px 32px rgba(0,0,0,0.5);color:var(--c-text-strong);font-size:13.5px}
.nmos .note-presets{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin:0 0 8px}
.nmos .note-sec-row{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0 6px}
.nmos .orph-head{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;margin:10px 0 8px;padding:8px 12px;border-radius:9px;background:var(--c-sunken);border:1px solid var(--c-line)}
.nmos .orph-all{display:inline-flex;align-items:center;gap:8px;margin:0;font-size:13.5px;font-weight:600;color:var(--c-text-strong);cursor:pointer}
.nmos .orph-all input[type=checkbox],.nmos .orph-row input[type=checkbox]{width:auto;flex:none;margin:2px 0 0;cursor:pointer}
.nmos .orph-list{display:flex;flex-direction:column;gap:6px;max-height:360px;overflow:auto;margin:0 0 10px}
.nmos .orph-row{display:flex;align-items:flex-start;gap:10px;padding:10px 12px;border-radius:10px;background:var(--c-sunken);border:1px solid var(--c-line);cursor:pointer;margin:0}
.nmos .orph-row:hover{border-color:var(--c-line-hover)}
.nmos .orph-row.has-carry{border-color:${alpha('warn', 0.42)};background:linear-gradient(90deg,${alpha('warn', 0.08)},var(--c-sunken) 55%)}
.nmos .orph-row-body{flex:1;min-width:0;display:flex;flex-direction:column;gap:3px}
.nmos .orph-title{font-size:14px;font-weight:600;color:var(--c-text-strong);word-break:break-word}
.nmos .orph-meta{font-size:12.5px;color:var(--c-text-muted)}
.nmos .orph-carry-warn{font-size:12.5px;color:var(--c-warn);line-height:1.45;margin-top:2px}
.nmos .orph-banner{padding:10px 12px;border-radius:9px;border:1px solid ${alpha('warn', 0.48)};background:${alpha('warn', 0.1)};color:var(--c-warn);font-size:13px;line-height:1.5;margin:0 0 10px}

@media (max-width: 860px){
  .nmos .notes-studio{grid-template-columns:1fr}
  .nmos .settings-shell{grid-template-columns:1fr}
  .nmos .settings-shell .groups{position:static;flex-direction:row;flex-wrap:wrap;gap:6px;padding:8px}
  .nmos .settings-shell .grp-label{width:100%;padding:4px 4px 2px}
  .nmos .settings-shell .groups button.group{padding:7px 10px;font-size:13px}
}
/* PHASE-69: Memory Explorer filter toolbar */
.nmos .exp-toolbar{padding:12px 14px;border-radius:12px;background:var(--c-surface);border:1px solid var(--c-line);display:flex;flex-direction:column;gap:10px}
.nmos .exp-toolbar .filter-chips{margin:0}
.nmos .exp-controls{display:flex;flex-wrap:wrap;align-items:center;gap:8px}
.nmos .exp-controls input[type=search]{flex:1 1 200px;min-width:140px;padding:7px 11px;font-size:13.5px}
.nmos .exp-controls select.exp-who{flex:0 1 170px;min-width:120px;width:auto;padding:7px 10px;font-size:13.5px}
.nmos .exp-add{margin-left:auto;white-space:nowrap}
.nmos .exp-empty{margin:10px 0;padding:22px 14px;text-align:center;color:var(--c-text-muted);font-size:14px;border:1px dashed var(--c-line-strong);border-radius:11px;background:var(--c-sunken)}
@media (max-width: 720px){
  .nmos .exp-add{margin-left:0;flex:1 1 auto}
  .nmos.shell-on .wrap{padding:12px 12px 84px}
  .nmos .nmos-topbar-in{padding:8px 12px;gap:8px}
  .nmos .nmos-nav{display:none}
  .nmos .status-pill .st-txt{display:none}
  .nmos .chat-picker{flex:1;min-width:0}
  .nmos .nmos-bottomnav{position:fixed;left:0;right:0;bottom:0;z-index:35;display:grid;grid-template-columns:repeat(4,1fr);background:${alpha('surface', 0.96)};backdrop-filter:blur(16px);border-top:1px solid var(--c-line-strong);padding:6px 6px max(8px,env(safe-area-inset-bottom))}
  .nmos .nmos-bottomnav button{flex-direction:column;gap:3px;padding:6px 4px;border:0;background:transparent;color:var(--c-text-muted);font-size:11px;font-weight:550;border-radius:8px;position:relative}
  .nmos .nmos-bottomnav button.on{color:var(--c-accent-hover);background:${alpha('accent', 0.12)}}
  .nmos .nmos-bottomnav .nav-badge{position:absolute;top:2px;right:calc(50% - 22px);min-width:16px;height:16px;font-size:10px}
  .nmos.shell-on .bar{bottom:58px;padding:10px 12px}
}
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

/** The Status tab's fix for a sidecar it cannot use: a token, a refused host, or the usual checks (audit F27). */
function fixFor(error: string | undefined): StringKey {
  const kind = failureKind(error);
  return kind === 'unauthorized' ? 'status.fix_token' : kind === 'host_refused' ? 'status.fix_host' : 'status.fix';
}

function errorText(lang: Lang, error: unknown): string {
  const text = error instanceof Error ? error.message : String(error);
  return text.replace(/^\/v1\/\S+ -> HTTP 422: /, t(lang, 'invalid')).replace(/^\/v1\/\S+ -> /, t(lang, 'sidecar_error'));
}

let current: { root: HTMLElement; select(tab: Tab, target?: PanelTarget): void } | null = null;

/** Open the NMOS panel on `tab` (or switch tabs / jump to a HUD target if it is already open). */
export async function openPanel(deps: PanelDeps, tab: Tab, target?: PanelTarget): Promise<void> {
  if (current && document.body.contains(current.root)) {
    current.select(tab, target);
    await deps.show();
    return;
  }
  if (!document.getElementById('nmos-style')) document.head.append(el('style', { id: 'nmos-style', text: CSS }));
  const lang = langOf(await deps.getArg('language'));
  current = await render(deps, lang, tab, target);
  await deps.show();
}

async function render(deps: PanelDeps, lang: Lang, tab: Tab, initialTarget?: PanelTarget):
  Promise<{ root: HTMLElement; select(tab: Tab, target?: PanelTarget): void }> {
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
  const title = el('h1', { text: L('title') });
  const legacyHeader = el('header', {}, title, language, close);
  const tabs = el('nav', { class: 'tabs' }, tabStatus, tabInspector, tabSettings);
  wrap.append(legacyHeader, tabs);
  const statusView = el('div');
  const inspectorView = el('div');
  const notesStudioView = el('div', { style: 'display:none' });
  const settingsView = el('div');
  wrap.append(statusView, inspectorView, notesStudioView, settingsView);
  let shown: Tab = tab;

  // --- floating Undo toast (#6) + onboarding helper (#9) ----------------------------------------
  let dirtyReady = false;
  const toastEl = el('div', { class: 'nmos-toast', style: 'display:none', role: 'status' });
  let toastTimer: ReturnType<typeof setTimeout> | null = null;
  function hideToast(): void {
    if (toastTimer !== null) { clearTimeout(toastTimer); toastTimer = null; }
    toastEl.style.display = 'none';
    toastEl.replaceChildren();
  }
  function showUndoToast(conversation: string, repairId: string): void {
    hideToast();
    const undoBtn = el('button', { class: 'primary mini', text: L('undo.button') });
    undoBtn.addEventListener('click', async () => {
      undoBtn.disabled = true;
      try {
        await deps.api('POST', `/v1/conversations/${conversation}/repairs/${repairId}/remove`, {}, 15_000);
        hideToast();
        say(actionMsg, L('undo.done'), 'ok');
        await showInspector();
      } catch (error) {
        say(actionMsg, errorText(lang, error), 'err');
        undoBtn.disabled = false;
      }
    });
    const dismiss = el('button', { class: 'ghost mini', 'aria-label': L('close'), text: '×' });
    dismiss.addEventListener('click', hideToast);
    toastEl.replaceChildren(el('span', { text: L('undo.applied') }), el('div', { style: 'display:flex;gap:6px' }, undoBtn, dismiss));
    toastEl.style.display = '';
    toastTimer = setTimeout(hideToast, 7000);
  }
  function onboardingCard(): HTMLElement {
    const goConn = el('button', { class: 'primary mini', text: L('onboard.step1_btn') });
    goConn.addEventListener('click', () => {
      if (viewsOn) { selectPrimary('settings'); openGroup('connection'); } else select('settings');
    });
    const goModels = el('button', { class: 'mini', text: L('onboard.step2_btn') });
    goModels.addEventListener('click', () => {
      if (viewsOn) { selectPrimary('settings'); openGroup('models'); } else select('settings');
    });
    return el('div', { class: 'onboard-card' },
      el('h2', { text: L('onboard.title') }),
      el('p', { class: 'sub', text: L('onboard.sub') }),
      el('div', { class: 'onboard-step' },
        el('div', {}, el('b', { text: L('onboard.step1') }), el('div', { class: 'sub', style: 'margin:2px 0 0', text: L('onboard.step1_sub') })),
        goConn),
      el('div', { class: 'onboard-step' },
        el('div', {}, el('b', { text: L('onboard.step2') }), el('div', { class: 'sub', style: 'margin:2px 0 0', text: L('onboard.step2_sub') })),
        goModels),
      el('div', { class: 'onboard-step' },
        el('div', {}, el('b', { text: L('onboard.step3') }), el('div', { class: 'sub', style: 'margin:2px 0 0', text: L('onboard.step3_sub') })),
        el('span', { class: 'badge', text: L('onboard.waiting') })));
  }

  // --- status tab ------------------------------------------------------------------------------
  let usageRound = 0; // a refresh or another chat's card makes an older answer stale
  let workerRound = 0; // the same for the "Model work" card
  async function refreshStatus(): Promise<void> {
    statusView.replaceChildren(el('div', { class: 'card muted', text: L('status.checking') }));
    const round = ++workerRound;
    const worker = workerCard(); // asked beside the health check; the other cards never wait for it
    const s = await deps.status();
    const base = s.sidecarUrl.replace(/\/+$/, '');
    const conn = el('div', { class: 'card' }, el('h2', { text: L('status.sidecar') }));
    if (s.connected) {
      conn.append(el('div', { class: 'line' }, el('span', { class: 'dot ok' }),
        el('span', { text: `${L('status.connected')} · NMOS ${s.version ?? ''}` })),
      el('div', { class: 'mono muted', text: base }));
      // A plugin from another build than the sidecar's (ADR 0037): features on one side are missing on the other.
      if (s.pluginExpected && s.pluginExpected !== PLUGIN_BUILD) {
        // The matching file, saved as the archives are (H21): a server-routed sidecar has no browser path to it (F26).
        const get = el('button', { class: 'mini', text: L('status.plugin_file') });
        const got = el('div', { class: 'msg' });
        get.addEventListener('click', async () => {
          get.disabled = true;
          try {
            await deps.download('/v1/plugin/nmos-pocketrisu.js', 'nmos-pocketrisu.js');
            say(got, L('status.plugin_saved', { name: 'nmos-pocketrisu.js' }), 'ok');
          } catch (error) {
            say(got, errorText(lang, error), 'err');
          } finally {
            get.disabled = false;
          }
        });
        conn.append(el('div', { class: 'line warn' }, el('span', { class: 'dot warn' }),
          el('span', { text: L('status.plugin_mismatch', { mine: PLUGIN_BUILD, theirs: s.pluginExpected }) })),
        el('div', { class: 'btns' }, get), got);
      } else if (s.pluginExpected) {
        conn.append(el('div', { class: 'muted', text: L('status.plugin_ok', { b: PLUGIN_BUILD }) }));
      }
      // No request since load: normal before the first message, a denied permission after it (a hint only).
      if (s.enabled && !s.last) conn.append(el('div', { class: 'muted', text: L('status.no_requests') }));
    } else {
      conn.append(el('div', { class: 'line' }, el('span', { class: 'dot err' }),
        el('span', { class: 'err', text: `${L('status.unreachable')}: ${base}` })),
      el('div', { class: 'muted', text: s.error ?? '' }), el('p', { class: 'sub', text: L(fixFor(s.error)) }));
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
        : s.last.outcome === 'nothing-relevant' ? L('outcome.nothing')
        : s.last.outcome === 'skipped' ? L('outcome.skipped') : L('outcome.failed');
      lastCard.append(el('div', { class: 'line' }, el('span', { class: `dot ${kind}` }), el('span', { text: what })),
        el('div', { class: 'muted', text: `${L('status.ago', { n: Math.round((Date.now() - s.last.at) / 1000) })} · ${s.last.ms}ms` }));
      // Old-dialogue trimming (PHASE-60 S1 "Shown"): what was left out, or why nothing was. Never mono (Korean text).
      const trimmed = trimStatusLine(lang, s.last.trim);
      if (trimmed !== null) lastCard.append(el('div', { class: 'muted', text: trimmed }));
      // How far memory has got (PHASE-60 S1): only when the sidecar said so; never mono (Korean text).
      const recorded = coverageLine(lang, s.last.coverage);
      if (recorded !== null) lastCard.append(el('div', { class: 'muted', text: recorded }));
      if (s.last.packet) lastCard.append(el('details', { class: 'help' },
        el('summary', { text: L('status.packet') }), el('pre', { class: 'packet', text: s.last.packet })));
      if (s.last.error) lastCard.append(el('div', { class: 'mono muted', text: s.last.error }));
    } else {
      lastCard.append(el('div', { class: 'muted', text: L('status.none') }));
    }

    const cards: HTMLElement[] = [conn, features, lastCard];
    // No Web Crypto on this page: every request is skipped, so it comes first (pre-0.4.0 audit F24).
    if (s.insecure) cards.unshift(el('div', { class: 'card err' }, el('div', { text: L('status.insecure') })));
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
    if (!s.connected && !viewsOn) cards.unshift(onboardingCard());
    const refresh = el('button', { text: L('refresh') });
    refresh.addEventListener('click', () => void refreshStatus());
    statusView.replaceChildren(...cards, el('div', { class: 'btns' }, refresh));
    void worker.then((card) => {
      if (card && s.connected && round === workerRound && conn.isConnected) conn.after(card);
    });
  }

  /** "Model work" (PHASE-61 S5): the queue, recent outcomes and the last model error; null, so no card, when the
   *  sidecar has no such route (an older one) or does not answer. */
  async function workerCard(): Promise<HTMLElement | null> {
    let raw: unknown;
    try {
      raw = await deps.api<unknown>('GET', '/v1/worker/status', undefined, 5000);
    } catch {
      return null;
    }
    const { level, lines } = workerLines(lang, raw);
    if (!lines.length) return null;
    const errorLine = (raw as WorkerStatus).last_error && level === 'trouble' ? lines.length - 1 : -1;
    return el('div', { class: 'card' }, el('h2', { text: L('worker.title') }),
      ...lines.map((text, i) => el('div', { class: i === errorLine ? 'warn' : 'muted', text })));
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
  // Only on a page that shows failed work (the sidecar marks it `has-failed`, owner 2026-10-14): it runs those again.
  const retryButton = el('button', { text: L('act.retry'), style: 'display:none' });
  // PHASE-62 S3: only where the sidecar reports turns an earlier cap read in part (a page's `has-cut`, the chat page's
  // own question): it reads those again, whole, and nothing else. The counts and the token range are the sidecar's.
  interface CutInfo { turns: number; windows: number; low: number; high: number; slow: number; shigh: number }
  const cutButton = el('button', { text: L('act.cut'), style: 'display:none' });
  const cutSummaries = el('input', { type: 'checkbox' });
  const cutSummariesText = el('span');
  const cutSummariesLabel = el('label', { class: 'sub', style: 'display:none' }, cutSummaries, cutSummariesText);
  let cutInfo: CutInfo | null = null;
  const rebuildButton = el('button', { text: L('act.rebuild') });
  const deleteButton = el('button', { text: L('act.delete') });
  const exportButton = el('button', { text: L('exp.chat') });
  // PHASE-50: sections for the chat's author's note. The sidecar writes them; the panel shows and copies them, since it
  // runs none of a page's scripts.
  const notesButton = el('button', { text: L('notes.open') });
  const notesCard = el('div', { class: 'card', style: 'display:none' });
  const factAddButton = el('button', { text: L('rp.fact_add') });
  const factAddCard = el('div', { class: 'card', style: 'display:none' });
  let notesFor: string | null = null; // the chat the note form is for: a page's, or the hub's
  let hubConversation: string | null = null; // the chat the hub is about (PHASE-52), from its answer
  let viewsOn = false; // the sidecar has the new screens (PHASE-52): hub first, settings in groups
  let mapOn = false; // and the memory map (PHASE-55): the hub and the memory document lead to it when asked
  let graphOn = false; // and its drawing as data, drawn here (PHASE-55 step 6)
  const actionMsg = el('div', { class: 'msg' });
  const actions = el('div', {}, el('div', { class: 'btns' }, retryButton, historyButton, cutButton, cutSummariesLabel, rebuildButton,
    exportButton, notesButton, factAddButton, deleteButton),
    el('details', { class: 'sub help' }, el('summary', { text: L('act.help') }), el('p', { text: L('act.sub') })));
  // The message sits outside the actions so a result stays visible after a delete returns to the list.
  // Back and Refresh stay in reach while reading far down a page.
  // On an entity's page: the owner joins it with another entity of its type, or undoes a join (ADR 0025).
  const linkCard = el('div', { class: 'card', style: 'display:none' });
  // On a character's page: the owner pins it so its facts go into every reply's memory (ADR 0087). Built here, beside
  // the sidecar's page, which stays as it is sent.
  const pinCard = el('div', { class: 'card', style: 'display:none' });
  // On a conversation's page: how memory treats what only some characters know (ADR 0035).
  const modeCard = el('div', { class: 'card', style: 'display:none' });
  const statusCard = el('div', { id: 'nmos-status-windows', class: 'card', style: 'display:none' });
  // The owner's repairs (ADR 0044): the threads picked for closing together, and the close controls on the page now,
  // by thread (one can show twice: under Threads and under Needs attention; its controls stay in step).
  const picked = new Set<string>();
  const chosen = new Map<string, string>(); // the outcome picked for a thread, kept through a refresh
  let closers = new Map<string, { first?: string; boxes: HTMLInputElement[]; selects: HTMLSelectElement[] }>();
  const bulkClose = el('button');
  // Needs attention in bulk (PHASE-57 B1): the rows picked, by what they send; select all of a kind; apply or retract
  // the picked rows after the sidecar's preview. The sidecar says what each row's Apply and Retract are.
  const bulkPicked = new Map<string, BulkMark>();
  let bulkGroups = new Map<string, { label: string; boxes: HTMLInputElement[] }>();
  let pendingBulk: 'apply' | 'retract' | null = null;
  const bulkKinds = el('div', { class: 'btns' });
  const bulkApply = el('button');
  const bulkRetract = el('button');
  const bulkBar = el('div', { class: 'bulk-card', style: 'display:none' }, el('div', { class: 'btns' }, bulkClose, bulkApply, bulkRetract),
    bulkKinds);
  const inspbar = el('div', { class: 'btns inspbar' }, inspectorBack, inspectorRefresh);
  const homeQuickBar = el('div', { class: 'home-quick', style: 'display:none' });
  const memSubBar = el('div', { class: 'mem-subbar', style: 'display:none' });
  inspectorView.append(inspbar, homeQuickBar, memSubBar, actions, actionMsg, notesCard, factAddCard,
    bulkBar, modeCard, statusCard, pinCard, linkCard, inspectorBody, inspectorAddress);
  function updateBulk(): void {
    bulkBar.style.display = picked.size || bulkGroups.size ? '' : 'none';
    bulkClose.style.display = picked.size ? '' : 'none';
    bulkClose.textContent = L('rp.bulk', { n: picked.size });
    const marks = [...bulkPicked.values()];
    for (const [button, side, key] of [[bulkApply, 'apply', 'bk.apply'], [bulkRetract, 'retract', 'bk.retract']] as const) {
      button.style.display = marks.length ? '' : 'none';
      button.textContent = pendingBulk === side ? L('bk.again') : L(key, { n: marks.filter((m) => m[side]).length });
    }
    bulkKinds.style.display = bulkGroups.size ? '' : 'none';
  }
  /** Apply or retract the picked rows: first the sidecar's preview (what each would do, what is skipped), then, on a
   * second press, the batch, written in one transaction or not at all. */
  async function runBulk(side: 'apply' | 'retract', button: HTMLButtonElement): Promise<void> {
    const conversation = inspectorConversation(inspectorPath);
    if (!conversation || !bulkPicked.size) return;
    const marks = [...bulkPicked.values()];
    const sent = marks.map((m) => m[side]).filter((r): r is BulkRequest => r !== undefined);
    const skipped = marks.length - sent.length;
    if (!sent.length) return void say(actionMsg, L('bk.none', { n: skipped }), 'warn');
    const body = { items: sent.filter((r) => 'kind' in r), undo: sent.flatMap((r) => ('undo' in r ? [r.undo] : [])) };
    const path = `/v1/conversations/${conversation}/repairs/batch`;
    button.disabled = true;
    try {
      if (pendingBulk !== side) {
        const plan = await deps.api<{ counts: Record<string, number>; errors: number; plan: { error?: string }[] }>(
          'POST', path, { ...body, preview: true }, 15_000);
        if (plan.errors) {
          const first = plan.plan.find((p) => p.error)?.error ?? '';
          return void say(actionMsg, L('bk.refused', { n: plan.errors, e: first }), 'err');
        }
        const what = Object.entries(plan.counts).map(([k, n]) => `${L(`rp.${k}` as StringKey)} ${n}`).join(', ');
        pendingBulk = side;
        say(actionMsg, L('bk.confirm', { what, n: skipped }), 'warn');
        return;
      }
      pendingBulk = null;
      await deps.api('POST', path, body, 30_000);
      bulkPicked.clear();
      say(actionMsg, L('bk.done', { n: sent.length }), 'ok');
      await showInspector();
    } catch (error) {
      pendingBulk = null;
      say(actionMsg, errorText(lang, error), 'err');
    } finally {
      button.disabled = false;
      updateBulk();
    }
  }
  bulkApply.addEventListener('click', () => void runBulk('apply', bulkApply));
  bulkRetract.addEventListener('click', () => void runBulk('retract', bulkRetract));
  /** The outcome a close of this thread sends: the one picked on the page, else its kind's default. */
  function outcomeOf(item: string): Record<string, string> {
    const c = closers.get(item);
    const outcome = c?.selects[0]?.value ?? c?.first;
    return outcome ? { outcome } : {};
  }
  /** The controls for one repair the page marks. */
  function repairControls(action: RepairAction): Node[] {
    if (action.kind === 'thread_close') return closeControls(action);
    const field = (action.extra ?? '').split('.')[0];
    const n = action.kind === 'fact_correct' ? L(field === 'object' ? 'rp.field_object' : 'rp.field_value')
      : action.extra ?? '';
    // canon's statement in a conflict is corrected and kept (PHASE-57 B2)
    const label = action.kind === 'fact_correct' && action.extra?.endsWith('.lock') ? 'rp.fact_correct_lock' : `rp.${action.kind}`;
    const button = el('button', { class: 'mini', text: L(label as StringKey, { n }) });
    const spot = el('div');
    button.addEventListener('click', () => {
      if (action.kind === 'fact_correct') correctForm(action, button);
      else if (action.kind === 'fact_hidden') hiddenForm(action, button);
      else if (action.kind === 'branch_inherit') void branchInherit(action, button, spot);
      else if (action.kind === 'undo' && (action.extra === 'name_split' || action.extra === 'entity_exclude')) {
        void undoSplit(action, button, spot); // previewed: a split's and an exclusion's undo (PHASE-20 Q2, PHASE-47)
      } else if (action.kind === 'entity_exclude') void notACharacter(action, button, spot);
      else if (action.kind === 'alias_join') void aliasJoin(action, button, spot);
      else void repairNow(action, button);
    });
    return [button, spot];
  }
  /** A close: the outcomes of the thread's kind (the default first), a box to close several at once, the button. */
  function closeControls(action: RepairAction): Node[] {
    const item = action.item;
    const choices = closeOutcomes(action.extra);
    if (inspectorPath.startsWith('/v1/views/')) { // the new screens: one button an ending, no bulk box (PHASE-52)
      const ends = (choices.length ? choices : ['']).map((o) => {
        const b = el('button', { class: 'mini', text: o ? outcomeLabel(o) : L('rp.thread_close') });
        b.addEventListener('click', () => void repairNow(action, b, o ? { outcome: o } : {}));
        return b;
      });
      return [el('span', { class: 'rp-ask', text: L('rp.how_ended') }), ...ends];
    }
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
    const field = (action.extra ?? '').split('.')[0] === 'object' ? 'object' : 'value';
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
      if (action.extra?.endsWith('.lock')) body.lock = true;  // canon's statement, kept as corrected (PHASE-57 B2)
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
  /** Inline form for `fact_hidden`: add or remove a character from a story fact's `hidden_from`. */
  function hiddenForm(action: RepairAction, button: HTMLButtonElement): void {
    const spot = button.parentElement;
    if (!spot) return;
    const who = el('input', { type: 'text', placeholder: L('fh.char'), 'aria-label': L('fh.char') });
    const mode = el('select', { class: 'mini' },
      el('option', { value: '1', text: L('fh.hide') }),
      el('option', { value: '0', text: L('fh.unhide') }));
    const save = el('button', { class: 'mini', text: L('save') });
    const cancel = el('button', { class: 'mini', text: L('cancel') });
    cancel.addEventListener('click', () => spot.replaceChildren(...repairControls(action)));
    save.addEventListener('click', () => {
      const name = who.value.trim();
      if (!name) return void who.focus();
      void repairNow(action, save, { character: name, hidden: mode.value === '1' });
    });
    spot.replaceChildren(el('span', { class: 'rpform' }, who, mode, save, cancel));
    who.focus();
  }
  /** Branch back-fill: dry-run preview first, then confirm to copy origin memory for the shared prefix. */
  async function branchInherit(action: RepairAction, button: HTMLButtonElement, spot: HTMLElement): Promise<void> {
    const conversation = inspectorConversation(inspectorPath) ?? action.item;
    if (!conversation) return;
    interface InheritResult { status?: string; prefix?: number; copied?: Record<string, number> }
    const path = `/v1/conversations/${conversation}/branch-inherit`;
    button.disabled = true;
    let preview: InheritResult;
    try {
      preview = await deps.api<InheritResult>('POST', path, { dry_run: true }, 30_000);
    } catch (error) {
      say(actionMsg, errorText(lang, error), 'err');
      button.disabled = false;
      return;
    }
    const c = preview.copied ?? {};
    const total = Object.values(c).reduce((a, b) => a + (Number(b) || 0), 0);
    if (preview.status !== 'done' || total === 0) {
      say(actionMsg, L('bi.empty', { s: preview.status ?? 'empty' }), 'ok');
      spot.replaceChildren();
      button.disabled = false;
      return;
    }
    const ok = el('button', { class: 'mini', text: L('bi.confirm') });
    const cancel = el('button', { class: 'mini', text: L('cancel') });
    cancel.addEventListener('click', () => { spot.replaceChildren(); button.disabled = false; });
    ok.addEventListener('click', async () => {
      ok.disabled = true;
      try {
        const res = await deps.api<InheritResult>('POST', path, { dry_run: false }, 60_000);
        const rc = res.copied ?? {};
        spot.replaceChildren();
        say(actionMsg, L('bi.done', { x: rc.extractions ?? 0, s: rc.summaries ?? 0, r: rc.repairs ?? 0 }), 'ok');
        await showInspector();
      } catch (error) {
        say(actionMsg, errorText(lang, error), 'err');
        ok.disabled = false;
      }
    });
    spot.replaceChildren(el('div', { class: 'preview' }, el('b', { text: L('bi.title') }),
      el('div', { text: L('bi.preview', { p: preview.prefix ?? 0, x: c.extractions ?? 0, s: c.summaries ?? 0,
        e: c.embeddings ?? 0, r: c.repairs ?? 0, l: c.links ?? 0 }) }),
      el('div', { class: 'btns' }, ok, cancel)));
  }
  /** A held alias linked by the owner (PHASE-29 Q5): the join's preview and link, naming the held row. */
  async function aliasJoin(action: RepairAction, button: HTMLButtonElement, spot: HTMLElement): Promise<void> {
    const conversation = inspectorConversation(inspectorPath);
    const pair = aliasPair(action);
    if (!conversation || !pair) return;
    const path = `/v1/conversations/${conversation}/entity-links`;
    const body = { entity_type: 'character', ...pair, held_alias: Number(action.item) };
    await withPreview(spot, button, `${path}/preview`, body, 'pv.confirm_join', async (expect) => {
      await deps.api('POST', path, { ...body, expect }, 15_000);
      say(actionMsg, L('link.done', { a: pair.name, b: pair.same_as }), 'ok');
      await showInspector();
    });
  }
  /** "Not a character" (PHASE-47 S4, Q1 a): out of the cast by default, every fact kept; a box offers memory too,
   * with how many facts that also hides. The action carries the fingerprint of the scope it was previewed for. */
  async function notACharacter(action: RepairAction, button: HTMLButtonElement, spot: HTMLElement): Promise<void> {
    const conversation = inspectorConversation(inspectorPath);
    if (!conversation) return;
    const path = `/v1/conversations/${conversation}/repairs`;
    const body = { kind: 'entity_exclude', item: action.item };
    const preview = (scope: string) => deps.api<ExcludePreview>('POST', `${path}/preview`, { ...body, scope }, 15_000);
    button.disabled = true;
    let p: ExcludePreview;
    try {
      p = await preview('cast');
    } catch (error) {
      say(actionMsg, errorText(lang, error), 'err');
      button.disabled = false;
      return;
    }
    const also = el('input', { type: 'checkbox', 'aria-label': L('ex.also', { f: p.scopes.memory.facts }) });
    const ok = el('button', { class: 'mini', text: L('ex.confirm') });
    const cancel = el('button', { class: 'mini', text: L('cancel') });
    cancel.addEventListener('click', () => { spot.replaceChildren(); button.disabled = false; });
    ok.addEventListener('click', async () => {
      ok.disabled = true;
      const scope = also.checked ? 'memory' : 'cast';
      try {
        const expect = scope === 'cast' ? p.fingerprint : (await preview('memory')).fingerprint;
        await deps.api('POST', path, { ...body, scope, expect }, 15_000);
        spot.replaceChildren();
        say(actionMsg, L('ex.done'), 'ok');
        await showInspector();
      } catch (error) {
        say(actionMsg, errorText(lang, error), 'err');
        ok.disabled = false;
      }
    });
    spot.replaceChildren(el('div', { class: 'preview' }, el('b', { text: L('pv.title') }),
      el('div', { text: L('ex.cast', { p: p.scopes.cast.pairs }) }),
      el('div', { class: 'check' }, also, el('span', { text: L('ex.also', { f: p.scopes.memory.facts }) })),
      el('div', { class: 'btns' }, ok, cancel)));
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
    } else if (action.kind === 'undo_batch') {  // every repair of one bulk action still in force (PHASE-57 B1)
      path = `${path}/batch/${action.item}/remove`;
      body = {};
    } else if (action.kind === 'secret_found_out' || action.kind === 'secret_keep') {
      body.character = action.extra;
    } else if (action.kind === 'attention_dismiss' && action.extra) {
      body.attention = action.extra;
    }
    button.disabled = true;
    try {
      const r = await deps.api<{ repair?: { id?: string } }>('POST', path, body, 15_000);
      picked.delete(action.item);
      updateBulk();
      const isUndo = action.kind === 'undo' || action.kind === 'undo_batch';
      say(actionMsg, L(isUndo ? 'rp.undone' : 'rp.done'), 'ok');
      if (!isUndo && typeof r?.repair?.id === 'string' && r.repair.id) showUndoToast(conversation, r.repair.id);
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
    // The chat list's search box (PHASE-52 D7): the sidecar marks where; the sanitizer keeps no input of its own.
    for (const slot of Array.from(page.querySelectorAll('.v-filter'))) {
      const box = el('input', { type: 'search', placeholder: L('chats.search'), 'aria-label': L('chats.search') });
      box.addEventListener('input', () => {
        const q = box.value.trim().toLowerCase();
        for (const row of Array.from(inspectorBody.querySelectorAll<HTMLElement>('.v-chat'))) {
          row.style.display = !q || (row.textContent ?? '').toLowerCase().includes(q) ? '' : 'none';
        }
      });
      slot.append(box);
    }
    // Story document search & open-thread kind filter (#4): injected client-side so sanitizer stays untouched.
    if (inspectorPath.includes('/memory')) {
      const docMain = page.querySelector<HTMLElement>('.v-doc-main') ?? page.querySelector<HTMLElement>('.v-doc');
      if (docMain) {
        const docInput = el('input', { type: 'search', placeholder: L('mem.search_doc'), 'aria-label': L('mem.search_doc') });
        const emptyNote = el('p', { class: 'v-note doc-search-empty', style: 'display:none', text: L('mem.search_empty') });
        const searchBar = el('div', { class: 'doc-search-bar' }, docInput, emptyNote);
        let threadKind = 'all';
        const applyDocFilter = () => {
          const q = docInput.value.trim().toLowerCase();
          const active = q.length > 0 || threadKind !== 'all';
          let visibleSecs = 0;
          for (const sec of Array.from(inspectorBody.querySelectorAll<HTMLElement>('.v-sec'))) {
            const isOpenSec = sec.id === 's-open';
            for (const det of Array.from(sec.querySelectorAll<HTMLDetailsElement>('details.v-more'))) {
              if (active) {
                if (!('wasOpen' in det.dataset)) det.dataset.wasOpen = det.open ? '1' : '0';
                det.open = true;
              } else if ('wasOpen' in det.dataset) {
                det.open = det.dataset.wasOpen === '1';
                delete det.dataset.wasOpen;
              }
            }
            const rows = Array.from(sec.querySelectorAll<HTMLElement>('.v-line, .v-ev'));
            if (!rows.length) {
              const show = !q || (sec.textContent ?? '').toLowerCase().includes(q);
              sec.style.display = show ? '' : 'none';
              if (show) visibleSecs += 1;
              continue;
            }
            let shownRows = 0;
            for (const row of rows) {
              const textOk = !q || (row.textContent ?? '').toLowerCase().includes(q);
              const kindOk = !isOpenSec || threadKind === 'all' || !!row.querySelector(`.v-tag.k-${threadKind}`);
              const show = textOk && kindOk;
              row.style.display = show ? '' : 'none';
              if (show) shownRows += 1;
            }
            const showSec = shownRows > 0 || (!active && !isOpenSec);
            sec.style.display = showSec ? '' : 'none';
            if (showSec) visibleSecs += 1;
          }
          emptyNote.style.display = active && visibleSecs === 0 ? '' : 'none';
        };
        docInput.addEventListener('input', applyDocFilter);
        docMain.prepend(searchBar);
        const openSec = page.querySelector<HTMLElement>('#s-open');
        if (openSec) {
          const kinds = (['promise', 'goal', 'threat', 'question', 'debt'] as const)
            .filter((k) => openSec.querySelector(`.v-tag.k-${k}`));
          if (kinds.length > 1) {
            const chips = el('div', { class: 'filter-chips' });
            const btns: HTMLButtonElement[] = [];
            for (const k of ['all', ...kinds] as const) {
              const b = el('button', { type: 'button', class: `filter-chip${k === 'all' ? ' on' : ''}`,
                'data-th-kind': k, text: L(`mem.filter_${k}` as StringKey) });
              b.addEventListener('click', () => {
                threadKind = k;
                for (const x of btns) x.classList.toggle('on', x.dataset.thKind === k);
                applyDocFilter();
              });
              btns.push(b);
              chips.append(b);
            }
            const h2 = openSec.querySelector('.v-h2');
            if (h2) h2.after(chips); else openSec.prepend(chips);
          }
        }
      }
    }
    // PHASE-69 S1: Memory Explorer interactive toolbar (category pills, search, character dropdown, canon toggle, +Add fact).
    if (inspectorPath.includes('/explore')) {
      const slot = page.querySelector<HTMLElement>('.v-exp-toolbar-slot');
      const cards = Array.from(page.querySelectorAll<HTMLElement>('.v-exp-card'));
      const sections = Array.from(page.querySelectorAll<HTMLElement>('.v-sec[data-cat]'));
      if (slot) {
        const CATS = ['facts', 'pairs', 'threads', 'epistemic', 'items', 'entities', 'canon'] as const;
        const whoCounts = new Map<string, number>();
        let canonCount = 0;
        let nonCanonStoryCount = 0;
        for (const c of cards) {
          const isCanon = c.getAttribute('data-canon') === '1';
          if (isCanon) canonCount += 1;
          else if (['facts', 'pairs', 'items'].includes(c.getAttribute('data-cat') ?? '')) nonCanonStoryCount += 1;
          const rawWho = c.getAttribute('data-who') ?? '';
          for (const w of rawWho.split('|')) {
            const name = w.trim();
            if (name) whoCounts.set(name, (whoCounts.get(name) ?? 0) + 1);
          }
        }
        let activeCat = 'all';
        let includeCanon = canonCount > 0 && nonCanonStoryCount === 0;
        const catBtns = new Map<string, HTMLButtonElement>();
        const chipsRow = el('div', { class: 'filter-chips' });
        const presentCats = CATS.filter((k) => cards.some((c) => c.getAttribute('data-cat') === k));
        for (const k of ['all', ...presentCats] as const) {
          const btn = el('button', { type: 'button', class: `filter-chip${k === 'all' ? ' on' : ''}`,
            'data-exp-cat': k, text: L(`exp.cat_${k}` as StringKey) });
          btn.addEventListener('click', () => {
            activeCat = k;
            for (const [ck, b] of catBtns) b.classList.toggle('on', ck === k);
            applyExploreFilter();
          });
          catBtns.set(k, btn);
          chipsRow.append(btn);
        }
        const searchInput = el('input', { type: 'search', placeholder: L('exp.search'), 'aria-label': L('exp.search') });
        const controls = el('div', { class: 'exp-controls' }, searchInput);
        const whoNames = Array.from(whoCounts.entries())
          .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
          .map(([name]) => name);
        let whoSelect: HTMLSelectElement | null = null;
        if (whoNames.length) {
          whoSelect = el('select', { class: 'exp-who', 'aria-label': L('exp.who_label') },
            el('option', { value: '', text: L('exp.who_all') }),
            ...whoNames.map((name) => el('option', { value: name, text: name })));
          whoSelect.addEventListener('change', () => applyExploreFilter());
          controls.append(whoSelect);
        }
        if (canonCount > 0) {
          const canonBtn = el('button', { type: 'button',
            class: `filter-chip exp-canon-toggle${includeCanon ? ' on' : ''}`,
            text: L('exp.include_canon', { n: canonCount }) });
          canonBtn.addEventListener('click', () => {
            includeCanon = !includeCanon;
            canonBtn.classList.toggle('on', includeCanon);
            applyExploreFilter();
          });
          controls.append(canonBtn);
        }
        const convId = inspectorConversation(inspectorPath);
        if (convId) {
          const addBtn = el('button', { type: 'button', class: 'primary mini exp-add', text: L('exp.add_fact') });
          addBtn.addEventListener('click', () => {
            if (factAddCard.style.display !== 'none') {
              factAddCard.style.display = 'none';
              return;
            }
            factAddCard.style.display = '';
            void buildFactAdd(convId);
            factAddCard.scrollIntoView({ block: 'nearest' });
          });
          controls.append(addBtn);
        }
        const emptyNote = el('div', { class: 'exp-empty', style: 'display:none', text: L('exp.empty') });
        const toolbar = el('div', { class: 'exp-toolbar' }, chipsRow, controls);
        slot.replaceChildren(toolbar, emptyNote);

        const applyExploreFilter = () => {
          const q = searchInput.value.trim().toLowerCase();
          const selectedWho = whoSelect?.value ?? '';
          const perCat = new Map<string, number>();
          let totalMatchingAll = 0;
          let visibleTotal = 0;
          for (const card of cards) {
            const cat = card.getAttribute('data-cat') ?? '';
            const isCanon = card.getAttribute('data-canon') === '1';
            const whoOk = !selectedWho || (card.getAttribute('data-who') ?? '').split('|').includes(selectedWho);
            const textOk = !q || (card.textContent ?? '').toLowerCase().includes(q);
            const canonOkForAll = includeCanon || !isCanon;
            if (whoOk && textOk && (cat === 'canon' || canonOkForAll)) {
              perCat.set(cat, (perCat.get(cat) ?? 0) + 1);
              totalMatchingAll += 1;
            }
            const catOk = activeCat === 'all' || cat === activeCat;
            const canonOk = activeCat === 'canon' || includeCanon || !isCanon;
            const show = catOk && canonOk && whoOk && textOk;
            card.style.display = show ? '' : 'none';
            if (show) visibleTotal += 1;
          }
          for (const [k, btn] of catBtns) {
            const n = k === 'all' ? totalMatchingAll : (perCat.get(k) ?? 0);
            btn.textContent = `${L(`exp.cat_${k}` as StringKey)} (${n})`;
          }
          for (const sec of sections) {
            const cat = sec.getAttribute('data-cat') ?? '';
            const secCards = cards.filter((c) => c.getAttribute('data-cat') === cat);
            const shown = secCards.filter((c) => c.style.display !== 'none').length;
            const catOk = activeCat === 'all' || cat === activeCat;
            const hasActiveFilter = q.length > 0 || selectedWho.length > 0 || activeCat !== 'all';
            sec.style.display = catOk && (shown > 0 || (!hasActiveFilter && secCards.length === 0)) ? '' : 'none';
            const badge = sec.querySelector('.v-h2 .v-n');
            if (badge) badge.textContent = String(shown);
          }
          emptyNote.style.display = cards.length > 0 && visibleTotal === 0 ? '' : 'none';
        };
        searchInput.addEventListener('input', applyExploreFilter);
        applyExploreFilter();
      }
    }
    // Model calls log filter (#1): All / Failed only chips above the calls table.
    if (inspectorPath.startsWith('/v1/inspector/calls')) {
      const tbl = page.querySelector('table');
      const rows = tbl ? Array.from(tbl.querySelectorAll<HTMLTableRowElement>('tbody tr')) : [];
      if (tbl && rows.length) {
        let fails = 0;
        for (const tr of rows) {
          const outcome = (tr.children[2]?.textContent ?? '').trim().toLowerCase();
          const isOk = outcome === 'ok' || outcome === '성공';
          if (!isOk) { tr.classList.add('call-fail'); fails += 1; }
        }
        const allBtn = el('button', { type: 'button', class: 'filter-chip on', text: L('calls.filter_all', { n: rows.length }) });
        const failBtn = el('button', { type: 'button', class: 'filter-chip', text: L('calls.filter_fail', { n: fails }) });
        const setFailOnly = (only: boolean) => {
          allBtn.classList.toggle('on', !only);
          failBtn.classList.toggle('on', only);
          for (const tr of rows) tr.style.display = only && !tr.classList.contains('call-fail') ? 'none' : '';
        };
        allBtn.addEventListener('click', () => setFailOnly(false));
        failBtn.addEventListener('click', () => setFailOnly(true));
        tbl.before(el('div', { class: 'filter-chips' }, allBtn, failBtn));
      }
    }
    // The timeline is asked for only when its section is opened, so a chat page never holds it unasked (an iPhone's
    // Safari reloads a page under memory pressure; PHASE-32 step 3). The listener goes with the page it is on.
    for (const box of Array.from(page.querySelectorAll<HTMLElement>('details > .tl-lazy'))) {
      const section = box.parentElement as HTMLDetailsElement;
      section.addEventListener('toggle', () => {
        if (section.open && !box.dataset.state) void loadTimeline(box, '');
      });
    }
    // The memory map's drawing (PHASE-55 step 6): drawn here from data, in place of the note that sends a reader to a
    // browser for it; asked for after the page shows, so the lines never wait on it.
    const note = graphOn ? page.querySelector<HTMLElement>('.v-graph-note') : null;
    if (note) {
      const box = el('div', { class: 'v-graph panel' });
      note.replaceWith(box);
      void loadGraph(box, note, false);
    }
    for (const spot of Array.from(page.querySelectorAll('span.rp[data-repair]'))) {
      const action = repairAction(spot.getAttribute('data-repair'));
      if (!action) continue;
      spot.replaceChildren(...repairControls(action));
      if (action.kind === 'fact_retract' && spot.closest('#s-facts') && !spot.closest('details.fold')
          && !spot.closest('[data-canon="1"]')) {
        const hid = el('span', { class: 'rp' });
        hid.replaceChildren(...repairControls({ kind: 'fact_hidden', item: action.item, extra: null }));
        spot.after(hid);
      }
    }
    for (const item of Array.from(picked)) if (!closers.has(item)) picked.delete(item); // closed or gone since
    bulkGroups = new Map();
    const shown = new Set<string>();
    for (const spot of Array.from(page.querySelectorAll('span.rq[data-bulk]'))) {
      const mark = bulkMark(spot.getAttribute('data-bulk'));
      if (!mark) continue;
      const key = JSON.stringify([mark.g, mark.apply ?? null, mark.retract ?? null]);
      shown.add(key);
      const box = el('input', { type: 'checkbox', 'aria-label': L('bk.select') });
      box.checked = bulkPicked.has(key);
      box.addEventListener('change', () => {
        if (box.checked) bulkPicked.set(key, mark); else bulkPicked.delete(key);
        pendingBulk = null;
        updateBulk();
      });
      let group = bulkGroups.get(mark.g);
      if (!group) bulkGroups.set(mark.g, group = { label: mark.l, boxes: [] });
      group.boxes.push(box);
      spot.replaceChildren(box);
    }
    for (const key of Array.from(bulkPicked.keys())) if (!shown.has(key)) bulkPicked.delete(key); // settled since
    pendingBulk = null;
    bulkKinds.replaceChildren(...Array.from(bulkGroups.values(), (group) => {
      const all = el('button', { class: 'mini', text: L('bk.all', { k: group.label, n: group.boxes.length }) });
      all.addEventListener('click', () => {
        const on = !group.boxes.every((b) => b.checked);
        for (const b of group.boxes) if (b.checked !== on) { b.checked = on; b.dispatchEvent(new Event('change')); }
      });
      return all;
    }));
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
  async function loadGraph(box: HTMLElement, note: HTMLElement, everyone: boolean): Promise<void> {
    const from = inspectorPath;
    const conv = /^\/v1\/views\/c\/[^/]+\/map(?:\?|$)/.test(from) ? inspectorConversation(from) : null;
    if (!conv) return void box.replaceWith(note);
    const focus = /\?focus=([0-9a-f-]{36})$/i.exec(from)?.[1];
    box.replaceChildren(el('div', { class: 'muted', text: L('insp.loading') }));
    try {
      const query = [focus ? `focus=${focus}` : '', everyone ? 'all=1' : '', lang === 'en' ? 'lang=en' : ''].filter(Boolean).join('&');
      const raw = await deps.api<unknown>('GET', `/v1/views/c/${conv}/map/graph${query ? `?${query}` : ''}`, undefined, 15_000);
      if (!box.isConnected || inspectorPath !== from) return; // the reader moved on
      const graph = parseGraph(raw);
      if (!graph?.edges.length) return void box.replaceWith(note);
      drawGraph(box, graph, (entity) => go(`/v1/views/c/${conv}/map?focus=${entity}`), (all) => void loadGraph(box, note, all), {
        labels: {
          search: L('graph.search'),
          zoomIn: L('graph.zoom_in'),
          zoomOut: L('graph.zoom_out'),
          filterAll: L('graph.filter_all'),
          filterSetting: L('graph.filter_setting'),
          filterStory: L('graph.filter_story'),
          filterChanged: L('graph.filter_changed'),
          filterSplit: L('graph.filter_split'),
          openPerson: L('graph.open_person'),
          focusPerson: L('graph.focus_person'),
          noTies: L('graph.no_ties'),
        },
        openPerson: (entity) => go(`/v1/views/c/${conv}/person/${entity}`),
      });
    } catch {
      if (box.isConnected) box.replaceWith(note); // the lines below hold the same
    }
  }
  async function loadTimeline(box: HTMLElement, span: string): Promise<void> {
    const from = inspectorPath;
    box.dataset.state = 'loading';
    box.replaceChildren(el('div', { class: 'muted', text: L('insp.loading') }));
    try {
      // the status window's lanes (PHASE-39) are their own part; every other lazy box is the cast's timeline
      const asked = box.classList.contains('tl-status') ? 'part=status' : 'part=timeline';
      const query = [asked, span ? `span=${span}` : '', lang === 'en' ? 'lang=en' : ''].filter(Boolean).join('&');
      const r = await deps.api<{ html: string }>('GET', `${from}?${query}`, undefined, 15_000);
      if (!box.isConnected || inspectorPath !== from) return; // the reader moved on
      const part = safeFragment(r.html);
      placeMarks(part);
      box.replaceChildren(part);
      box.dataset.state = 'loaded';
    } catch (error) {
      if (!box.isConnected) return;
      delete box.dataset.state; // opening the section again retries
      box.replaceChildren(el('div', { class: 'card err', text: errorText(lang, error) }));
    }
  }
  // A tapped mark shows its detail right under its lane; one detail at a time, replaced, never piled up.
  function showMark(mark: Element): void {
    const timeline = mark.closest('.tl');
    const row = mark.closest('.tl-row');
    if (!timeline || !row) return;
    timeline.querySelector('.tl-card')?.remove();
    if (mark.classList.contains('sel')) return void mark.classList.remove('sel'); // a second tap closes it
    for (const on of Array.from(timeline.querySelectorAll('.sel'))) on.classList.remove('sel');
    mark.classList.add('sel');
    row.after(markDetail(mark, { canon: L('tl.canon'), owner: L('tl.owner') }));
  }
  let pendingSection: string | null = null;
  function go(path: string, section: string | null = null): void {
    pendingSection = section;
    if (path === inspectorPath && !section) return void showInspector();
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
    if (conversation) {
      hubConversation = conversation;
      activeChatId = conversation;
    }
    if (conversation !== actionConversation) {
      actionConversation = conversation;
      notesCard.replaceChildren(); // another chat's sections never stay on screen
      notesCard.style.display = 'none';
      factAddCard.replaceChildren();
      factAddCard.style.display = 'none';
      notesFor = null;
      say(actionMsg, '');
      disarm();
      picked.clear();
      updateBulk();
    }
    // The new screens (PHASE-52/59) keep their actions where the design puts them: not today's row on top.
    const isView = path.startsWith('/v1/views/');
    const attentionMode = viewsOn && pendingSection === 's-attention';
    const rawInspector = Boolean(conversation && !isView && !attentionMode);
    if (rawInspector) {
      restoreLegacyActions();
      if (actionMsg.parentElement !== inspectorView) actions.after(actionMsg);
      if (modeCard.parentElement !== inspectorView) bulkBar.after(modeCard, statusCard);
    }
    actions.style.display = rawInspector ? '' : 'none';
    const shownEntity = inspectorEntity(path);
    if (!shownEntity) { linkCard.style.display = 'none'; pinCard.style.display = 'none'; }
    if (!again && !rawInspector && !path.includes('/explore')) { factAddCard.style.display = 'none'; }
    if (!rawInspector || shownEntity) { modeCard.style.display = 'none'; statusCard.style.display = 'none'; }
    if (viewsOn) syncShellForPath(path);
    if (again) {
      inspectorBody.classList.add('busy'); // the old page stays until the new one is there
    } else {
      shownPath = null;
      inspectorBody.replaceChildren(el('div', { class: 'card muted', text: L('insp.loading') }));
      pinCard.style.display = 'none';  // another page's switch never acts on the page that is loading
    }
    // Only a sidecar the browser reaches itself can be opened in a tab; a server-routed one (Docker
    // name, LAN address behind HTTPS) is reachable from the PocketRisu server only.
    const base = ((await deps.getArg('sidecar_url')) || 'http://127.0.0.1:8790').replace(/\/+$/, '');
    const direct = routeFor(base, await deps.getArg('route')) === 'direct';
    inspectorAddress.textContent = direct ? L('insp.browser', { url: `${base}/inspector${lang === 'en' ? '?lang=en' : ''}` }) : '';
    const isExploreOrAttn = Boolean(conversation && /^\/v1\/views\/c\/[^/]+\/(explore|attention)(?:\?|$)/.test(path));
    const fallbackToRaw = () => {
      if (!conversation) return false;
      pendingSection = path.includes('/attention') ? 's-attention' : null;
      void showInspector(`/v1/inspector/c/${conversation}`, at);
      return true;
    };
    try {
      // A chat's and a character's page get a closed timeline section, filled when it is opened (PHASE-32 step 3), and
      // a chat's page one for its status window (PHASE-39); a sidecar without them ignores the ask.
      const wantRich = isView && (path.includes('/memory') || path.includes('/person/'));
      const query = [conversation ? 'timeline=lazy&status=lazy' : '', isView && mapOn ? 'map=1' : '',
        wantRich ? 'rich=1' : '', lang === 'en' ? 'lang=en' : ''].filter(Boolean).join('&');
      const r = await deps.api<{ html?: string; conversation?: string | null; meta?: HubMeta }>('GET',
        `${path}${query ? `${path.includes('?') ? '&' : '?'}${query}` : ''}`, undefined, 15_000);
      if (load !== loads) return;
      if (isExploreOrAttn && typeof r?.html !== 'string') {
        if (fallbackToRaw()) return;
      }
      if (path.startsWith('/v1/views/hub')) {
        hubConversation = r.conversation ?? null;
        if (hubConversation && !path.includes('conversation=')) hostConversationId = hubConversation;
        if (hubConversation) activeChatId = hubConversation;
        if (viewsOn) applyHubMeta(r.meta);
      }
      const page = safeFragment(r.html ?? '');
      placeMarks(page); // a person's circles (PHASE-52 D4)
      enhance(page);
      retryButton.style.display = page.querySelector('.has-failed') ? '' : 'none';
      if (page.querySelector('.has-cut') && conversation) void loadCut(conversation);
      else showCut(null);
      inspectorBody.replaceChildren(page);
      shownPath = path;
      const focusSec = pendingSection;
      pendingSection = null;
      if (focusSec) {
        const target = inspectorBody.querySelector<HTMLElement>(`#${focusSec}`);
        if (target) {
          if (target instanceof HTMLDetailsElement) target.open = true;
          target.scrollIntoView({ block: 'start' });
        } else if (keep) restore(keep);
        else root.scrollTop = 0;
      } else if (keep) restore(keep);
      else root.scrollTop = 0;
      if (viewsOn) syncShellForPath(path);
      if (shownEntity) void showEntityCards(shownEntity.conversation, shownEntity.entity, load);
      else if (conversation && !isView && !attentionMode) { void showMode(conversation, load); void showStatusWindows(conversation, load); }
    } catch (error) {
      if (load !== loads) return;
      if (isExploreOrAttn && /(?:HTTP\s+404|\b404\b)/i.test(String((error as Error)?.message ?? error))) {
        if (fallbackToRaw()) return;
      }
      shownPath = null;
      retryButton.style.display = 'none';
      showCut(null);
      pinCard.style.display = 'none';
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
      el('div', { class: 'btns' }, save), msg, ...await repliesOnly(conversation));
    modeCard.style.display = '';
  }
  /** "Remember AI replies only" (PHASE-48 S1, step 2): set at once, nothing queued, and undone at once; none on an
   * older sidecar. */
  async function repliesOnly(conversation: string): Promise<Node[]> {
    let on: boolean;
    try {
      on = (await deps.api<{ on: boolean }>('GET', `/v1/conversations/${conversation}/replies-only`, undefined, 15_000)).on;
    } catch {
      return [];
    }
    const box = el('input', { type: 'checkbox', 'aria-label': L('ro.title') });
    box.checked = on;
    const msg = el('div', { class: 'msg' });
    box.addEventListener('change', async () => {
      box.disabled = true;
      try {
        const r = await deps.api<{ on: boolean }>('PUT', `/v1/conversations/${conversation}/replies-only`,
          { on: box.checked }, 15_000);
        box.checked = r.on;
        say(msg, L(r.on ? 'ro.on' : 'ro.off'), 'ok');
      } catch (error) {
        box.checked = !box.checked;
        say(msg, errorText(lang, error), 'err');
      } finally { box.disabled = false; }
    });
    return [el('div', { class: 'check' }, box, el('span', { text: L('ro.title') })),
      el('p', { class: 'sub', text: L('ro.sub') }), msg];
  }
  /** This chat's status windows (PHASE-43 S3): what was found by its shape, tracked on the owner's confirmation (Q1)
   *  for the card (Q2), with pins (Q3). Only this chat: every card's rules stay under Settings, folded. */
  async function showStatusWindows(conversation: string, load: number): Promise<void> {
    let found: StatusCandidates;
    try {
      found = await deps.api<StatusCandidates>('GET', `/v1/conversations/${conversation}/status/candidates`, undefined, 15_000);
    } catch {
      statusCard.style.display = 'none'; // an older sidecar finds no windows
      return;
    }
    if (load !== loads) return;
    if (!found || !Array.isArray(found.candidates)) { statusCard.style.display = 'none'; return; }
    const msg = el('div', { class: 'msg', role: 'status' });
    const card = found.card;
    const cardLabel = found.card_name || card || '';
    const act = async (button: HTMLButtonElement, method: Method, path: string, body: unknown, done: string) => {
      button.disabled = true;
      try {
        await deps.api(method, path, body, 30_000);
        await showStatusWindows(conversation, load);
        say(statusCard.querySelector('.msg') as HTMLElement, done, 'ok');
      } catch (error) { say(msg, errorText(lang, error), 'err'); button.disabled = false; }
    };
    const rows = found.candidates.map((c) => {
      const preview = c.keys.slice(0, 8).map((k) => `${k}: ${c.values[k] ?? ''}`).join(' · ')
        + (c.keys.length > 8 ? ' …' : '');
      const head = el('div', { class: 'line' }, el('span', { class: `dot ${c.tracked ? 'ok' : 'muted'}` }),
        el('span', { text: L(c.tracked ? 'sw.tracked' : 'sw.found', { n: c.keys.length, c: c.count }) }));
      const box = el('div', { class: 'sw-window' }, head, el('div', { class: 'sub', text: preview }));
      if (!card) return box;
      if (!c.tracked) {
        const track = el('button', { class: 'primary', text: L('sw.track') });
        track.addEventListener('click', () => void act(track, 'POST', '/v1/parsers/card/track',
          { card, conversation_id: conversation, keys: c.keys }, L('sw.tracked_now', { card: cardLabel })));
        box.append(el('div', { class: 'btns' }, track));
        return box;
      }
      const pins = c.keys.map((k) => {
        const box = el('input', { type: 'checkbox', value: k });
        box.checked = found.pins.includes(k);
        return el('label', { class: 'check' }, box, el('span', { text: `📌 ${k}` }));
      });
      const savePins = el('button', { text: L('sw.save_pins') });
      savePins.addEventListener('click', () => void act(savePins, 'PUT', '/v1/parsers/card/pins', {
        card, conversation_id: conversation,
        keys: pins.map((p) => p.querySelector('input') as HTMLInputElement).filter((i) => i.checked).map((i) => i.value),
      }, L('sw.pins_saved')));
      const buttons = el('div', { class: 'btns' }, savePins);
      if (c.rule_id) {
        const untrack = el('button', { text: L('sw.untrack') });
        untrack.addEventListener('click', () => void act(untrack, 'POST', '/v1/parsers/card/untrack',
          { card, conversation_id: conversation, rule_id: c.rule_id }, L('sw.untracked')));
        buttons.append(untrack);
      } else {
        box.append(el('p', { class: 'sub', text: L('sw.by_rule') }));
      }
      box.append(el('p', { class: 'sub', text: L('sw.pins_sub') }), el('div', { class: 'pins' }, ...pins), buttons);
      return box;
    });
    statusCard.replaceChildren(el('h2', { text: L('sw.title') }),
      el('p', { class: 'sub', text: card ? L('sw.sub', { card: cardLabel }) : L('sw.no_card') }),
      ...(rows.length ? rows : [el('p', { class: 'muted', text: L('sw.none') })]), msg);
    statusCard.style.display = '';
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
  /** An entity's page's cards, from one list of the chat's entities: the pin switch and the joins. */
  async function showEntityCards(conversation: string, entity: string, load: number): Promise<void> {
    let entities: PinRow[] | null;
    try {
      const rows = await deps.api<PinRow[]>('GET', `/v1/conversations/${conversation}/entities`, undefined, 15_000);
      entities = Array.isArray(rows) ? rows : null;
    } catch {
      entities = null; // the page itself already reports a failing sidecar
    }
    if (load !== loads) return;
    showPin(conversation, entity, entities);
    showLinks(conversation, entity, entities ?? []);
  }
  /** Said once in the pin card after the refresh that follows a pin or an unpin of that entity. */
  let pinSaid: { entity: string; key: StringKey } | null = null;
  /** The pin switch (ADR 0087), for a character that is not the persona and not excluded (an exclusion wins). A list
   *  from a sidecar older than pins has no `pinned` anywhere: the switch is off and simply pins. */
  function showPin(conversation: string, entity: string, entities: PinRow[] | null): void {
    const row = entities?.find((e) => e.id === entity);
    const said = pinSaid?.entity === entity ? pinSaid.key : null;
    pinSaid = null;
    if (!row || row.type !== 'character' || row.persona || row.excluded) {
      pinCard.style.display = 'none';
      pinCard.replaceChildren();
      return;
    }
    const pinned = typeof row.pinned === 'string' && row.pinned ? row.pinned : null;
    const box = el('input', { type: 'checkbox' });
    box.checked = pinned !== null;
    const msg = el('div', { class: 'msg', role: 'status' });
    if (said) say(msg, L(said), 'ok');
    box.addEventListener('change', async () => {
      const on = box.checked;
      box.disabled = true;
      say(msg, '');
      try {
        if (on) await deps.api('POST', `/v1/conversations/${conversation}/repairs`, { kind: 'entity_pin', item: entity }, 15_000);
        else if (pinned) await deps.api('POST', `/v1/conversations/${conversation}/repairs/${pinned}/remove`, {}, 15_000);
        pinSaid = { entity, key: on ? 'pin.done' : 'pin.undone' };
        say(msg, L(pinSaid.key), 'ok');
        await showInspector();
      } catch (error) {
        box.checked = !on;  // nothing changed: the switch says so
        say(msg, errorText(lang, error), 'err');
      } finally {
        box.disabled = false;
      }
    });
    pinCard.replaceChildren(el('h2', { text: L('pin.title', { n: row.name }) }), el('p', { class: 'sub', text: L('pin.sub') }),
      el('label', { class: 'check' }, box, el('span', { text: L('pin.toggle') })), msg);
    pinCard.style.display = '';
  }
  function showLinks(conversation: string, entity: string, entities: EntityRow[]): void {
    const choices = linkChoices(entities, entity);
    if (!choices) {
      linkCard.style.display = 'none';
      return;
    }
    const { self, others } = choices;
    const entityDest = (eid: string) =>
      inspectorPath.startsWith('/v1/views/') ? `/v1/views/c/${conversation}/person/${eid}` : `/v1/inspector/c/${conversation}/e/${eid}`;
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
            if (next && next.id !== entity) go(entityDest(next.id));
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
          if (next && next.id !== entity) go(entityDest(next.id));
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
          if (r.entity && r.entity.id !== entity) go(entityDest(r.entity.id));
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
    const clicked = event.target instanceof Element ? event.target : null;
    const act = clicked?.closest('[data-act]')?.getAttribute('data-act');
    if (act) {
      event.preventDefault();
      return void doAct(act);
    }
    // A line of a new screen shows its repair when tapped (PHASE-52 D2), not on every line at once.
    const row = clicked?.closest('.v-line');
    if (row && !clicked?.closest('a, button, select, input, label, .rp')) return void row.classList.toggle('open');
    const choice = clicked?.closest('.tl-span[data-span]');
    const box = choice?.closest<HTMLElement>('.tl-lazy');
    if (choice && box) return void loadTimeline(box, choice.getAttribute('data-span') ?? '');
    const mark = clicked?.closest('.tl [data-v]');
    if (mark) return showMark(mark);
    const link = clicked ? clicked.closest('a') : null;
    if (!link) return;
    event.preventDefault();
    const href = link.getAttribute('href');
    const section = sectionTarget(href);
    const path = inspectorApiPath(href);
    if (!path || path === inspectorPath) {
      const target = section ? inspectorBody.querySelector<HTMLElement>(`#${section}`) : null;
      if (target) {
        if (target instanceof HTMLDetailsElement) target.open = true;
        target.scrollIntoView({ block: 'start', behavior: 'smooth' });
        return;
      }
    }
    if (path) go(path, section);
  });
  inspectorBack.addEventListener('click', () => {
    const at = visited.pop();
    if (at) void showInspector(at.path, at);
  });
  inspectorRefresh.addEventListener('click', () => void showInspector());
  // Destructive actions take two clicks: the first arms the button for 6 s.
  const confirmable: [HTMLButtonElement, StringKey, string][] = [
    [rebuildButton, 'act.rebuild', 'primary'], [deleteButton, 'act.delete', 'danger'], [cutButton, 'act.cut', 'primary']];
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
  interface NotePart { kind: string; made: string; cached: boolean; held: number; reason: string; stale?: number; entries?: number; left_out?: number }
  interface NotesResult { text: string; chars: number; sections: NotePart[]; last_turn: number | null }
  const count = (n: number) => n.toLocaleString('en-US');
  /** Show or hide "read the cut turns again" with what the sidecar counted (PHASE-62 S3). */
  function showCut(info: CutInfo | null): void {
    cutInfo = info && info.turns + info.windows > 0 ? info : null;
    if (armed === cutButton) disarm();
    cutButton.style.display = cutInfo ? '' : 'none';
    cutSummariesLabel.style.display = cutInfo && cutInfo.windows > 0 ? '' : 'none';
    if (!cutInfo || cutInfo.windows === 0) cutSummaries.checked = false;
    if (cutInfo) cutSummariesText.textContent = ' ' + L('act.cut_summaries', { w: cutInfo.windows, low: count(cutInfo.slow), high: count(cutInfo.shigh) });
  }
  interface CutView { extract?: { turns?: number; input_tokens?: number[] }; summarize?: { windows?: number; input_tokens?: number[] } }
  /** Ask the sidecar what the action would read for this chat; an older sidecar has no such route and shows nothing. */
  async function loadCut(conversation: string): Promise<CutInfo | null> {
    let info: CutInfo | null = null;
    try {
      const r = await deps.api<CutView>('GET', `/v1/conversations/${conversation}/cut-turns`);
      const e = r.extract ?? {}, s = r.summarize ?? {};
      info = { turns: Number(e.turns) || 0, windows: Number(s.windows) || 0,
        low: Number(e.input_tokens?.[0]) || 0, high: Number(e.input_tokens?.[1]) || 0,
        slow: Number(s.input_tokens?.[0]) || 0, shigh: Number(s.input_tokens?.[1]) || 0 };
    } catch { info = null; }
    if (actionConversation === conversation) showCut(info);
    return cutInfo;
  }
  cutButton.addEventListener('click', async () => {
    const conversation = actionConversation;
    const info = cutInfo;
    if (!conversation || !info) return;
    const both = cutSummaries.checked && info.windows > 0;
    if (armed !== cutButton) {  // two clicks: each turn is a model call, so the first says what it would read
      disarm();
      armed = cutButton;
      cutButton.textContent = both
        ? L('act.cut_confirm_sum', { n: info.turns, w: info.windows, low: count(info.low + info.slow), high: count(info.high + info.shigh) })
        : L('act.cut_confirm', { n: info.turns, low: count(info.low), high: count(info.high) });
      cutButton.className = 'primary';
      armTimer = window.setTimeout(disarm, 6000);
      return;
    }
    disarm();
    cutButton.disabled = true;
    say(actionMsg, L('act.working'));
    try {
      const r = await deps.api<{ queued: { extract?: number; summarize?: number } }>('POST',
        `/v1/conversations/${conversation}/read-cut`, { summaries: both }, 30_000);
      const t = r.queued.extract ?? 0, s = r.queued.summarize ?? 0;
      say(actionMsg, t + s ? L('act.cut_done', { t, s }) : L('act.history_none'), 'ok');
      if (t + s) deps.hud.background(conversation);
      await loadCut(conversation);
      await showInspector();
    } catch (error) { say(actionMsg, actionError(error), 'err'); } finally { cutButton.disabled = false; }
  });
  retryButton.addEventListener('click', async () => {
    const conversation = actionConversation;
    if (!conversation) return;
    disarm();
    retryButton.disabled = true;
    say(actionMsg, L('act.working'));
    try {
      const r = await deps.api<{ retried?: Record<string, number> }>('POST',
        `/v1/conversations/${conversation}/retry-failed`, {}, 30_000);
      const n = Object.values(r.retried ?? {}).reduce((a, b) => a + (Number(b) || 0), 0);
      say(actionMsg, n ? L('act.retry_done', { n }) : L('act.retry_none'), 'ok');
      if (n) deps.hud.background(conversation);
      await showInspector();
    } catch (error) { say(actionMsg, actionError(error), 'err'); } finally { retryButton.disabled = false; }
  });
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

  notesButton.addEventListener('click', () => {
    const conversation = actionConversation;
    if (!conversation) return;
    if (notesCard.style.display !== 'none') return void (notesCard.style.display = 'none');
    if (!notesCard.childElementCount) buildNotes(conversation);
    notesCard.style.display = '';
  });
  factAddButton.addEventListener('click', () => {
    const conversation = actionConversation;
    if (!conversation) return;
    if (factAddCard.style.display !== 'none') return void (factAddCard.style.display = 'none');
    factAddCard.style.display = '';
    void buildFactAdd(conversation);
  });
  /** Inline form for `fact_add`: pick a recent message, enter predicate/subject/object/value, and submit. */
  async function buildFactAdd(conversation: string): Promise<void> {
    interface MsgRow { host_logical_id: string; turn: number; position: number; role: string; name: string | null; preview: string }
    factAddCard.replaceChildren(el('b', { text: L('fa.title') }), el('p', { class: 'sub', text: L('act.working') }));
    let msgs: MsgRow[];
    try {
      msgs = await deps.api<MsgRow[]>('GET', `/v1/conversations/${conversation}/messages?limit=40`, undefined, 15_000);
    } catch (error) {
      factAddCard.replaceChildren(el('b', { text: L('fa.title') }), el('p', { class: 'msg err', text: errorText(lang, error) }));
      return;
    }
    if (!msgs.length) {
      factAddCard.replaceChildren(el('b', { text: L('fa.title') }), el('p', { class: 'sub', text: L('fa.no_msgs') }));
      return;
    }
    const preds: [string, string, string | null][] = [
      ['has_status', 'character', null], ['located_in', 'character', 'place'], ['identity', 'character', null],
      ['has_trait', 'character', null], ['relationship', 'character', 'character'], ['role_toward', 'character', 'character'],
      ['feels_toward', 'character', 'character'], ['addresses', 'character', 'character'], ['possesses', 'character', 'item'],
      ['member_of', 'character', 'group'], ['knows', 'character', null], ['goal', 'character', null],
      ['promised', 'character', 'character'], ['event', 'character', null], ['world_fact', 'concept', null],
    ];
    const msgSel = el('select', { 'aria-label': L('fa.msg') }, ...msgs.map((m) =>
      el('option', { value: m.host_logical_id, text: `t${m.turn} #${m.position} (${m.name || m.role}) ${m.preview.slice(0, 48)}` })));
    const predSel = el('select', { 'aria-label': L('fa.pred') }, ...preds.map(([p]) => el('option', { value: p, text: p })));
    const subj = el('input', { type: 'text', placeholder: L('fa.subj'), 'aria-label': L('fa.subj') });
    const obj = el('input', { type: 'text', placeholder: L('fa.obj'), 'aria-label': L('fa.obj') });
    const val = el('input', { type: 'text', placeholder: L('fa.val'), 'aria-label': L('fa.val') });
    const hid = el('input', { type: 'text', placeholder: L('fa.hidden'), 'aria-label': L('fa.hidden') });
    const save = el('button', { class: 'primary', text: L('save') });
    const cancel = el('button', { text: L('cancel') });
    const formMsg = el('div', { class: 'msg' });
    cancel.addEventListener('click', () => { factAddCard.style.display = 'none'; });
    save.addEventListener('click', async () => {
      const s = subj.value.trim();
      if (!s) return void say(formMsg, L('fa.need_subj'), 'err');
      const spec = preds.find(([p]) => p === predSel.value) ?? preds[0]!;
      const o = obj.value.trim() || null;
      const v = val.value.trim() || null;
      const hidden = hid.value.split(',').map((x) => x.trim()).filter(Boolean);
      const fact: Record<string, unknown> = {
        predicate: spec[0], subject: s, subject_type: spec[1],
        ...(o ? { object: o, object_type: spec[2] ?? 'character' } : {}),
        ...(v ? { value: v } : {}),
        ...(hidden.length ? { hidden_from: hidden } : {}),
      };
      save.disabled = true;
      say(formMsg, L('act.working'));
      try {
        await deps.api('POST', `/v1/conversations/${conversation}/repairs`,
          { kind: 'fact_add', item: msgSel.value, fact }, 15_000);
        factAddCard.replaceChildren();
        factAddCard.style.display = 'none';
        say(actionMsg, L('rp.done'), 'ok');
        await showInspector();
      } catch (error) {
        say(formMsg, errorText(lang, error), 'err');
        save.disabled = false;
      }
    });
    factAddCard.replaceChildren(el('b', { text: L('fa.title') }),
      el('div', { class: 'row' }, msgSel), el('div', { class: 'row' }, predSel),
      el('div', { class: 'row' }, subj, obj), el('div', { class: 'row' }, val, hid),
      el('div', { class: 'btns' }, save, cancel), formMsg);
  }
  const notesCache = new Map<string, NotesResult>();
  let notesElapsedTimer: ReturnType<typeof setInterval> | null = null;
  function clearNotesTimer(): void {
    if (notesElapsedTimer !== null) { clearInterval(notesElapsedTimer); notesElapsedTimer = null; }
  }
  /** The form: which sections, the chronicle's length, whether secrets go in (PHASE-50 S1, PHASE-59 Studio). */
  function buildNotes(conversation: string, target: HTMLElement = notesCard, studio = false): void {
    notesFor = conversation;
    clearNotesTimer();
    interface OptSpec {
      key: StringKey; kind: string; on: boolean; desc: StringKey;
      badge: StringKey; badgeCls: string; calls: number;
    }
    const specs: OptSpec[] = [
      { key: 'notes.diverged', kind: 'diverged', on: true, desc: 'notes.desc_diverged', badge: 'notes.badge_llm', badgeCls: 'b-llm', calls: 1 },
      { key: 'notes.chronicle', kind: 'chronicle', on: false, desc: 'notes.desc_chronicle', badge: 'notes.badge_llm', badgeCls: 'b-llm', calls: 1 },
      { key: 'notes.address', kind: 'address', on: false, desc: 'notes.desc_address', badge: 'notes.badge_free', badgeCls: 'b-free', calls: 0 },
      { key: 'notes.custom', kind: 'custom', on: false, desc: 'notes.desc_custom', badge: 'notes.badge_unchecked', badgeCls: 'b-warn', calls: 1 },
    ];
    const estBar = el('div', { class: 'notes-est' });
    const kinds = specs.map((s) => {
      const box = el('input', { type: 'checkbox', value: s.kind });
      box.checked = s.on;
      if (!studio) {
        return { box, calls: s.calls, row: el('div', { class: 'check' }, box, el('span', { text: L(s.key) })) };
      }
      const card = el('label', { class: `note-opt${s.on ? ' on' : ''}` },
        box,
        el('div', { class: 'note-opt-body' },
          el('div', { class: 'note-opt-top' },
            el('span', { class: 'note-opt-title', text: L(s.key) }),
            el('span', { class: `badge ${s.badgeCls}`, text: L(s.badge) })),
          el('div', { class: 'note-opt-desc', text: L(s.desc) })));
      box.addEventListener('change', () => {
        card.classList.toggle('on', box.checked);
        updateEst();
      });
      return { box, calls: s.calls, row: card };
    });
    const updateEst = () => {
      const calls = kinds.reduce((sum, k) => sum + (k.box.checked ? k.calls : 0), 0);
      estBar.replaceChildren(icon(calls > 0 ? 'sparkles' : 'check', 14),
        el('span', { text: calls > 0 ? L('notes.calls_est', { n: calls }) : L('notes.calls_free') }));
    };
    if (studio) updateEst();
    // PHASE-56: the owner's prompt, one for every chat (the sidecar keeps it), and whether the setting goes in.
    const custom = kinds[3]!.box;
    const prompt = el('textarea', { rows: 6, maxlength: String(PROMPT_MAX), spellcheck: 'false',
      style: 'font-family:inherit', 'aria-label': L('notes.custom_prompt'), placeholder: L('notes.custom_placeholder') });
    const count = el('p', { class: 'sub' });
    const counted = () => { count.textContent = L('notes.custom_count', { n: prompt.value.trim().length, max: PROMPT_MAX }); };
    prompt.addEventListener('input', counted);
    counted();
    // Studio prompt presets (#7): 3 built-in starters + locally saved custom presets.
    const presetRow = el('div', { class: 'note-presets' });
    let userPresets: NotePreset[] = studio ? loadNotePresets() : [];
    const builtInPresets: NotePreset[] = studio ? [
      { name: L('notes.preset_feelings'), prompt: L('notes.preset_feelings_body') },
      { name: L('notes.preset_threads'), prompt: L('notes.preset_threads_body') },
      { name: L('notes.preset_npcs'), prompt: L('notes.preset_npcs_body') },
    ] : [];
    const renderPresets = () => {
      if (!studio) return;
      const all = [...builtInPresets, ...userPresets];
      const cur = prompt.value.trim();
      const chips = all.map((p) => {
        const b = el('button', { type: 'button', class: `filter-chip${cur === p.prompt ? ' on' : ''}`, text: p.name });
        b.addEventListener('click', () => {
          prompt.value = p.prompt;
          counted();
          renderPresets();
        });
        return b;
      });
      const savePreset = el('button', { type: 'button', class: 'mini ghost', text: `+ ${L('notes.preset_save')}` });
      savePreset.addEventListener('click', () => {
        const bodyText = prompt.value.trim();
        if (!bodyText) return;
        const firstLine = bodyText.split('\n')[0]!.trim().slice(0, 18) || 'Preset';
        userPresets = [{ name: firstLine, prompt: bodyText }, ...userPresets.filter((p) => p.prompt !== bodyText)].slice(0, 6);
        saveNotePresets(userPresets);
        renderPresets();
      });
      presetRow.replaceChildren(el('span', { class: 'muted', style: 'font-size:12px', text: `${L('notes.presets_label')}:` }),
        ...chips, savePreset);
    };
    if (studio) {
      prompt.addEventListener('input', renderPresets);
      renderPresets();
    }
    const setting = el('input', { type: 'checkbox' });
    const customArea = el('div', { style: 'display:none;margin:8px 0 12px' },
      ...(studio ? [presetRow] : []), prompt, count,
      el('div', { class: 'check' }, setting, el('span', { text: L('notes.custom_setting') })),
      el('p', { class: 'sub', text: L('notes.custom_setting_sub') }),
      el('p', { class: 'sub', text: L('notes.custom_unchecked') }));
    custom.addEventListener('change', () => { customArea.style.display = custom.checked ? '' : 'none'; });
    let saved = '';
    void deps.api<{ prompt?: string }>('GET', '/v1/notes/prompt', undefined, 15_000).then((r) => {
      saved = typeof r?.prompt === 'string' ? r.prompt : '';
      if (!prompt.value) { prompt.value = saved; counted(); renderPresets(); }
    }).catch(() => {}); // an older sidecar has no prompt: the box starts empty
    const length = el('select', { 'aria-label': L('notes.length') },
      el('option', { value: '3000', text: L('notes.short') }), el('option', { value: '6000', text: L('notes.long') }));
    // What a model writes the note's parts in (`notes.LANGUAGES`): the chat's own language, or English.
    const language = el('select', { 'aria-label': L('notes.language') },
      el('option', { value: 'chat', text: L('notes.lang_chat') }), el('option', { value: 'en', text: L('notes.lang_en') }));
    const secrets = el('input', { type: 'checkbox' });
    const warn = el('p', { class: 'sub warn', text: L('notes.secrets_warn'), style: 'display:none' });
    secrets.addEventListener('change', () => { warn.style.display = secrets.checked ? '' : 'none'; });
    const make = el('button', { class: 'primary' }, ...(studio ? [icon('sparkles', 15)] : []), L('notes.make'));
    const cancelBtn = el('button', { class: 'danger mini', style: 'display:none', text: L('notes.cancel', { s: 0 }) });
    const msg = el('div', { class: 'msg' });
    const cached = studio ? notesCache.get(conversation) : undefined;
    const results = el('div', {}, ...(cached
      ? [el('p', { class: 'sub', text: L('notes.cached_hint') }), noteResult(cached, msg, studio)]
      : studio ? [el('div', { class: 'studio-empty', text: L('notes.empty_hint') })] : []));
    let runSeq = 0;
    cancelBtn.addEventListener('click', () => {
      runSeq += 1;
      clearNotesTimer();
      make.disabled = false;
      cancelBtn.style.display = 'none';
      say(msg, L('notes.cancelled'), 'muted');
      const prev = studio ? notesCache.get(conversation) : undefined;
      results.replaceChildren(...(prev
        ? [el('p', { class: 'sub', text: L('notes.cached_hint') }), noteResult(prev, msg, studio)]
        : studio ? [el('div', { class: 'studio-empty', text: L('notes.empty_hint') })] : []));
    });
    make.addEventListener('click', async () => {
      const sections = kinds.filter((k) => k.box.checked).map((k) => k.box.value);
      if (!sections.length) return say(msg, L('notes.pick'), 'warn');
      const text = prompt.value.trim();
      if (custom.checked && !text) return say(msg, L('notes.custom_empty'), 'warn');
      const myRun = ++runSeq;
      let elapsed = 0;
      make.disabled = true;
      say(msg, L('act.working'));
      const waitBox = el('div', { class: 'studio-empty', text: studio ? L('notes.working_sec', { s: 0 }) : L('act.working') });
      results.replaceChildren(...(studio ? [waitBox] : []));
      if (studio) {
        cancelBtn.textContent = L('notes.cancel', { s: 0 });
        cancelBtn.style.display = '';
        clearNotesTimer();
        notesElapsedTimer = setInterval(() => {
          if (myRun !== runSeq) return clearNotesTimer();
          elapsed += 1;
          waitBox.textContent = L('notes.working_sec', { s: elapsed });
          cancelBtn.textContent = L('notes.cancel', { s: elapsed });
        }, 1000);
      }
      let unsaved = false;
      if (custom.checked && text !== saved) {
        try {
          await deps.api('PUT', '/v1/notes/prompt', { prompt: text }, 15_000);
          saved = text;
        } catch { unsaved = true; } // the note is still made from the box (C2)
      }
      // `language` only when not the sidecar's default (`chat`): the body is then the one an older sidecar was sent.
      // Whether a sidecar reads it is not reported (no `/v1/health` feature): an older one writes in the chat's language.
      const body: Record<string, unknown> = { sections, chars: Number(length.value), secrets: secrets.checked,
        ...(language.value !== 'chat' ? { language: language.value } : {}) };
      if (custom.checked) Object.assign(body, { custom_prompt: text, custom_setting: setting.checked });
      try {
        const r = await deps.api<NotesResult>('POST', `/v1/conversations/${conversation}/notes`,
          body, 900_000); // up to three model parts, each with a retry
        if (notesFor !== conversation || myRun !== runSeq) return;
        notesCache.set(conversation, r);
        results.replaceChildren(noteResult(r, msg, studio));
        const done = r.text ? L('notes.done') : L('notes.part_none', { part: L('notes.title') });
        say(msg, unsaved ? `${done} ${L('notes.custom_unsaved')}` : done, r.text && !unsaved ? 'ok' : 'warn');
      } catch (error) {
        if (myRun !== runSeq) return;
        say(msg, errorText(lang, error), 'err');
      } finally {
        if (myRun === runSeq) {
          clearNotesTimer();
          make.disabled = false;
          cancelBtn.style.display = 'none';
        }
      }
    });
    if (!studio) {
      target.replaceChildren(el('h2', { text: L('notes.title') }), el('p', { class: 'sub', text: L('notes.sub') }),
        ...kinds.map((k) => k.row), customArea,
        el('div', { class: 'row' }, field(L('notes.length'), length), field(L('notes.language'), language)),
        el('div', { class: 'check' }, secrets, el('span', { text: L('notes.secrets') })), warn,
        el('div', { class: 'btns' }, make), msg, results);
      return;
    }
    const leftCol = el('div', { class: 'studio-col' },
      el('h3', { text: L('notes.config_head') }),
      ...kinds.map((k) => k.row), customArea,
      el('div', { class: 'row' }, field(L('notes.length'), length), field(L('notes.language'), language)),
      el('div', { class: 'check' }, secrets, el('span', { text: L('notes.secrets') })), warn,
      estBar, el('div', { class: 'btns' }, make, cancelBtn), msg);
    const rightCol = el('div', { class: 'studio-col' },
      el('h3', { text: L('notes.preview_head') }), results);
    target.replaceChildren(
      el('div', { class: 'studio-head' }, el('h2', { text: L('notes.title') }), el('p', { class: 'sub', text: L('notes.studio_sub') })),
      el('div', { class: 'notes-studio' }, leftCol, rightCol));
  }
  /** The note: how each part was made, the one text in a box, and Copy (PHASE-50 S6, amendment 2). */
  function noteResult(r: NotesResult, msg: HTMLElement, studio = false): HTMLElement {
    const how = (p: NotePart): string => {
      const part = L(`notes.part.${p.kind}` as StringKey);
      if (p.reason === 'no_scenes') return L('notes.part_no_scenes', { part });
      if (p.reason === 'none') return L('notes.part_none', { part });
      // PHASE-56: the custom part has no fallback; it is left out and says why
      if (p.reason === 'no_model' || p.reason === 'failed' || p.reason === 'held') {
        return L(`notes.part_${p.reason}` as StringKey, { part });
      }
      const bits = [L(`notes.made_${p.made}` as StringKey)];
      if (p.cached) bits.push(L('notes.cached'));
      if (p.held) bits.push(L('notes.held', { n: p.held }));
      if (p.entries !== undefined) bits.push(L('notes.entries', { n: p.entries, m: p.left_out ?? 0 }));
      if (p.kind === 'custom') bits.push(L('notes.unchecked'));
      return L('notes.part_made', { part, how: bits.join(', ') });
    };
    // the chronicle and the custom part read the same threads: the same stale ones, counted once (PHASE-56)
    const stale = r.sections.reduce((n, p) => Math.max(n, p.stale ?? 0), 0);
    const about = el('ul', { class: 'sub' }, ...r.sections.map((p) => el('li', { text: how(p) })),
      ...(stale ? [el('li', { text: L('notes.stale', { n: stale }) })] : []));
    if (!r.text) return el('div', {}, about);
    // Korean names in it read badly in monospace (the owner's design rules): the box keeps the panel's font.
    const box = el('textarea', { readonly: true, rows: 14, spellcheck: 'false', style: 'font-family:inherit',
      'aria-label': L('notes.result') });
    box.value = r.text;
    const copy = el('button', { class: 'primary' }, icon('copy', 15), L('notes.copy'));
    copy.addEventListener('click', async () => {
      const copied = await copyText(box, navigator.clipboard);
      say(msg, L(copied ? 'notes.copied' : 'notes.copy_hint'), copied ? 'ok' : 'warn');
    });
    const secButtons: HTMLElement[] = [];
    if (studio) {
      const sections = splitNoteSections(r.text);
      if (sections.length > 1) {
        for (const sec of sections) {
          const sb = el('button', { type: 'button', class: 'mini', title: L('notes.copy_section') },
            icon('copy', 13), sec.title);
          sb.addEventListener('click', async () => {
            const temp = el('textarea', { readonly: true });
            temp.value = sec.body;
            const copied = await copyText(temp, navigator.clipboard);
            say(msg, copied ? L('notes.section_copied', { title: sec.title }) : L('notes.copy_hint'), copied ? 'ok' : 'warn');
          });
          secButtons.push(sb);
        }
      }
    }
    return el('div', {}, el('h2', { text: L('notes.result') }), about,
      el('p', { class: 'sub', text: L('notes.chars', { n: r.chars }) }),
      ...(secButtons.length ? [el('div', { class: 'note-sec-row' }, ...secButtons)] : []),
      box, el('div', { class: 'btns' }, copy));
  }
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
  const token = el('input', { type: 'password', placeholder: L('conn.token_placeholder'), autocomplete: 'off' });
  let install: string | null = null;  // what the sidecar says it is (`bundle`): the Ollama preset's address
  settingsView.append(el('div', { class: 'card' },
    el('h2', { text: L('conn.title') }), el('p', { class: 'sub', text: L('conn.sub') }),
    field(L('conn.url'), url), field(L('conn.token'), token),
    el('div', { class: 'row' }, field(L('conn.route'), route), field(L('conn.budget'), reserved), field(L('conn.deadline'), deadline)),
    el('div', { class: 'check' }, enabled, el('span', { text: L('conn.enabled') })),
    el('p', { class: 'sub', text: L('conn.hint') }), el('p', { class: 'sub', text: L('conn.deadline_hint') })));

  function modelSection(kind: 'llm' | 'embeddings', title: StringKey, sub: StringKey, presets: Preset[],
    onPreset?: (p: Preset) => void, extra?: { nodes: Node[]; test(): Record<string, unknown> | null }) {
    const preset = el('select', {}, ...presets.map((p, i) => el('option', { value: String(i),
      text: p.label.includes('.') ? L(p.label as StringKey) : p.label })));
    const endpoint = el('input', { placeholder: 'https://…/v1', spellcheck: 'false' });
    const model = el('input', { placeholder: L(kind === 'llm' ? 'model.llm_placeholder' : 'model.emb_placeholder'), spellcheck: 'false' });
    const list = el('select', { style: 'display:none' });
    const key = el('input', { type: 'password', placeholder: L('model.key_placeholder'), autocomplete: 'off' });
    const msg = el('div', { class: 'msg' });
    const load = el('button', { text: L('model.load') });
    const test = el('button', { text: L('model.test') });
    // Vertex only (ADR 0022 amendment 1): pick the service-account key file instead of pasting it. LLM section only,
    // since the sidecar refuses a JSON key for embeddings.
    const keyFile = el('input', { type: 'file', accept: '.json,application/json', style: 'display:none' });
    const pickKey = el('button', { text: L('model.key_file'), style: 'display:none' });
    const syncPickKey = () => {
      pickKey.style.display = kind === 'llm' && isVertexEndpoint(endpoint.value) ? '' : 'none';
    };
    pickKey.addEventListener('click', () => keyFile.click());
    keyFile.addEventListener('change', async () => {
      const file = keyFile.files?.[0];
      keyFile.value = '';  // picking the same file again fires `change` again
      if (!file) return;
      let text: string;
      try { text = (await file.text()).trim(); } catch (error) { return say(msg, errorText(lang, error), 'err'); }
      const project = serviceAccountProject(text);
      if (!project) return say(msg, L('model.key_file_bad'), 'err');
      const vertexModel = presets.find((p) => p.url === VERTEX_URL)?.model;
      key.value = text;
      endpoint.value = endpointForKey(endpoint.value, text);
      preset.value = String(presetIndex(presets, endpoint.value));
      if (!model.value.trim().startsWith('google/') && vertexModel) model.value = vertexModel;
      update();
      say(msg, L('model.key_file_ok', { project }), 'ok');
      load.click();  // the file is all a Vertex user needs to give: list the models right away
    });
    preset.addEventListener('change', () => {
      const p = presets[Number(preset.value)] as Preset;
      if (p.url !== 'custom') endpoint.value = fillProject(presetUrl(p.url, install), key.value);
      if (p.model) model.value = p.model;
      if (!p.url) model.value = '';
      say(msg, p.hint ? L(p.hint) : p.url.includes('{project}') ? L('model.vertex_hint') : '');
      onPreset?.(p);
      syncPickKey();
      update();
    });
    endpoint.addEventListener('input', syncPickKey);
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
      const more = extra ? extra.test() : {};  // what the requests carry, as in the form (PHASE-61 S4)
      if (!more) return say(msg, L('extra.invalid'), 'err');
      test.disabled = true;
      say(msg, L('model.testing'));
      try {
        const r = await deps.api<{ ok: boolean; ms: number; dimensions?: number; error?: string }>('POST', '/v1/config/test',
          { kind, url: endpoint.value.trim(), model: model.value.trim(), api_key: key.value.trim() || undefined, ...more });
        say(msg, r.ok ? L('model.test_ok', { ms: r.ms }) + (r.dimensions ? L('model.dims', { n: r.dimensions }) : '')
          : L('model.test_failed', { e: r.error ?? '' }), r.ok ? 'ok' : 'err');
      } catch (error) { say(msg, errorText(lang, error), 'err'); } finally { test.disabled = false; }
    });
    settingsView.append(el('div', { class: 'card' },
      el('h2', { text: L(title) }), el('p', { class: 'sub', text: L(sub) }),
      field(L('model.provider'), preset), field(L('model.endpoint'), endpoint),
      field(L('model.model'), model), list, field(L('model.key'), key), ...(extra?.nodes ?? []),
      el('div', { class: 'btns' }, pickKey, load, test), keyFile, msg));
    return {
      values: () => ({ url: endpoint.value, model: model.value, key: key.value }),
      fill(cfg: { url: string; model: string; api_key_set: boolean }) {
        preset.value = String(presetIndex(presets, cfg.url));
        endpoint.value = cfg.url;
        model.value = cfg.model;
        key.value = '';
        key.placeholder = L(cfg.api_key_set ? 'model.key_saved' : 'model.key_placeholder');
        syncPickKey();
      },
    };
  }
  // What the extraction model's requests carry (PHASE-61 S4, ADR 0088): one stored body, and the effort dropdown as a
  // view of it; hidden when the sidecar does not report `llm.extra_body`.
  let extraKnown = false;
  const extraText = el('textarea', { rows: 4, spellcheck: 'false', placeholder: '{}', style: 'min-height:96px',
    'aria-label': L('extra.body') });
  const extraErr = el('div', { class: 'msg err', text: L('extra.invalid'), style: 'display:none' });
  const effortCustom = el('option', { value: 'custom', text: L('extra.custom') });  // in the list only while custom
  const effort = el('select', { 'aria-label': L('extra.effort') }, el('option', { value: '', text: '—' }),
    ...EFFORTS.map((e) => el('option', { value: e, text: e })));
  const effortRow = el('div', {}, field(L('extra.effort'), effort), el('p', { class: 'sub', text: L('extra.effort_sub') }));
  const noTemp = el('input', { type: 'checkbox' });
  const extraBox = el('div', { style: 'display:none' }, field(L('extra.body'), extraText), extraErr,
    el('p', { class: 'sub', text: L('extra.body_sub') }), effortRow,
    el('div', { class: 'check' }, noTemp, el('span', { text: L('extra.no_temp') })),
    el('p', { class: 'sub', text: L('extra.no_temp_sub') }));
  // On `input` too: a browser fires it before `change`, and the settings view's own `input` listener runs `update`,
  // whose `syncExtra` would set the dropdown back from the text before `change` ever saw the choice.
  const writeEffort = (): void => {
    if (effort.value !== 'custom') extraText.value = withEffort(extraText.value, effort.value || null);
  };
  effort.addEventListener('input', writeEffort);
  effort.addEventListener('change', writeEffort);
  /** The dropdown follows the text and the address; called from `update`, since loads and presets set them without an event. */
  function syncExtra(): void {
    extraBox.style.display = extraKnown ? '' : 'none';
    effortRow.style.display = isOpenRouter(llm.values().url) ? '' : 'none';
    const s = effortOf(extraText.value);
    if (s.state === 'custom') effort.append(effortCustom); else effortCustom.remove();
    effort.value = s.state === 'value' ? s.effort : s.state === 'custom' ? 'custom' : '';
    effort.disabled = s.state === 'invalid';
    extraErr.style.display = s.state === 'invalid' ? '' : 'none';
  }
  const extraValues = () => (extraKnown ? { extra: extraText.value, noTemp: noTemp.checked } : {});
  const llm = modelSection('llm', 'llm.title', 'llm.sub', LLM_PRESETS, undefined, { nodes: [extraBox], test: () => {
    if (!extraKnown) return {};
    const body = bodyOf(extraText.value);
    return body && { extra_body: body, no_temperature: noTemp.checked };
  } });
  // Similarity scores differ by embedding model, so a preset measured with its own bar brings it (AGE-40).
  const emb = modelSection('embeddings', 'emb.title', 'emb.sub', EMBED_PRESETS,
    (p) => { if (p.minSim !== undefined) minSim.value = String(p.minSim); });

  // Optional reranker (PHASE-60 S5, ADR 0084): hidden when the sidecar does not report `rerank`; no test action,
  // and `rerank_format` (only `standard`) is neither shown nor sent.
  let rerankKnown = false;
  const rerankUrl = el('input', { placeholder: 'https://…/v1', spellcheck: 'false' });
  const rerankModel = el('input', { placeholder: L('rerank.model_placeholder'), spellcheck: 'false' });
  const rerankKey = el('input', { type: 'password', placeholder: L('model.key_placeholder'), autocomplete: 'off' });
  const rerankTimeout = el('input', { type: 'number', min: MIN_RERANK_TIMEOUT_MS, max: MAX_RERANK_TIMEOUT_MS, step: 50 });
  const rerankDot = el('span', { class: 'dot' });
  const rerankStateText = el('span', { text: L('rerank.off') });
  const rerankState = el('div', { class: 'line muted' }, rerankDot, rerankStateText);
  const rerankCard = el('div', { class: 'card', style: 'display:none' },
    el('h2', { text: L('rerank.title') }),
    rerankState,
    el('p', { class: 'sub', text: L('rerank.sub') }),
    field(L('rerank.url'), rerankUrl),
    field(L('model.model'), rerankModel),
    field(L('model.key'), rerankKey),
    field(L('rerank.timeout'), rerankTimeout));
  settingsView.append(rerankCard);
  const rerank = {
    values: () => ({ url: rerankUrl.value, model: rerankModel.value, key: rerankKey.value, timeout: rerankTimeout.value }),
    fill(cfg: ServerConfig['rerank']): void {
      rerankKnown = Boolean(cfg);
      if (cfg) {
        rerankUrl.value = cfg.url;
        rerankModel.value = cfg.model;
        rerankKey.value = '';
        rerankKey.placeholder = L(cfg.key_set ? 'model.key_saved' : 'model.key_placeholder');
        rerankTimeout.value = String(cfg.timeout_ms);
        rerankState.className = cfg.configured ? 'line ok' : 'line muted';
        rerankDot.className = cfg.configured ? 'dot ok' : 'dot';
        rerankStateText.textContent = L(cfg.configured ? 'rerank.on' : 'rerank.off');
      } else {
        rerankUrl.value = '';
        rerankModel.value = '';
        rerankKey.value = '';
        rerankKey.placeholder = L('model.key_placeholder');
        rerankTimeout.value = '';
        rerankState.className = 'line muted';
        rerankDot.className = 'dot';
        rerankStateText.textContent = L('rerank.off');
      }
      rerankCard.style.display = rerankKnown && (!viewsOn || currentGroup === 'models') ? '' : 'none';
    },
  };

  const threshold = el('input', { type: 'number', step: 0.05, min: 0.05, max: 1 });
  const minSim = el('input', { type: 'number', step: 0.01, min: 0, max: 1 });
  const embedWait = el('input', { type: 'number', step: 100, min: 100, max: 5000 });  // NMOS_EMBED_TIMEOUT_MS (K34)
  const topK = el('input', { type: 'number', min: 0, max: 20 });
  const factsLimit = el('input', { type: 'number', min: 0, max: 30 });
  const backfill = el('input', { type: 'number', min: 0, max: 5000 });
  const summaries = el('input', { type: 'checkbox' });  // scene summaries and the story so far (ADR 0042, 0043)
  const canonFacts = el('input', { type: 'checkbox' });  // facts read from the canon (ADR 0047)
  const pinAt = el('input', { type: 'checkbox', disabled: true });  // @name in a message pins a character for that reply (ADR 0087)
  let pinAtKnown = false;  // the sidecar reported the setting: an older one refuses the key
  // Extract a reply about 20 s after it instead of when it is answered (PHASE-67): the plugin syncs after a reply only then.
  const extractOnOutput = el('input', { type: 'checkbox', disabled: true });
  let extractOnOutputKnown = false;  // likewise
  // Chunks embedded per message (ADR 0062): how much of a long message semantic search reaches, beside extraction's cap.
  const embedChunks = el('input', { type: 'number', min: MIN_EMBED_MAX_CHUNKS, max: MAX_EMBED_MAX_CHUNKS, step: 1,
    disabled: true });
  let embedChunksKnown = false;  // likewise: a sidecar that does not report it keeps it in NMOS_EMBED_MAX_CHUNKS
  const embedChunksHint = el('p', { class: 'sub' });
  const showEmbedChunks = (): void => {
    const chars = embedChunkChars(embedChunks.value);
    embedChunksHint.textContent = !embedChunksKnown ? L('tune.embed_chunks_fixed')
      : chars === null ? L('tune.embed_chunks_range', { min: MIN_EMBED_MAX_CHUNKS, max: MAX_EMBED_MAX_CHUNKS })
        : L('tune.embed_chunks_hint', { n: embedChunks.value.trim(), chars: chars.toLocaleString('en-US'),
          d: DEFAULT_EMBED_MAX_CHUNKS, dchars: (DEFAULT_EMBED_MAX_CHUNKS * EMBED_CHUNK_CHARS).toLocaleString('en-US') });
  };
  embedChunks.addEventListener('input', showEmbedChunks);
  showEmbedChunks();
  settingsView.append(el('div', { class: 'card' },
    el('h2', { text: L('tune.title') }), el('p', { class: 'sub', text: L('tune.sub') }),
    el('div', { class: 'row' }, field(L('tune.threshold'), threshold), field(L('tune.min_sim'), minSim),
      field(L('tune.embed_wait'), embedWait)),
    el('p', { class: 'sub', text: L('tune.embed_wait_hint') }),
    el('div', { class: 'row' }, field(L('tune.embed_chunks'), embedChunks)), embedChunksHint,
    el('div', { class: 'row' }, field(L('tune.top_k'), topK), field(L('tune.facts'), factsLimit), field(L('tune.backfill'), backfill)),
    el('div', { class: 'check' }, summaries, el('span', { text: L('tune.summaries') })),
    el('p', { class: 'sub', text: L('tune.summaries_hint') }),
    el('div', { class: 'check' }, canonFacts, el('span', { text: L('tune.canon_facts') })),
    el('p', { class: 'sub', text: L('tune.canon_facts_hint') }),
    el('div', { class: 'check' }, extractOnOutput, el('span', { text: L('tune.extract_on_output') })),
    el('p', { class: 'sub', text: L('tune.extract_on_output_hint') }),
    el('div', { class: 'check' }, pinAt, el('span', { text: L('tune.pin_at') })),
    el('p', { class: 'sub', text: L('tune.pin_at_hint') })));

  // Leaving out old dialogue (PHASE-60 S1, ADR 0083): two plugin args, saved on their own, never in the sidecar update.
  const trimOn = el('input', { type: 'checkbox' });
  const trimKeep = el('input', { type: 'number', min: MIN_KEEP_RECENT_TURNS, max: MAX_KEEP_RECENT_TURNS, step: 1 });
  trimKeep.value = String(DEFAULT_KEEP_RECENT_TURNS);
  // Without summaries the sidecar never moves the cut (`no_summaries`): said while both boxes say so, in words.
  const trimWarn = el('div', { class: 'warn', text: L('trimset.needs_summaries'), style: 'display:none' });
  const syncTrimWarn = (): void => { trimWarn.style.display = trimOn.checked && !summaries.checked ? '' : 'none'; };
  settingsView.append(el('div', { class: 'card' },
    el('h2', { text: L('trimset.title') }), el('p', { class: 'sub', text: L('trimset.sub') }),
    el('div', { class: 'check' }, trimOn, el('span', { text: L('trimset.on') })),
    field(L('trimset.keep'), trimKeep), trimWarn));

  // Status drafts have their own Apply; the general Save never reads or resets these controls.
  const rules = el('textarea', { id: 'nmos-parser-draft', spellcheck: 'false', 'aria-label': L('rules.draft'),
    placeholder: L('rules.none') });
  const parserTarget = el('input', { id: 'nmos-parser-target', list: 'nmos-parser-cards',
    'aria-label': L('rules.target'), placeholder: L('rules.choose_target') });
  const parserCards = el('datalist', { id: 'nmos-parser-cards' });
  const parserActive = el('div', { id: 'nmos-parser-active', class: 'sub', style: 'white-space:pre-line' });
  const parserStored = el('pre', {});
  const parserPreview = el('p', { id: 'nmos-parser-preview', class: 'sub' });
  const parserMessage = el('div', { class: 'msg', role: 'status' });
  const parserApply = el('button', { id: 'nmos-parser-apply', text: L('rules.apply') });
  const parserClear = el('button', { text: L('rules.prepare_disable') });
  const parserFile = el('input', { id: 'nmos-parser-file', type: 'file', accept: '.json,application/json', style: 'display:none' });
  const parserPick = el('button', { text: L('rules.import') });
  const parserPreset = el('select', { id: 'nmos-parser-preset', 'aria-label': L('rules.preset') });
  const parserName = el('input', { id: 'nmos-parser-name', 'aria-label': L('rules.preset_name') });
  const parserSavePreset = el('button', { id: 'nmos-parser-save-preset', text: L('rules.save_preset') });
  const parserRemovePreset = el('button', { id: 'nmos-parser-remove-preset', text: L('rules.remove_preset') });
  const example = el('button', { text: L('rules.example') });
  let parserSupported = false;
  let parserBusy = false;
  let parserPresets: ParserPreset[] = [];
  let appliedDraft = '';
  let appliedTarget = '';
  const knownCards = new Set<string>();
  const parserDirty = () => rules.value !== appliedDraft || parserTarget.value !== appliedTarget;

  function updateParser(): void {
    const parsed = parserDraft(rules.value);
    const target = parserTarget.value.trim();
    parserApply.disabled = parserBusy || !parserSupported || !target || !parsed.ok;
    parserApply.textContent = L(parsed.ok && parsed.rules.length === 0 ? 'rules.disable' : 'rules.apply');
    parserSavePreset.disabled = parserBusy || !parserSupported || !parserName.value.trim() || !parsed.ok;
    parserRemovePreset.disabled = parserBusy || !parserSupported || !parserPreset.value;
    parserPreview.textContent = !target ? L('rules.choose_target') : !parsed.ok
      ? L(parsed.error === 'blank' ? 'rules.blank' : parsed.error === 'json' ? 'rules.invalid_json' : 'rules.invalid_shape')
      : L('rules.preview', { card: target, n: parsed.rules.length });
    syncDirtyDots();
  }

  function fillParsers(cfg: ServerConfig): void {
    parserSupported = cfg.parsers.spec !== undefined && Array.isArray(cfg.parsers.presets);
    const spec = cfg.parsers.spec ?? cfg.parsers.rules;
    const bindings = parserBindings(spec);
    const notes = bindings.cards.map(({ name, count }) => L('rules.binding', { card: name, n: count }));
    if (bindings.unbound) notes.push(L('rules.unbound', { n: bindings.unbound }));
    if (!notes.length) notes.push(L('rules.no_active'));
    if (!parserSupported) notes.push(L('rules.upgrade'));
    notes.push(...cfg.parsers.errors);
    parserActive.textContent = notes.join('\n');
    parserStored.textContent = JSON.stringify(spec ?? { rules: [] }, null, 2);
    for (const { name } of bindings.cards) knownCards.add(name);
    parserCards.replaceChildren(...[...knownCards].sort().map((name) => el('option', { value: name })));
    parserPresets = cfg.parsers.presets ?? [];
    const selected = parserPreset.value;
    parserPreset.replaceChildren(el('option', { value: '', text: L('rules.choose_preset') }),
      ...parserPresets.map((p) => el('option', { value: p.name, text: p.name })));
    parserPreset.value = parserPresets.some((p) => p.name === selected) ? selected : '';
    updateParser();
  }

  parserPick.addEventListener('click', () => parserFile.click());
  parserFile.addEventListener('change', async () => {
    const file = parserFile.files?.[0];
    parserFile.value = '';
    if (!file) return;
    try {
      rules.value = await file.text();
      parserPreset.value = '';
      say(parserMessage, L('rules.loaded'));
      updateParser();
    } catch (error) { say(parserMessage, errorText(lang, error), 'err'); }
  });
  parserPreset.addEventListener('change', () => {
    const chosen = parserPresets.find((p) => p.name === parserPreset.value);
    if (chosen) { rules.value = JSON.stringify({ rules: chosen.rules }, null, 2); parserName.value = chosen.name; }
    updateParser();
  });
  for (const control of [rules, parserTarget, parserName]) control.addEventListener('input', updateParser);
  example.addEventListener('click', () => { rules.value = JSON.stringify(PARSER_EXAMPLE, null, 2); updateParser(); });
  parserClear.addEventListener('click', () => { rules.value = JSON.stringify({ rules: [] }, null, 2); updateParser(); });
  parserApply.addEventListener('click', async () => {
    const parsed = parserDraft(rules.value);
    const card = parserTarget.value.trim();
    if (parserBusy || !parserSupported || !card || !parsed.ok) return;
    const draft = rules.value;
    const target = parserTarget.value;
    parserBusy = true; updateParser();
    try {
      const cfg = await deps.api<ServerConfig>('PUT', '/v1/parsers/card', { card, rules: parsed.rules });
      fillParsers(cfg);
      appliedDraft = draft; appliedTarget = target;
      say(parserMessage, L('rules.applied', { card, n: parsed.rules.length }), 'ok');
    } catch (error) { say(parserMessage, errorText(lang, error), 'err'); }
    finally { parserBusy = false; updateParser(); }
  });
  async function savePresets(next: ParserPreset[], selected: string): Promise<void> {
    if (parserBusy || !parserSupported) return;
    parserBusy = true; updateParser();
    try {
      const cfg = await deps.api<ServerConfig>('PUT', '/v1/config', { parser_presets: next });
      fillParsers(cfg);
      parserPreset.value = selected;
      say(parserMessage, L('rules.preset_saved'), 'ok');
    } catch (error) { say(parserMessage, errorText(lang, error), 'err'); }
    finally { parserBusy = false; updateParser(); }
  }
  parserSavePreset.addEventListener('click', () => {
    const parsed = parserDraft(rules.value);
    const name = parserName.value.trim();
    if (!parsed.ok || !name) return;
    void savePresets([...parserPresets.filter((p) => p.name !== name), { name, rules: presetRules(parsed.rules) }], name);
  });
  parserRemovePreset.addEventListener('click', () => {
    const name = parserPreset.value;
    if (name) void savePresets(parserPresets.filter((p) => p.name !== name), '');
  });
  // PHASE-43 S3: a chat's status window is set up on its own Inspector page; here every card's rules, folded, and the
  // hand-written rules under advanced.
  settingsView.append(el('div', { class: 'card' },
    el('h2', { text: L('rules.title') }), el('p', { class: 'sub', text: L('rules.where') }),
    el('details', {}, el('summary', { text: L('rules.all_cards') }), parserActive,
      el('details', {}, el('summary', { text: L('rules.stored') }), parserStored)),
    el('details', {}, el('summary', { text: L('rules.advanced') }), el('p', { class: 'sub', text: L('rules.scope') }),
      field(L('rules.target'), parserTarget), parserCards,
      el('div', { class: 'btns' }, parserPick, example), parserFile,
      field(L('rules.preset'), parserPreset), field(L('rules.draft'), rules),
      el('p', { class: 'sub', text: L('rules.sub') }),
      field(L('rules.preset_name'), parserName), el('div', { class: 'btns' }, parserSavePreset, parserRemovePreset),
      parserPreview, el('div', { class: 'btns' }, parserApply, parserClear)), parserMessage));
  updateParser();

  // --- settings tab: export (applied at once; ADR 0050) ------------------------------------------
  const exportEmbeddings = el('input', { type: 'checkbox' });
  const exportAll = el('button', { text: L('exp.all') });
  const exportMsg = el('div', { class: 'msg' });
  exportAll.addEventListener('click', () => void exportTo(exportAll, exportMsg,
    `/v1/archive${exportEmbeddings.checked ? '?embeddings=true' : ''}`, 'all'));
  settingsView.append(el('div', { class: 'card', id: 'nmos-backup' },
    el('h2', { text: L('exp.title') }), el('p', { class: 'sub', text: L('exp.sub') }),
    el('div', { class: 'check' }, exportEmbeddings, el('span', { text: L('exp.embeddings') })),
    el('div', { class: 'btns' }, exportAll), exportMsg));

  // --- settings tab: restore from an archive (applied at once; PHASE-38) -----------------------
  const restoreFile = el('input', { type: 'file', accept: '.zip,application/zip', style: 'display:none' });
  const restorePick = el('button', { text: L('rst.pick') });
  const restoreMsg = el('div', { class: 'msg' });
  const restoreSummary = el('div', {});
  const restoreGo = el('button', { text: L('rst.restore'), style: 'display:none' });
  const restoreCancel = el('button', { text: L('rst.cancel'), style: 'display:none' });
  let restoreId: string | null = null;
  const restoreIdle = (id: string | null) => {
    restoreId = id;
    restorePick.disabled = false;
    restoreGo.style.display = restoreCancel.style.display = id ? '' : 'none';
    restoreGo.disabled = restoreCancel.disabled = false;
  };
  restorePick.addEventListener('click', () => restoreFile.click());
  restoreFile.addEventListener('change', async () => {
    const file = restoreFile.files?.[0];
    restoreFile.value = '';  // picking the same file again fires `change` again
    if (!file) return;
    restoreSummary.replaceChildren();
    restoreIdle(null);
    // Each chunk is hashed with crypto.subtle, which a page over plain HTTP on another host does not have (H8).
    if (!globalThis.crypto?.subtle) return say(restoreMsg, L('rst.insecure'), 'err');
    restorePick.disabled = true;
    try {
      const up = await uploadArchive(deps.api, file, (sent, total) => say(restoreMsg, L('rst.uploading', {
        pct: total ? Math.floor((sent / total) * 100) : 100, sent: (sent / 1_048_576).toFixed(1),
        total: (total / 1_048_576).toFixed(1) })));
      say(restoreMsg, L('rst.checking'));
      await deps.api('POST', `/v1/archive/uploads/${up.id}/check`, {});  // nativeFetch refuses a POST without a body
      const view = await waitFor(deps.api, up.id, ['checked', 'refused']);
      if (view.state === 'refused' || !view.summary) {
        say(restoreMsg, L('rst.refused', { why: view.detail ?? '' }), 'err');
        restoreIdle(null);
        return;
      }
      showSummary(view.summary);
      const blocked = view.summary.conversations.some((c) => c.here);
      say(restoreMsg, blocked ? L('rst.blocked') : '', blocked ? 'err' : 'muted');
      restoreIdle(up.id);
      restoreGo.disabled = blocked;
    } catch (error) {
      say(restoreMsg, errorText(lang, error), 'err');
      restoreIdle(null);
    }
  });
  /** What the checked archive holds: its scope, chats (those already here marked), settings and upgrades (Q2, Q5). */
  function showSummary(s: ArchiveSummary): void {
    const head = L('rst.summary', { scope: L(s.scope === 'install' ? 'rst.scope_install' : 'rst.scope_chats'),
      n: s.conversations.length, version: s.nmos_version ?? '?', date: (s.created_at ?? '').slice(0, 10) });
    const list = el('ul', {}, ...s.conversations.map((c) => el('li', {
      text: `${c.character ?? L('rst.no_character')} — ${c.chat ?? `${L('rst.no_chat')} (${c.host_chat_ref.slice(0, 8)})`}`
        + (c.here ? ` (${L('rst.here')})` : '') })));
    restoreSummary.replaceChildren(el('p', { class: 'sub', text: head }), list,
      ...(s.settings_added.length ? [el('p', { class: 'sub', text: L('rst.settings', {
        keys: s.settings_added.map((x) => (x.value !== undefined ? `${x.key} = ${String(x.value)}` : x.key)).join(', ') }) })] : []),
      ...(s.migrations.length ? [el('p', { class: 'sub', text: L('rst.migrations', { list: s.migrations.join(', ') }) })] : []));
  }
  restoreGo.addEventListener('click', async () => {
    const id = restoreId;
    if (!id) return;
    restoreGo.disabled = restoreCancel.disabled = restorePick.disabled = true;
    say(restoreMsg, L('rst.restoring'));
    try {
      await deps.api('POST', `/v1/archive/uploads/${id}/restore`, {});
      const view = await waitFor(deps.api, id, ['restored', 'failed']);
      if (view.state === 'restored' && view.result) {
        say(restoreMsg, L('rst.done', { n: view.result.conversations.length, jobs: view.result.queued_jobs ?? 0 })
          + (view.detail ? ` ${view.detail}` : ''), 'ok');
      } else {
        say(restoreMsg, L('rst.failed', { why: view.detail ?? '' }), 'err');
      }
      restoreSummary.replaceChildren();
    } catch (error) {
      say(restoreMsg, errorText(lang, error), 'err');
    }
    restoreIdle(null);
  });
  restoreCancel.addEventListener('click', async () => {
    const id = restoreId;
    restoreIdle(null);
    restoreSummary.replaceChildren();
    say(restoreMsg, '');
    if (id) await deps.api('DELETE', `/v1/archive/uploads/${id}`).catch(() => undefined);
  });
  settingsView.append(el('div', { class: 'card' },
    el('h2', { text: L('rst.title') }), el('p', { class: 'sub', text: L('rst.sub') }),
    el('div', { class: 'btns' }, restorePick, restoreGo, restoreCancel), restoreFile, restoreSummary, restoreMsg));

  // --- settings tab: clean up conversations missing from the host (PHASE-68, H22, ADR 0009) ------
  let orphanRows: OrphanRow[] = [];
  let orphanSelected = new Set<string>();
  let orphanArmed = false;
  let orphanBusy = false;
  let orphanTotalHost = 0;
  let orphanMatchedActive = 0;
  const orphanScan = el('button', { text: L('orph.scan') });
  const orphanSummary = el('p', { class: 'sub', style: 'display:none;margin-top:12px' });
  const orphanSelectAll = el('input', { type: 'checkbox', class: 'orph-select-all' });
  const orphanCount = el('span', { class: 'muted', style: 'font-size:13px' });
  const orphanHead = el('div', { class: 'orph-head', style: 'display:none' },
    el('label', { class: 'orph-all' }, orphanSelectAll, el('span', { text: L('orph.select_all') })),
    orphanCount);
  const orphanList = el('div', { class: 'orph-list', style: 'display:none' });
  const orphanBanner = el('div', { class: 'orph-banner', style: 'display:none' });
  const orphanDelete = el('button', { class: 'danger', style: 'display:none', disabled: true,
    text: L('orph.delete', { n: 0 }) });
  const orphanMsg = el('div', { class: 'msg' });

  const formatCarryTargetList = (targets: { character?: string | null; chat?: string | null; id?: string | null;
    target_missing?: boolean }[]) => targets.map((tg) => {
    const name = orphanLabel(tg, L('orph.unnamed'));
    return tg.target_missing ? L('orph.carry_target_missing', { name }) : name;
  }).join(', ');

  function syncOrphanControls(): void {
    const sum = selectionSummary(orphanRows, orphanSelected);
    const hasRows = sum.totalCount > 0;
    orphanHead.style.display = hasRows ? '' : 'none';
    orphanList.style.display = hasRows ? '' : 'none';
    orphanDelete.style.display = hasRows ? '' : 'none';
    if (!hasRows) {
      orphanBanner.style.display = 'none';
      orphanSelectAll.checked = false;
      orphanSelectAll.indeterminate = false;
      orphanDelete.disabled = true;
      return;
    }
    orphanSelectAll.checked = sum.allSelected;
    orphanSelectAll.indeterminate = sum.indeterminate;
    orphanSelectAll.disabled = orphanBusy;
    orphanCount.textContent = L('orph.selected_count', { n: sum.selectedCount, total: sum.totalCount });
    if (sum.activeCarryTargets.length > 0) {
      orphanBanner.textContent = L('orph.carry_banner', {
        n: sum.activeCarryTargets.length,
        targets: formatCarryTargetList(sum.activeCarryTargets),
      });
      orphanBanner.style.display = '';
    } else {
      orphanBanner.style.display = 'none';
    }
    orphanDelete.disabled = orphanBusy || sum.selectedCount === 0;
    orphanDelete.textContent = orphanArmed
      ? L('orph.delete_confirm', { n: sum.selectedCount })
      : L('orph.delete', { n: sum.selectedCount });
  }

  function disarmOrphan(): void {
    if (!orphanArmed) return;
    orphanArmed = false;
    say(orphanMsg, '');
  }

  function renderOrphanList(): void {
    orphanList.replaceChildren(...orphanRows.map((row) => {
      const box = el('input', { type: 'checkbox', 'data-orph-id': row.id });
      box.checked = orphanSelected.has(row.id);
      box.disabled = orphanBusy;
      box.addEventListener('change', () => {
        if (box.checked) orphanSelected.add(row.id);
        else orphanSelected.delete(row.id);
        disarmOrphan();
        syncOrphanControls();
      });
      const metaBits = [row.messages > 0 ? L('orph.msgs', { n: row.messages }) : L('orph.stub')];
      const when = formatOrphanDate(row.last_retrieval || row.created_at);
      if (when) metaBits.push(L(row.last_retrieval ? 'orph.last_used' : 'orph.created', { when }));
      const bodyChildren: HTMLElement[] = [
        el('span', { class: 'orph-title', text: orphanLabel(row, L('orph.unnamed')) }),
        el('span', { class: 'orph-meta', text: metaBits.join(' · ') }),
      ];
      if (row.carried_by.length > 0) {
        bodyChildren.push(el('span', {
          class: 'orph-carry-warn',
          text: L('orph.carry_badge', { targets: formatCarryTargetList(row.carried_by) }),
        }));
      }
      const hasCarry = row.carried_by.length > 0;
      return el('label', { class: `orph-row${hasCarry ? ' has-carry' : ''}` },
        box, el('span', { class: 'orph-row-body' }, ...bodyChildren));
    }));
    syncOrphanControls();
  }

  orphanSelectAll.addEventListener('change', () => {
    if (orphanSelectAll.checked) orphanSelected = new Set(orphanRows.map((r) => r.id));
    else orphanSelected.clear();
    for (const box of Array.from(orphanList.querySelectorAll<HTMLInputElement>('input[data-orph-id]'))) {
      box.checked = orphanSelectAll.checked;
    }
    disarmOrphan();
    syncOrphanControls();
  });

  orphanScan.addEventListener('click', async () => {
    if (orphanBusy) return;
    orphanBusy = true;
    orphanArmed = false;
    orphanRows = [];
    orphanSelected = new Set();
    orphanSummary.style.display = 'none';
    orphanScan.disabled = true;
    renderOrphanList();
    say(orphanMsg, L('orph.scanning'));
    try {
      const scan: HostChatScan = deps.scanHostChats
        ? await deps.scanHostChats()
        : { ok: false, reason: 'unsupported' };
      if (!scan.ok) {
        const key = scan.reason === 'denied' ? 'orph.err_denied'
          : scan.reason === 'invalid' ? 'orph.err_invalid' : 'orph.err_unsupported';
        say(orphanMsg, L(key), 'err');
        return;
      }
      // Q3 (a): an empty host list blocks cleanup rather than risking a wipe on host schema/load issues.
      if (scan.chatIds.length === 0) {
        say(orphanMsg, L('orph.err_empty_host'), 'warn');
        return;
      }
      const preview = await deps.api<OrphanPreview>('POST', '/v1/conversations/orphans/preview',
        { host: 'pocketrisu', active_chat_refs: scan.chatIds }, 30_000);
      if (!preview.orphans.length) {
        say(orphanMsg, L('orph.none', { matched: preview.matched_active, total: preview.total_host_conversations }), 'ok');
        return;
      }
      // Q1 (a): all candidates start unchecked by default; user picks via row checkboxes or Select all.
      orphanRows = preview.orphans;
      orphanSelected = new Set();
      orphanTotalHost = preview.total_host_conversations;
      orphanMatchedActive = preview.matched_active;
      orphanSummary.textContent = L('orph.summary', {
        total: orphanTotalHost,
        n: orphanRows.length,
        matched: orphanMatchedActive,
      });
      orphanSummary.style.display = '';
      say(orphanMsg, '');
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      say(orphanMsg, /-> HTTP (?:404|405)\b/.test(msg) ? L('orph.no_sidecar') : errorText(lang, error), 'err');
    } finally {
      orphanBusy = false;
      orphanScan.disabled = false;
      renderOrphanList();
    }
  });

  orphanDelete.addEventListener('click', async () => {
    if (orphanBusy) return;
    const sum = selectionSummary(orphanRows, orphanSelected);
    if (sum.selectedCount === 0) return;
    if (!orphanArmed) {
      orphanArmed = true;
      syncOrphanControls();
      say(orphanMsg, sum.activeCarryTargets.length > 0
        ? L('orph.delete_warn_carry', { n: sum.selectedCount, m: sum.totalMessages, c: sum.activeCarryTargets.length })
        : L('orph.delete_warn', { n: sum.selectedCount, m: sum.totalMessages }), 'err');
      return;
    }
    orphanArmed = false;
    orphanBusy = true;
    orphanScan.disabled = true;
    renderOrphanList();
    say(orphanMsg, L('orph.deleting'));
    const removed = new Set<string>();
    let deletedConvs = 0;
    let deletedMsgs = 0;
    let deletedCarry = 0;
    try {
      for (const batch of chunkIds(Array.from(orphanSelected))) {
        const res = await deps.api<BatchDeleteResult>('POST', '/v1/conversations/delete-batch', { ids: batch }, 120_000);
        for (const item of res.deleted ?? []) removed.add(item.id);
        for (const id of res.not_found ?? []) removed.add(id);
        deletedConvs += res.totals?.conversations ?? (res.deleted?.length ?? 0);
        deletedMsgs += res.totals?.messages ?? 0;
        deletedCarry += res.totals?.carry_links ?? 0;
      }
      say(orphanMsg, deletedCarry > 0
        ? L('orph.done_carry', { n: deletedConvs, m: deletedMsgs, c: deletedCarry })
        : L('orph.done', { n: deletedConvs, m: deletedMsgs }), 'ok');
    } catch (error) {
      say(orphanMsg, errorText(lang, error), 'err');
    } finally {
      if (removed.size > 0) {
        orphanRows = orphanRows
          .filter((r) => !removed.has(r.id))
          .map((r) => ({ ...r, carried_by: r.carried_by.filter((t) => !removed.has(t.id)) }));
        orphanTotalHost = Math.max(orphanMatchedActive + orphanRows.length, orphanTotalHost - deletedConvs);
        for (const id of removed) orphanSelected.delete(id);
        knownChats = knownChats.filter((c) => !removed.has(c.id));
        if (activeChatId && removed.has(activeChatId)) {
          activeChatId = null;
          activeChatName = '';
          updateChatLabel();
        }
        if (hubConversation && removed.has(hubConversation)) hubConversation = null;
        if (hostConversationId && removed.has(hostConversationId)) hostConversationId = null;
        visited.length = 0;
        if (!orphanRows.length) {
          orphanSummary.style.display = 'none';
        } else {
          orphanSummary.textContent = L('orph.summary', {
            total: orphanTotalHost,
            n: orphanRows.length,
            matched: orphanMatchedActive,
          });
        }
      }
      orphanBusy = false;
      orphanScan.disabled = false;
      renderOrphanList();
    }
  });

  settingsView.append(el('div', { class: 'card', id: 'nmos-orphans' },
    el('h2', { text: L('orph.title') }), el('p', { class: 'sub', text: L('orph.sub') }),
    el('div', { class: 'btns' }, orphanScan),
    orphanSummary, orphanHead, orphanList, orphanBanner,
    el('div', { class: 'btns' }, orphanDelete), orphanMsg));

  // --- settings tab: one save bar ---------------------------------------------------------------
  const barText = el('span', { class: 'text muted' });
  const revert = el('button', { text: L('revert') });
  const save = el('button', { class: 'primary', text: L('save') });
  const bar = el('div', { class: 'bar' }, barText, revert, save);
  root.append(bar);

  function values(): FormValues {
    return {
      conn: { url: url.value, route: route.value, enabled: enabled.checked, reserved: reserved.value, deadline: deadline.value,
        token: token.value },
      llm: { ...llm.values(), ...extraValues() }, emb: emb.values(), rerank: rerank.values(),
      tune: { threshold: threshold.value, minSim: minSim.value, embedWait: embedWait.value, topK: topK.value,
        facts: factsLimit.value, backfill: backfill.value, summaries: summaries.checked, canonFacts: canonFacts.checked,
        pinAt: pinAt.checked, embedChunks: embedChunks.value, extractOnOutput: extractOnOutput.checked },
      trim: { on: trimOn.checked, keep: trimKeep.value },
    };
  }
  let baseline: FormValues = values();
  let closing = false;
  const dirty = () => dirtySections(baseline, values());

  const SECTION_TO_GROUP: Record<Section, Group> = {
    conn: 'connection', llm: 'models', emb: 'models', rerank: 'models', tune: 'memory', trim: 'memory',
  };
  let activeModalCancel: (() => void) | null = null;
  let workerAutoOn = false;
  let workerAutoTimer: ReturnType<typeof setInterval> | null = null;
  function stopWorkerAuto(): void {
    if (workerAutoTimer !== null) { clearInterval(workerAutoTimer); workerAutoTimer = null; }
  }
  function syncDirtyDots(): void {
    if (!dirtyReady) return;
    const groups = new Set<Group>(dirty().map((s) => SECTION_TO_GROUP[s]));
    if (parserDirty()) groups.add('rules');
    for (const btn of Array.from(groupList.querySelectorAll<HTMLButtonElement>('button[data-group]'))) {
      const dot = btn.querySelector<HTMLElement>('.dirty-dot');
      if (dot) dot.style.display = groups.has(btn.dataset.group as Group) ? '' : 'none';
    }
    for (const dot of settingsDirtyDots) dot.style.display = groups.size ? '' : 'none';
  }

  function update(message?: { text: string; kind: 'ok' | 'err' | 'warn' | 'muted' }): void {
    const d = dirty();
    syncTrimWarn();  // here, since loading and saving set the boxes without an event
    syncExtra();
    syncDirtyDots();
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
    token.value = (await deps.getArg('auth_token')) || '';
    hudBox.checked = Number(await deps.getArg('hud')) === 1;
  }

  /** The trimming args as `host.ts` reads them: on only at 1, the recent turns kept within 4..200 (16 when unset). */
  async function loadTrim(): Promise<void> {
    const stored = trimArgs({ on: Number(await deps.getArg('trim_old_turns')) === 1,
      keep: String((await deps.getArg('keep_recent_turns')) ?? '') });
    trimOn.checked = stored.trim_old_turns === 1;
    trimKeep.value = String(stored.keep_recent_turns);
  }

  function fillServer(cfg: ServerConfig): void {
    install = cfg.install ?? null;
    llm.fill(cfg.llm); emb.fill(cfg.embeddings); rerank.fill(cfg.rerank);
    extraKnown = typeof cfg.llm.extra_body === 'object' && cfg.llm.extra_body !== null;
    extraText.value = extraKnown ? showBody(cfg.llm.extra_body as Record<string, unknown>) : '';
    noTemp.checked = cfg.llm.no_temperature === true;
    threshold.value = String(cfg.recall.threshold);
    minSim.value = String(cfg.recall.vector_min_sim);
    embedWait.value = cfg.recall.embed_timeout_ms === undefined ? '' : String(cfg.recall.embed_timeout_ms);
    embedWait.disabled = cfg.recall.embed_timeout_ms === undefined;  // a sidecar older than the setting
    topK.value = String(cfg.recall.top_k);
    factsLimit.value = String(cfg.recall.facts_limit);
    backfill.value = String(cfg.extraction.backfill);
    summaries.checked = cfg.extraction.summaries !== false;
    canonFacts.checked = cfg.extraction.canon_facts !== false;
    pinAtKnown = typeof cfg.recall.pin_at_mentions === 'boolean';
    pinAt.checked = cfg.recall.pin_at_mentions === true;
    pinAt.disabled = !pinAtKnown;  // a sidecar older than the setting: nothing to show, nothing sent
    embedChunksKnown = typeof cfg.embeddings.max_chunks === 'number';
    embedChunks.value = embedChunksKnown ? String(cfg.embeddings.max_chunks) : '';
    embedChunks.disabled = !embedChunksKnown;  // likewise
    extractOnOutputKnown = typeof cfg.extraction.on_output === 'boolean';
    extractOnOutput.checked = cfg.extraction.on_output === true;
    extractOnOutput.disabled = !extractOnOutputKnown;  // likewise
    showEmbedChunks();
    fillParsers(cfg);
  }

  async function loadAll(): Promise<void> {
    await loadConn();
    await loadTrim();
    try { fillServer(await deps.api<ServerConfig>('GET', '/v1/config', undefined, 5000)); } catch { /* the status tab shows why */ }
    baseline = values();
    update();
    void deps.api<{ host_character_name?: string | null }[]>('GET', '/v1/conversations?host=pocketrisu', undefined, 5000)
      .then((chats) => {
        if (!Array.isArray(chats)) return;
        for (const c of chats) if (c.host_character_name?.trim()) knownCards.add(c.host_character_name.trim());
        parserCards.replaceChildren(...[...knownCards].sort().map((name) => el('option', { value: name })));
      }).catch(() => {});
  }

  /** What a save that changes the extraction model would queue, per choice (PHASE-57 A3, `POST /v1/config/preview`). */
  interface ModelPreview { model_change: boolean; queued: Partial<Record<'continue' | 'recent' | 'canon', Record<string, number>>> }
  const jobsOf = (q: Record<string, number> | undefined): number => Object.values(q ?? {}).reduce((a, b) => a + b, 0);

  /** Asks, in a centered modal sheet (keeping `.bar .model-change` structure), what the chats already processed get
   * from the new model: carry on (selected), the latest turns again, and the setting read again; null on cancel. */
  function askModelChange(p: ModelPreview, turns: string): Promise<{ mode: 'continue' | 'recent'; canon: boolean } | null> {
    return new Promise((resolve) => {
      const name = `nmos-model-change-${Date.now()}`;
      const carry = el('input', { type: 'radio', name, value: 'continue' });
      const redo = el('input', { type: 'radio', name, value: 'recent' });
      const canon = el('input', { type: 'checkbox' });
      carry.checked = true;
      const extra = Math.max(0, (p.queued.canon?.canon ?? 0) - (p.queued.continue?.canon ?? 0));
      const go = el('button', { class: 'primary', text: L('save') });
      const back = el('button', { text: L('cancel') });
      const done = (answer: { mode: 'continue' | 'recent'; canon: boolean } | null) => {
        activeModalCancel = null;
        bar.classList.remove('modal-open');
        bar.replaceChildren(barText, revert, save);
        resolve(answer);
      };
      activeModalCancel = () => done(null);
      go.addEventListener('click', () => done({ mode: redo.checked ? 'recent' : 'continue', canon: canon.checked }));
      back.addEventListener('click', () => done(null));
      bar.classList.add('modal-open');
      bar.replaceChildren(el('div', { class: 'model-change' },
        el('h2', { text: L('mc.title') }),
        el('p', { class: 'sub', text: L('mc.sub') }),
        el('label', { class: 'check' }, carry, el('span', { text: L('mc.continue', { n: jobsOf(p.queued.continue) }) })),
        el('label', { class: 'check' }, redo, el('span', { text: L('mc.recent', { t: turns, n: jobsOf(p.queued.recent) }) })),
        el('label', { class: 'check' }, canon, el('span', { text: L('mc.canon', { n: extra }) })),
        el('div', { class: 'btns' }, back, go)));
    });
  }

  async function saveAll(): Promise<boolean> {
    const d = dirty();
    if (!d.length) { update({ text: L('no_changes'), kind: 'muted' }); return true; }
    // before anything is written: the sidecar would refuse it, and the field says why (PHASE-61 S4)
    if (extraKnown && !bodyOf(extraText.value)) { update({ text: L('extra.invalid'), kind: 'err' }); return false; }
    save.disabled = true;
    say(barText, L('saving'));
    const v = values();
    let connSaved = 0;
    let connTotal = 0;
    let connComplete = !d.includes('conn');
    let trimComplete = !d.includes('trim');
    try {
      if (d.includes('trim')) {
        // Plugin args only: no sidecar update, and the connection and status-rule state stay as they are.
        const args = trimArgs(v.trim);
        await deps.setArg('trim_old_turns', args.trim_old_turns);
        await deps.setArg('keep_recent_turns', args.keep_recent_turns);
        trimComplete = true;
        trimKeep.value = String(args.keep_recent_turns);  // show what was stored: kept within 4..200
        baseline = { ...baseline, trim: values().trim };
        if (d.length === 1) { update({ text: L('saved'), kind: 'ok' }); return true; }
      }
      if (d.includes('conn')) {
        // The prior connection's capabilities must not enable status writes to a changed sidecar.
        parserSupported = false; updateParser();
        // First, so the server update below already goes to a changed sidecar address.
        const args = connArgs(v.conn);
        connTotal = Object.keys(args).length;
        for (const [k, value] of Object.entries(args)) {
          await deps.setArg(k, value);
          connSaved += 1;
        }
        connComplete = true;
        // Show what was stored: the budget is capped at PANEL_MAX_RESERVED_TOKENS, the deadline kept in range.
        reserved.value = String(args.reserved_memory_tokens);
        deadline.value = String(args.deadline_ms);
        baseline = { ...baseline, conn: values().conn };
      }
      const body = configBody(d, v, { pinAt: pinAtKnown, rerank: rerankKnown, embedChunks: embedChunksKnown,
        extractOnOutput: extractOnOutputKnown }, baseline);
      // Said with any save that touches either value; the save itself goes ahead (audit F20).
      const tight = (d.includes('tune') || d.includes('conn')) && embedWaitTooLong(v.tune.embedWait, v.conn.deadline)
        ? ` ${L('tune.embed_wait_tight', { w: v.tune.embedWait.trim(), d: v.conn.deadline.trim() || String(DEFAULT_DEADLINE_MS) })}` : '';
      if (!Object.keys(body).length) {
        // First connection: load its active bindings and capabilities without reopening or applying the draft.
        fillServer(await deps.api<ServerConfig>('GET', '/v1/config', undefined, 5000));
        baseline = values();
        update({ text: L('saved') + tight, kind: tight ? 'warn' : 'ok' });
        return true;
      }
      const modelChanged = d.includes('llm') && modelChange(baseline, v);  // a body or switch change too (PHASE-61 S2)
      if (modelChanged) {  // a sidecar older than PHASE-57 has no preview: it saves as before
        const p = await deps.api<ModelPreview>('POST', '/v1/config/preview', body, 10000).catch(() => null);
        if (p?.model_change) {
          const answer = await askModelChange(p, v.tune.backfill.trim() || backfill.value);
          if (!answer) { update({ text: L('mc.cancelled'), kind: 'muted' }); return false; }
          body.on_model_change = answer;
        }
      }
      const r = await deps.api<ServerConfig>('PUT', '/v1/config', body);
      fillServer(r);
      baseline = values();
      const parts = [r.queued_jobs ? L('saved_queued', { n: r.queued_jobs }) : L('saved')];
      if (r.queued_jobs) deps.hud.background();
      update({ text: parts.join(' ') + tight, kind: tight ? 'warn' : 'ok' });
      return true;
    } catch (error) {
      const text = errorText(lang, error);
      update({ text: !trimComplete ? text : !connComplete ? L('conn_save_failed', { n: connSaved, total: connTotal, e: text })
        : d.includes('conn') ? L('conn_saved_server_failed', { e: text }) : text, kind: 'err' });
      return false;
    }
  }

  save.addEventListener('click', () => void saveAll());
  revert.addEventListener('click', () => void loadAll());

  // --- closing, language, tabs ------------------------------------------------------------------
  let onDocClick: ((e: MouseEvent) => void) | null = null;
  let onDocKey: ((e: KeyboardEvent) => void) | null = null;
  function cleanupPanel(): void {
    window.clearTimeout(armTimer);
    stopWorkerAuto();
    clearNotesTimer();
    hideToast();
    activeModalCancel = null;
    if (onDocClick) document.removeEventListener('click', onDocClick);
    if (onDocKey) document.removeEventListener('keydown', onDocKey);
    closers.clear();
    bulkGroups.clear();
    picked.clear();
    bulkPicked.clear();
    knownChats = [];
    lastMeta = null;
  }
  function shut(): void {
    cleanupPanel();
    root.remove();
    current = null;
    void deps.hide();
  }
  close.addEventListener('click', () => {
    if (closing) return;
    if (!dirty().length && !parserDirty()) return shut();
    closing = true;
    const saveClose = el('button', { class: 'primary', text: L('save_and_close') });
    const discard = el('button', { text: L('discard_and_close') });
    const cancel = el('button', { text: L('cancel') });
    const restore = (refresh = true) => { closing = false; bar.replaceChildren(barText, revert, save); if (refresh) update(); };
    saveClose.addEventListener('click', async () => {
      saveClose.disabled = true;
      if (await saveAll()) shut(); else restore(false);
    });
    discard.addEventListener('click', shut);
    cancel.addEventListener('click', () => restore());
    select('settings');
    // A status draft must be applied by its own button, never by Save-and-close.
    bar.replaceChildren(el('span', { class: 'text warn', text: L(parserDirty() ? 'rules.close_draft' : 'close_unsaved') }),
      cancel, discard, ...(parserDirty() ? [] : [saveClose]));
  });

  language.addEventListener('change', async () => {
    if (dirty().length || parserDirty()) {
      language.value = lang;
      select('settings');
      update({ text: L('lang_unsaved'), kind: 'warn' });
      return;
    }
    const next = langOf(language.value);
    await deps.setArg('language', next);
    cleanupPanel();
    root.remove();
    current = await render(deps, next, shown);
  });

  // --- PHASE-59 persistent shell state & controls -----------------------------------------------
  let activePrimary: PrimaryTab = 'home';
  let activeMemSub: MemorySub = 'story';
  let activeChatId: string | null = null;
  let hostConversationId: string | null = null;
  let activeChatName = '';
  let attentionCount = 0;
  let lastMeta: HubMeta | null = null;
  let lastConnected = true;
  let lastStatusKind: 'ok' | 'warn' | 'err' | '' = 'ok';
  let knownChats: HubChatItem[] = [];
  let chatPopOpen = false;
  let currentGroup: Group = 'chat';

  const navButtons = new Map<PrimaryTab, HTMLButtonElement[]>();
  const attnBadges: HTMLSpanElement[] = [];
  const settingsDirtyDots: HTMLSpanElement[] = [];
  let chatBtnLabel: HTMLSpanElement | null = null;
  let chatPop: HTMLElement | null = null;
  let chatSearchInput: HTMLInputElement | null = null;
  let chatListEl: HTMLElement | null = null;
  let statusPill: HTMLButtonElement | null = null;

  function setPrimaryNav(next: PrimaryTab): void {
    activePrimary = next;
    for (const [k, btns] of navButtons.entries()) {
      for (const b of btns) b.classList.toggle('on', k === next);
    }
  }

  function updateAttentionBadges(n: number): void {
    attentionCount = Math.max(0, n);
    for (const badge of attnBadges) {
      badge.textContent = attentionCount > 99 ? '99+' : String(attentionCount);
      badge.style.display = attentionCount > 0 ? '' : 'none';
    }
    const subBadge = memSubBar.querySelector<HTMLElement>('.mem-attn-badge');
    if (subBadge) {
      subBadge.textContent = String(attentionCount);
      subBadge.style.display = attentionCount > 0 ? '' : 'none';
    }
  }

  function updateChatLabel(): void {
    if (!chatBtnLabel) return;
    chatBtnLabel.textContent = activeChatName || L('shell.no_chat');
  }

  function updateStatusPill(s?: StatusInfo | null, meta?: HubMeta | null): void {
    if (!statusPill) return;
    let kind: 'ok' | 'warn' | 'err' | '' = '';
    let key: StringKey = 'shell.status_ok';
    if (s && !s.connected) {
      kind = 'err'; key = 'shell.status_err';
    } else if (s && !s.enabled) {
      kind = ''; key = 'shell.status_off';
    } else if (meta?.working?.state === 'failed' || (meta?.working?.failed ?? 0) > 0) {
      kind = 'err'; key = 'shell.status_warn';
    } else if (meta?.working?.state === 'working' || (meta?.working?.queued ?? 0) > 0) {
      kind = 'warn'; key = 'shell.status_working';
    } else if ((meta?.attention ?? attentionCount) > 0) {
      kind = 'warn'; key = 'shell.status_warn';
    } else {
      kind = 'ok'; key = 'shell.status_ok';
    }
    if (s) lastConnected = s.connected;
    lastStatusKind = kind;
    statusPill.className = `status-pill${kind ? ` ${kind}` : ''}`;
    statusPill.replaceChildren(
      el('span', { class: `dot${kind ? ` ${kind}` : ''}` }),
      el('span', { class: 'st-txt', text: L(key) }),
    );
  }

  function applyHubMeta(meta: HubMeta | undefined): void {
    if (!meta) return;
    lastMeta = meta;
    if (meta.conv) {
      activeChatId = meta.conv.id;
      activeChatName = meta.conv.name;
      updateChatLabel();
    }
    if (typeof meta.attention === 'number') updateAttentionBadges(meta.attention);
    if (Array.isArray(meta.chats) && meta.chats.length) knownChats = meta.chats;
    void deps.status().then((s) => updateStatusPill(s, meta)).catch(() => updateStatusPill(null, meta));
  }

  function renderChatOptions(filter = ''): void {
    if (!chatListEl) return;
    const q = filter.trim().toLowerCase();
    const items = knownChats.filter((c) => !q || c.name.toLowerCase().includes(q)
      || (c.character ?? '').toLowerCase().includes(q) || (c.title ?? '').toLowerCase().includes(q));
    if (!items.length) {
      chatListEl.replaceChildren(el('div', { class: 'muted', style: 'padding:8px;font-size:13px', text: L('shell.chats_empty') }));
      return;
    }
    chatListEl.replaceChildren(...items.map((c) => {
      const isActive = c.id === (activeChatId ?? hubConversation);
      const opt = el('button', { class: `chat-opt${isActive ? ' on' : ''}`, 'data-chat-id': c.id },
        el('span', { style: 'overflow:hidden;text-overflow:ellipsis;white-space:nowrap', text: c.name }),
        el('span', { class: 'chat-meta', text: typeof c.turns === 'number' ? `${c.turns}t` : (isActive ? '✓' : '') }));
      opt.addEventListener('click', () => {
        closeChatPop();
        void switchActiveChat(c);
      });
      return opt;
    }));
  }

  function closeChatPop(): void {
    chatPopOpen = false;
    if (chatPop) chatPop.style.display = 'none';
  }

  async function openChatPop(): Promise<void> {
    if (!chatPop) return;
    chatPopOpen = !chatPopOpen;
    chatPop.style.display = chatPopOpen ? '' : 'none';
    if (!chatPopOpen) return;
    renderChatOptions(chatSearchInput?.value ?? '');
    chatSearchInput?.focus();
    try {
      const rows = await deps.api<{ id: string; host_character_name?: string | null; title?: string | null; message_count?: number }[]>(
        'GET', '/v1/conversations?host=pocketrisu', undefined, 5000);
      if (Array.isArray(rows) && rows.length) {
        knownChats = rows.map((r) => {
          const ch = (r.host_character_name ?? '').trim();
          const ti = (r.title ?? '').trim();
          const name = ch && ti && ti !== ch ? `${ch} · ${ti}` : (ch || ti || r.id.slice(0, 8));
          return { id: r.id, name, character: ch, title: ti, turns: typeof r.message_count === 'number' ? r.message_count : undefined };
        });
        const cur = knownChats.find((c) => c.id === (activeChatId ?? hubConversation));
        if (cur && !activeChatName) { activeChatName = cur.name; updateChatLabel(); }
        if (chatPopOpen) renderChatOptions(chatSearchInput?.value ?? '');
      }
    } catch { /* keep cached meta.chats if sidecar call fails */ }
  }

  async function switchActiveChat(chat: HubChatItem): Promise<void> {
    activeChatId = chat.id;
    hubConversation = chat.id;
    activeChatName = chat.name;
    updateChatLabel();
    if (activePrimary === 'home') {
      visited.length = 0;
      const base = await hubPath(chat.id);
      inspectorPath = base;
      void showInspector(base);
    } else if (activePrimary === 'memory') {
      openMemorySub(activeMemSub, false);
    } else if (activePrimary === 'notes') {
      notesFor = null;
      openNotesStudio(chat.id);
    } else if (activePrimary === 'settings' && currentGroup === 'chat') {
      showChatPage();
    }
  }

  function otherChatBanner(): HTMLElement | null {
    if (!hostConversationId || !activeChatId || activeChatId === hostConversationId) return null;
    const back = el('button', { class: 'primary mini', text: L('home.back_host') });
    back.addEventListener('click', () => {
      activeChatId = hostConversationId;
      hubConversation = hostConversationId;
      const found = knownChats.find((c) => c.id === hostConversationId);
      if (found) activeChatName = found.name;
      updateChatLabel();
      if (activePrimary === 'settings' && currentGroup === 'chat') showChatPage();
      else void goHome();
    });
    return el('div', { class: 'other-chat-banner' },
      el('div', {},
        el('b', { text: L('home.other_chat_title', { name: activeChatName || activeChatId.slice(0, 8) }) }),
        el('div', { class: 'chat-strip-sub', text: L('home.other_chat_sub') })),
      back);
  }

  function openDiag(mode: 'working' | 'calls' | 'raw'): void {
    const cid = activeChatId ?? hubConversation;
    notesStudioView.style.display = 'none';
    settingsView.style.display = 'none';
    statusView.style.display = 'none';
    inspectorView.style.display = '';
    bar.style.display = 'none';
    shown = 'inspector';
    root.classList.add('wide');
    setPrimaryNav('memory');
    homeQuickBar.style.display = 'none';
    memSubBar.style.display = '';
    stopWorkerAuto();
    renderMemSubBar('diag', mode);
    if (mode === 'calls') { go('/v1/inspector/calls'); return; }
    if (!cid) {
      inspbar.style.display = 'none';
      inspectorBody.replaceChildren(el('div', { class: 'card muted', text: L('mem.no_chat') }));
      return;
    }
    go(mode === 'raw' ? `/v1/inspector/c/${cid}` : `/v1/views/c/${cid}/working`);
  }

  /** Inline Home quick bar: other-chat banner, onboarding (disconnected), This Chat ON/OFF, live Worker card, advisories. */
  let quickRound = 0;
  async function refreshHomeQuick(): Promise<void> {
    if (!viewsOn) return;
    const round = ++quickRound;
    const items: HTMLElement[] = [];
    const workerReq = deps.api<unknown>('GET', '/v1/worker/status', undefined, 5000).catch(() => null);
    let s: StatusInfo | null = null;
    try { s = await deps.status(); } catch { s = null; }
    if (round !== quickRound) return;
    updateStatusPill(s, lastMeta);
    const other = otherChatBanner();
    if (other) items.push(other);
    if (s && !s.connected) {
      items.push(onboardingCard());
    }
    try {
      const state = await deps.chat.current();
      if (round !== quickRound) return;
      if (state.id !== null) {
        const id = state.id;
        const off = state.off;
        const allOff = s ? !s.enabled : false;
        const flip = el('button', { class: off ? 'primary' : '', text: L(off ? 'chat.turn_on' : 'chat.turn_off') });
        const msg = el('div', { class: 'msg' });
        flip.addEventListener('click', async () => {
          flip.disabled = true;
          try {
            await deps.chat.set(id, !off);
            const nextHub = await hubPath(activeChatId ?? undefined);
            inspectorPath = nextHub;
            void showInspector(nextHub);
            void refreshHomeQuick();
          } catch (error) { flip.disabled = false; say(msg, errorText(lang, error), 'err'); }
        });
        const badgeText = allOff ? L('home.all_off_badge') : L(off ? 'home.chat_off_badge' : 'home.chat_on_badge');
        const strip = el('div', { class: `chat-strip${off || allOff ? ' off' : ''}` },
          el('div', { class: 'chat-strip-info' },
            el('span', { class: `dot ${off || allOff ? 'warn' : 'ok'}` }),
            el('div', {},
              el('div', { class: 'chat-strip-title', text: `${L('chat.title')} · ${badgeText}` }),
              el('div', { class: 'chat-strip-sub', text: allOff ? L('chat.all_off') : L(off ? 'chat.off_sub' : 'chat.on_sub') }),
              msg)),
          flip);
        items.push(strip);
      }
    } catch { /* host chat state unavailable */ }
    if (s) {
      if (s.insecure) {
        items.unshift(el('div', { class: 'adv-card err' }, el('div', {}, el('b', { class: 'err', text: L('status.insecure') }))));
      }
      const advice = deadlineAdvice(s.last);
      if (advice) {
        const open = el('button', { class: 'mini', text: L('deadline.open_settings') });
        open.addEventListener('click', () => { selectPrimary('settings'); openGroup('connection'); });
        const took = advice.tookMs === null ? '' : L('deadline.took', { n: formatMs(advice.tookMs) });
        const text = advice.level === 'over'
          ? L('deadline.over', { d: formatMs(advice.deadlineMs), took, s: formatMs(advice.suggestMs) })
          : L('deadline.near', { d: formatMs(advice.deadlineMs), n: formatMs(advice.tookMs ?? 0), s: formatMs(advice.suggestMs) });
        items.push(el('div', { class: `adv-card${advice.level === 'over' ? ' err' : ''}` },
          el('div', {}, el('b', { class: advice.level === 'over' ? 'err' : 'warn', text: L(`deadline.${advice.level}.title`) }),
            el('p', { text })), open));
      }
      const curTokens = Number(await deps.getArg('reserved_memory_tokens')) || DEFAULT_RESERVED_TOKENS;
      if (round !== quickRound) return;
      const budget = budgetAdvice(s.last, curTokens);
      if (budget) {
        const apply = el('button', { class: 'primary mini', text: L('budget.apply', { n: budget.suggest }) });
        const bmsg = el('div', { class: 'msg' });
        apply.addEventListener('click', async () => {
          apply.disabled = true;
          try {
            await deps.setArg('reserved_memory_tokens', budget.suggest);
            say(bmsg, L('budget.applied', { n: budget.suggest, d: budget.suggest - curTokens }), 'ok');
          } catch (error) { apply.disabled = false; say(bmsg, errorText(lang, error), 'err'); }
        });
        const text = L(budget.all ? 'budget.text' : 'budget.text_more', { m: budget.offered, c: budget.cut, b: budget.budget,
          s: budget.suggest, d: budget.suggest - curTokens });
        items.push(el('div', { class: 'adv-card' },
          el('div', {}, el('b', { class: 'warn', text: L('budget.title', { c: budget.cut }) }), el('p', { text }), bmsg), apply));
      }
      if (s.last?.vectors === 'fallback') {
        items.push(el('div', { class: 'adv-card' },
          el('div', {}, el('b', { class: 'warn', text: L('vectors.title') }), el('p', { text: L('vectors.text') }))));
      }
    }
    homeQuickBar.replaceChildren(...items);
    // Live Worker card (#1): surface queued/failing model work directly on Home without delaying the hub.
    const rawWorker = await workerReq;
    if (round !== quickRound || !homeQuickBar.isConnected || homeQuickBar.style.display === 'none') return;
    const wShown = workerLines(lang, rawWorker);
    if (wShown.lines.length && (wShown.level === 'working' || wShown.level === 'trouble')) {
      const ws = rawWorker as WorkerStatus;
      const errIdx = ws.last_error && wShown.level === 'trouble' ? wShown.lines.length - 1 : -1;
      const autoBtn = el('button', { class: `mini${workerAutoOn ? ' primary' : ''}`,
        text: L(workerAutoOn ? 'worker.auto_on' : 'worker.auto_off') });
      autoBtn.addEventListener('click', () => {
        workerAutoOn = !workerAutoOn;
        if (workerAutoOn) {
          stopWorkerAuto();
          workerAutoTimer = setInterval(() => {
            if (activePrimary === 'home' && homeQuickBar.style.display !== 'none') void refreshHomeQuick();
            else stopWorkerAuto();
          }, 5000);
        } else stopWorkerAuto();
        autoBtn.classList.toggle('primary', workerAutoOn);
        autoBtn.textContent = L(workerAutoOn ? 'worker.auto_on' : 'worker.auto_off');
      });
      const callsBtn = el('button', { class: 'mini', text: L('worker.open_calls') });
      callsBtn.addEventListener('click', () => openDiag('calls'));
      const actBtns: HTMLElement[] = [callsBtn];
      const cid = activeChatId ?? hubConversation;
      if (wShown.level === 'trouble') {
        if (cid && (ws.dead_recent > 0 || ws.retrying > 0)) {
          const retry = el('button', { class: 'primary mini', text: L('act.retry') });
          retry.addEventListener('click', () => void retryFrom(cid));
          actBtns.unshift(retry);
        }
        const modelsBtn = el('button', { class: 'mini', text: L('worker.open_models') });
        modelsBtn.addEventListener('click', () => { selectPrimary('settings'); openGroup('models'); });
        actBtns.push(modelsBtn);
      }
      const wCard = el('div', { class: `worker-home${wShown.level === 'trouble' ? ' trouble' : ''}` },
        el('div', { class: 'worker-home-head' },
          el('span', { class: 'worker-home-title' },
            el('span', { class: `dot ${wShown.level === 'trouble' ? 'warn' : 'ok'}` }),
            el('span', { text: L('worker.title') })),
          el('div', { style: 'display:flex;gap:6px;flex-wrap:wrap' }, autoBtn, ...actBtns)),
        el('div', { class: 'worker-home-lines' },
          ...wShown.lines.map((line, i) => el('div', { class: i === errIdx ? 'warn' : 'muted', text: line }))));
      homeQuickBar.append(wCard);
      if (wShown.level === 'trouble') updateStatusPill(s, { ...(lastMeta ?? {}), working: { state: 'failed', failed: ws.dead_recent + ws.retrying } });
    } else {
      stopWorkerAuto();
    }
  }

  function renderMemSubBar(sub: MemorySub, diagMode: 'working' | 'calls' | 'raw' = 'working'): void {
    activeMemSub = sub;
    const defs: { key: MemorySub; label: StringKey; ic: IconName; hide?: boolean }[] = [
      { key: 'story', label: 'mem.story', ic: 'book' },
      { key: 'explore', label: 'mem.explore', ic: 'search' },
      { key: 'attention', label: 'mem.attention', ic: 'alert' },
      { key: 'map', label: 'mem.map', ic: 'map', hide: !mapOn },
      { key: 'diag', label: 'mem.diag', ic: 'terminal' },
    ];
    const tabsRow = el('div', { class: 'mem-subtabs' });
    for (const d of defs) {
      if (d.hide) continue;
      const children: (Node | string)[] = [icon(d.ic, 14), L(d.label)];
      if (d.key === 'attention') {
        const badge = el('span', { class: 'nav-badge mem-attn-badge', text: String(attentionCount),
          style: attentionCount > 0 ? '' : 'display:none' });
        children.push(badge);
      }
      const btn = el('button', { class: sub === d.key ? 'on' : '', 'data-memsub': d.key }, ...children);
      btn.addEventListener('click', () => openMemorySub(d.key));
      tabsRow.append(btn);
    }
    const subHead = el('div', { class: 'mem-subhead' },
      el('p', { class: 'mem-subtext', text: L(`mem.${sub}_sub` as StringKey) }));
    if (sub === 'diag') {
      const cid = activeChatId ?? hubConversation;
      const bWork = el('button', { class: diagMode === 'working' ? 'on' : '', text: L('mem.diag_working') });
      const bCalls = el('button', { class: diagMode === 'calls' ? 'on' : '', text: L('mem.diag_calls') });
      const bRaw = el('button', { class: diagMode === 'raw' ? 'on' : '', text: L('mem.diag_raw') });
      bWork.addEventListener('click', () => { if (cid) go(`/v1/views/c/${cid}/working`); });
      bCalls.addEventListener('click', () => go('/v1/inspector/calls'));
      bRaw.addEventListener('click', () => { if (cid) go(`/v1/inspector/c/${cid}`); });
      subHead.append(el('div', { class: 'diag-toggle' }, bWork, bCalls, bRaw));
    }
    memSubBar.replaceChildren(tabsRow, subHead);
  }

  function openMemorySub(sub: MemorySub, pushHistory = true): void {
    activeMemSub = sub;
    const cid = activeChatId ?? hubConversation;
    notesStudioView.style.display = 'none';
    settingsView.style.display = 'none';
    statusView.style.display = 'none';
    inspectorView.style.display = '';
    bar.style.display = 'none';
    shown = 'inspector';
    root.classList.add('wide');
    setPrimaryNav('memory');
    homeQuickBar.style.display = 'none';
    memSubBar.style.display = '';
    stopWorkerAuto();
    renderMemSubBar(sub, 'working');
    if (!cid) {
      inspbar.style.display = 'none';
      inspectorBody.replaceChildren(el('div', { class: 'card muted', text: L('mem.no_chat') }));
      return;
    }
    const target = sub === 'story' ? `/v1/views/c/${cid}/memory`
      : sub === 'explore' ? `/v1/views/c/${cid}/explore`
      : sub === 'attention' ? `/v1/views/c/${cid}/attention`
      : sub === 'map' ? `/v1/views/c/${cid}/map`
      : `/v1/views/c/${cid}/working`;
    if (pushHistory) go(target, null);
    else {
      pendingSection = null;
      void showInspector(target);
    }
  }

  function openNotesStudio(conversation: string | null): void {
    const cid = conversation ?? activeChatId ?? hubConversation;
    inspectorView.style.display = 'none';
    settingsView.style.display = 'none';
    statusView.style.display = 'none';
    notesStudioView.style.display = '';
    bar.style.display = 'none';
    root.classList.add('wide');
    setPrimaryNav('notes');
    if (!cid) {
      notesStudioView.replaceChildren(el('div', { class: 'card muted', text: L('notes.no_chat') }));
      return;
    }
    if (notesFor !== cid || !notesStudioView.childElementCount) {
      buildNotes(cid, notesStudioView, true);
    }
  }

  function syncShellForPath(path: string): void {
    if (!viewsOn) return;
    if (path.startsWith('/v1/views/hub')) {
      setPrimaryNav('home');
      homeQuickBar.style.display = '';
      memSubBar.style.display = 'none';
      inspbar.style.display = visited.length ? '' : 'none';
      void refreshHomeQuick();
      return;
    }
    if (path.startsWith('/v1/views/chats')) {
      setPrimaryNav('home');
      homeQuickBar.style.display = 'none';
      memSubBar.style.display = 'none';
      inspbar.style.display = '';
      return;
    }
    homeQuickBar.style.display = 'none';
    stopWorkerAuto();
    if (shown !== 'inspector') return;
    setPrimaryNav('memory');
    memSubBar.style.display = '';
    const isPerson = /\/(person|e)\//.test(path);
    inspbar.style.display = visited.length || isPerson ? '' : 'none';
    if (path.includes('/memory')) renderMemSubBar('story', 'working');
    else if (path.includes('/explore')) renderMemSubBar('explore', 'working');
    else if (path.includes('/attention')) renderMemSubBar('attention', 'working');
    else if (path.includes('/map')) renderMemSubBar('map', 'working');
    else if (path.includes('/working')) renderMemSubBar('diag', 'working');
    else if (path.startsWith('/v1/inspector/calls')) renderMemSubBar('diag', 'calls');
    else if (path.startsWith('/v1/inspector/c/')) {
      const isAttn = pendingSection === 's-attention' || activeMemSub === 'attention';
      renderMemSubBar(isAttn ? 'attention' : 'diag', isAttn ? 'working' : 'raw');
    } else {
      renderMemSubBar(activeMemSub, 'working');
    }
  }

  function selectPrimary(next: PrimaryTab): void {
    if (!viewsOn) {
      select(next === 'settings' ? 'settings' : next === 'home' ? 'status' : 'inspector');
      return;
    }
    closeChatPop();
    if (next === 'home') {
      void goHome();
      return;
    }
    if (next === 'memory') {
      openMemorySub(activeMemSub);
      return;
    }
    if (next === 'notes') {
      openNotesStudio(activeChatId ?? hubConversation);
      return;
    }
    select('settings');
  }

  function buildShell(): void {
    root.classList.add('shell-on');
    legacyHeader.style.display = 'none';
    tabs.style.display = 'none';

    const brand = el('button', { class: 'nmos-brand', 'aria-label': L('nav.home') },
      el('span', { class: 'nmos-logo' }, icon('brand', 18)),
      el('span', { text: 'NMOS' }));
    brand.addEventListener('click', () => selectPrimary('home'));

    chatBtnLabel = el('span', { class: 'chat-lbl', text: L('shell.no_chat') });
    const chatBtn = el('button', { class: 'chat-btn', 'aria-label': L('shell.switch_chat') },
      icon('chat', 14), chatBtnLabel, icon('chevronDown', 14));
    chatSearchInput = el('input', { type: 'search', placeholder: L('shell.search_chat'), 'aria-label': L('shell.search_chat') });
    chatSearchInput.addEventListener('input', () => renderChatOptions(chatSearchInput?.value ?? ''));
    chatListEl = el('div', { class: 'chat-list' });
    const allChatsBtn = el('button', { class: 'mini ghost', text: L('shell.chats_all') });
    allChatsBtn.addEventListener('click', () => {
      closeChatPop();
      notesStudioView.style.display = 'none';
      settingsView.style.display = 'none';
      statusView.style.display = 'none';
      inspectorView.style.display = '';
      bar.style.display = 'none';
      shown = 'inspector';
      go('/v1/views/chats');
    });
    chatPop = el('div', { class: 'chat-pop', style: 'display:none' },
      chatSearchInput, chatListEl, el('div', { class: 'chat-pop-foot' }, allChatsBtn));
    const chatPicker = el('div', { class: 'chat-picker' }, chatBtn, chatPop);
    chatBtn.addEventListener('click', (e) => { e.stopPropagation(); void openChatPop(); });
    chatPop.addEventListener('click', (e) => e.stopPropagation());

    const makeNavBtn = (key: PrimaryTab, ic: IconName, labelKey: StringKey, mobile = false): HTMLButtonElement => {
      const children: (Node | string)[] = [icon(ic, mobile ? 18 : 15), el('span', { text: L(labelKey) })];
      if (key === 'memory') {
        const badge = el('span', { class: 'nav-badge', text: '0', style: 'display:none' });
        attnBadges.push(badge);
        children.push(badge);
      }
      if (key === 'settings') {
        const dot = el('span', { class: 'dirty-dot', style: 'display:none' });
        settingsDirtyDots.push(dot);
        children.push(dot);
      }
      const btn = el('button', { 'data-nav': key }, ...children);
      btn.addEventListener('click', () => selectPrimary(key));
      const list = navButtons.get(key) ?? [];
      list.push(btn);
      navButtons.set(key, list);
      return btn;
    };

    const topNav = el('nav', { class: 'nmos-nav', 'aria-label': 'NMOS' },
      makeNavBtn('home', 'home', 'nav.home'),
      makeNavBtn('memory', 'book', 'nav.memory'),
      makeNavBtn('notes', 'feather', 'nav.notes'),
      makeNavBtn('settings', 'sliders', 'nav.settings'));

    const bottomNav = el('nav', { class: 'nmos-bottomnav', 'aria-label': 'NMOS' },
      makeNavBtn('home', 'home', 'nav.home', true),
      makeNavBtn('memory', 'book', 'nav.memory', true),
      makeNavBtn('notes', 'feather', 'nav.notes', true),
      makeNavBtn('settings', 'sliders', 'nav.settings', true));

    statusPill = el('button', { type: 'button', class: 'status-pill', title: L('shell.status_tip') },
      el('span', { class: 'dot' }), el('span', { class: 'st-txt', text: L('shell.status_ok') }));
    statusPill.addEventListener('click', () => {
      closeChatPop();
      if (!lastConnected) { selectPrimary('settings'); openGroup('connection'); return; }
      openDiag(lastStatusKind === 'err' || lastStatusKind === 'warn' ? 'calls' : 'working');
    });
    close.className = 'nmos-close ghost';
    close.replaceChildren(icon('close', 16));
    close.setAttribute('aria-label', L('close'));
    close.setAttribute('title', L('close'));

    const topbar = el('div', { class: 'nmos-topbar' },
      el('div', { class: 'nmos-topbar-in' },
        brand, chatPicker, topNav,
        el('div', { class: 'nmos-top-right' }, statusPill, language, close)));

    root.prepend(topbar);
    root.append(bottomNav);

    onDocClick = () => { if (chatPopOpen) closeChatPop(); };
    onDocKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      if (activeModalCancel) { activeModalCancel(); return; }
      if (chatPopOpen) { closeChatPop(); return; }
      const rpCancel = inspectorBody.querySelector<HTMLButtonElement>('.rp-form button:not(.primary)');
      if (rpCancel) { rpCancel.click(); return; }
      if (closing) { bar.querySelector<HTMLButtonElement>('button')?.click(); return; }
      close.click();
    };
    document.addEventListener('click', onDocClick);
    document.addEventListener('keydown', onDocKey);
  }

  function select(next: Tab): void {
    shown = next;
    notesStudioView.style.display = 'none';
    if (viewsOn && next === 'settings') {
      setPrimaryNav('settings');
      openGroup(currentGroup);
    }
    const views: [Tab, HTMLElement, HTMLElement][] = [
      ['status', statusView, tabStatus], ['inspector', inspectorView, tabInspector], ['settings', settingsView, tabSettings]];
    for (const [name, view, button] of views) {
      view.style.display = name === next ? '' : 'none';
      button.className = name === next ? 'on' : '';
    }
    bar.style.display = next === 'settings' ? '' : 'none';
    root.classList.toggle('wide', viewsOn || next === 'inspector');
    if (next === 'status') void refreshStatus();
    if (next === 'inspector') void showInspector();
  }
  tabStatus.addEventListener('click', () => select('status'));
  tabInspector.addEventListener('click', () => select('inspector'));
  tabSettings.addEventListener('click', () => select('settings'));

  /** What a hub block asks the plugin to do itself (PHASE-52 D1, PHASE-59): settings, backup, Author's Note studio. */
  function doAct(act: string): void {
    if (act === 'settings' || act === 'backup') {
      if (act === 'backup') currentGroup = 'backup';
      select('settings');
      if (act === 'backup') openGroup('backup');
      return;
    }
    if (act === 'retry') return void retryFrom(inspectorConversation(inspectorPath));
    if (act === 'notes') {
      const cid = activeChatId ?? hubConversation;
      if (viewsOn) {
        openNotesStudio(cid);
      } else if (cid) {
        notesCard.replaceChildren();
        buildNotes(cid);
        notesCard.style.display = '';
        notesCard.scrollIntoView({ block: 'start' });
      }
    }
  }
  /** The hub again, for the chat open in the host now (PHASE-52/59): from the brand, Home tab, or settings. */
  async function goHome(): Promise<void> {
    visited.length = 0;
    inspectorPath = await hubPath();
    select('inspector');
  }
  // --- settings in 2-column groups (PHASE-59 D5): This chat first, then Global settings -----------------------
  const GROUPS = ['chat', 'connection', 'models', 'memory', 'rules', 'display', 'backup'] as const;
  type Group = typeof GROUPS[number];
  const GROUP_ICONS: Record<Group, IconName> = {
    chat: 'chat', connection: 'plug', models: 'cpu', memory: 'database', rules: 'shield', display: 'eye', backup: 'archive',
  };
  const groupList = el('div', { class: 'groups' });
  const settingsPane = el('div', { class: 'settings-pane' });
  const settingsShell = el('div', { class: 'settings-shell' }, groupList, settingsPane);
  const chatPage = el('div', { 'data-group': 'chat', style: 'display:none' });
  const legacyActionBtns = actions.firstElementChild as HTMLElement;

  function restoreLegacyActions(): void {
    if (historyButton.parentElement !== legacyActionBtns) {
      legacyActionBtns.replaceChildren(retryButton, historyButton, cutButton, cutSummariesLabel, rebuildButton, exportButton,
        notesButton, deleteButton);
    }
  }

  function groupSettings(): void {
    const byTitle: Record<string, Group> = {
      [L('hud.title')]: 'display', [L('conn.title')]: 'connection', [L('llm.title')]: 'models', [L('emb.title')]: 'models',
      [L('rerank.title')]: 'models',
      [L('tune.title')]: 'memory', [L('trimset.title')]: 'memory', [L('rules.title')]: 'rules', [L('exp.title')]: 'backup',
      [L('rst.title')]: 'backup', [L('orph.title')]: 'backup',
    };
    const existingCards = Array.from(settingsView.children) as HTMLElement[];
    for (const card of existingCards) {
      const group = byTitle[card.querySelector('h2')?.textContent ?? ''];
      if (group) card.dataset.group = group;
    }
    statusView.dataset.group = 'connection';
    settingsPane.replaceChildren(chatPage, statusView, ...existingCards);
    settingsView.replaceChildren(settingsShell);

    const makeGroupBtn = (g: Group) => {
      const b = el('button', { class: 'group', 'data-group': g },
        icon(GROUP_ICONS[g], 16),
        el('span', { class: 'grp-txt' },
          el('b', { text: L(`grp.${g}` as StringKey) }),
          el('span', { class: 'sub', text: L(`grp.${g}_sub` as StringKey) })),
        el('span', { class: 'dirty-dot', style: 'display:none' }));
      b.addEventListener('click', () => openGroup(g));
      return b;
    };
    groupList.replaceChildren(
      el('div', { class: 'grp-label', text: L('set.scope_chat') }),
      makeGroupBtn('chat'),
      el('div', { class: 'grp-label', text: L('set.scope_global') }),
      ...GROUPS.filter((g) => g !== 'chat').map(makeGroupBtn),
    );
  }
  function pages(): HTMLElement[] {
    return Array.from(settingsPane.children).filter((x): x is HTMLElement => x instanceof HTMLElement && 'group' in x.dataset);
  }
  function openGroup(group: Group): void {
    currentGroup = group;
    for (const btn of Array.from(groupList.querySelectorAll<HTMLButtonElement>('button[data-group]'))) {
      btn.classList.toggle('on', btn.dataset.group === group);
    }
    for (const page of pages()) {
      page.style.display = page.dataset.group === group && (page !== rerankCard || rerankKnown) ? '' : 'none';
    }
    if (group === 'connection') void refreshStatus();
    if (group === 'chat') showChatPage();
  }
  /** This chat's tools in one place (PHASE-52 D6, PHASE-59 D5): ON/OFF switch, memory mode, status windows, and risk-badged maintenance. */
  function showChatPage(): void {
    const cid = activeChatId ?? hubConversation;
    if (!cid) {
      chatPage.replaceChildren(el('div', { class: 'card muted', text: L('grp.chat_none') }));
      return;
    }
    actionConversation = cid;
    disarm();
    const switchSlot = el('div');
    void deps.status().then((s) => chatCard(s.enabled, s.connected)).then((card) => {
      if (switchSlot.isConnected) switchSlot.replaceChildren(card);
    }).catch(() => {});

    const maintRow = (titleText: string, desc: StringKey, badgeKey: StringKey, badgeCls: string, btn: HTMLButtonElement, danger = false) =>
      el('div', { class: `maint-row${danger ? ' danger-row' : ''}` },
        el('div', { class: 'maint-info' },
          el('div', { class: 'maint-title' }, el('span', { text: titleText }), el('span', { class: `badge ${badgeCls}`, text: L(badgeKey) })),
          el('div', { class: 'maint-desc', text: L(desc) })),
        btn);

    const maintRows: HTMLElement[] = [];
    if (retryButton.style.display !== 'none') {
      maintRows.push(maintRow(L('act.retry'), 'set.act_retry_desc', 'set.badge_llm', 'b-llm', retryButton));
    }
    // PHASE-62 S3: a row for "read the cut turns again", filled once the sidecar says this chat has cut turns
    const cutSlot = el('div', { style: 'display:none' });
    void loadCut(cid).then((info) => {
      if (!info || !cutSlot.isConnected || actionConversation !== cid) return;
      cutSlot.replaceChildren(el('div', { class: 'maint-row' },
        el('div', { class: 'maint-info' },
          el('div', { class: 'maint-title' }, el('span', { text: L('act.cut') }), el('span', { class: 'badge b-llm', text: L('set.badge_llm') })),
          el('div', { class: 'maint-desc', text: L('set.act_cut_desc', { n: info.turns, low: count(info.low), high: count(info.high) }) }),
          cutSummariesLabel),
        cutButton));
      cutSlot.style.display = '';
    });
    maintRows.push(
      maintRow(L('act.history'), 'set.act_history_desc', 'set.badge_llm', 'b-llm', historyButton),
      cutSlot,
      maintRow(L('act.rebuild'), 'set.act_rebuild_desc', 'set.badge_warn', 'b-warn', rebuildButton),
      maintRow(L('exp.chat'), 'set.act_export_desc', 'set.badge_local', 'b-free', exportButton),
      maintRow(L('act.delete'), 'set.act_delete_desc', 'set.badge_danger', 'b-danger', deleteButton, true),
    );
    const maintCard = el('div', { class: 'card' },
      el('h2', { text: L('set.maint_title') }),
      el('p', { class: 'sub', text: L('set.maint_sub') }),
      el('div', { class: 'maint-list' }, ...maintRows),
      actionMsg);
    const pinsCard = el('div', { class: 'card' }, el('h2', { text: L('pins.title') }), el('p', { class: 'sub', text: L('pin.sub') }));
    const carryCard = el('div', { class: 'card', style: 'display:none' });
    const other = otherChatBanner();
    chatPage.replaceChildren(...(other ? [other] : []), switchSlot, modeCard, statusCard, pinsCard, carryCard, maintCard);
    void showPins(cid, pinsCard);
    void showCarry(cid, carryCard);
    void showMode(cid, loads);
    void showStatusWindows(cid, loads);
  }
  /** Carry another chat's memory (PHASE-60 S6, ADR 0085): preview before linking, 409 refresh, read again, two-tap unlink. */
  async function showCarry(conversation: string, card: HTMLElement, said?: StringKey): Promise<void> {
    const carryHead = () => [
      el('h2', { text: L('carry.title') }),
      el('p', { class: 'sub', text: L('carry.sub') }),
      el('p', { class: 'sub', text: L('carry.policy_note') }),
    ];
    let state: CarryState;
    try {
      const res = await deps.api<CarryState>('GET', `/v1/conversations/${conversation}/carry`, undefined, 15_000);
      if (!res || typeof res !== 'object' || !('in_force' in res)) {
        card.style.display = 'none';
        card.replaceChildren();
        return;
      }
      state = res;
    } catch (error) {
      if (!card.isConnected || actionConversation !== conversation) return;
      if (isCarryNotFound(error)) {
        card.style.display = 'none';
        card.replaceChildren();
        return;
      }
      const errMsg = el('div', { class: 'msg', role: 'status' });
      say(errMsg, carryErrorText(lang, error, errorText), 'err');
      card.replaceChildren(...carryHead(), errMsg);
      card.style.display = '';
      return;
    }
    if (!card.isConnected || actionConversation !== conversation) return;

    const msg = el('div', { class: 'msg', role: 'status' });
    if (said) say(msg, L(said), 'ok');
    const previewSpot = el('div');

    /** An `/entities` row as the regression fallback reads it; `excluded` is the exclusion's scope ('cast' | 'memory'). */
    type CarryEntity = { type?: string; name?: string; mentions?: number; persona?: boolean; excluded?: string | null };
    /** The sidecar's `carry._characters` over the source's entities: characters only, not the persona, not excluded from
     *  memory (a cast exclusion stays), most mentioned first, ties in the list's order. */
    const carryCharacters = (rows: CarryEntity[]): string[] => rows
      .filter((e) => e && e.type === 'character' && !e.persona && e.excluded !== 'memory' && typeof e.name === 'string')
      .map((e, i) => ({ name: String(e.name), mentions: Number(e.mentions) || 0, i }))
      .sort((a, b) => b.mentions - a.mentions || a.i - b.i)
      .map((e) => e.name);

    async function openPreview(
      trigger: HTMLButtonElement,
      req: { source_conversation_id: string; mode: CarryMode; entity_names: string[]; cutoff_turn: number | null },
      changed = false,
    ): Promise<void> {
      const round = nextRound(previewSpot);
      say(msg, '');
      trigger.disabled = true;
      // Regression needs 1-8 names; when none are picked yet, preview in continue mode first to list the source's characters.
      const discover = req.mode === 'regression' && req.entity_names.length === 0;
      const body: CarryRequestBody = {
        source_conversation_id: req.source_conversation_id,
        mode: discover ? 'continue' : req.mode,
        entity_names: discover ? [] : [...req.entity_names],
        cutoff_turn: req.cutoff_turn,
      };
      let first: CarryPreview | null = null;
      let chars: string[] = [];
      try {
        first = await deps.api<CarryPreview>('POST', `/v1/conversations/${conversation}/carry/preview`, body, 15_000);
        chars = first.characters ?? [];
      } catch (error) {
        if (previewRound.get(previewSpot) !== round) return;
        const refused = () => {
          say(msg, carryErrorText(lang, error, errorText), 'err');
          trigger.disabled = false;
        };
        // The discover preview reads the whole source and the sidecar caps that reading; a few names may still fit
        // under the cap, so a size refusal lists the source's characters from its entities instead.
        if (!discover || !carryRefusal(error instanceof Error ? error.message : String(error))) {
          refused();
          return;
        }
        let rows: unknown;
        try {
          rows = await deps.api<unknown>('GET', `/v1/conversations/${req.source_conversation_id}/entities`, undefined, 15_000);
        } catch {
          rows = null;
        }
        if (previewRound.get(previewSpot) !== round) return;
        if (!Array.isArray(rows)) {
          refused();
          return;
        }
        chars = carryCharacters(rows as CarryEntity[]);
      }
      if (previewRound.get(previewSpot) !== round) return;

      let active: CarryPreview | null = discover ? null : first;
      let pickedNames: string[] = discover ? [] : [...req.entity_names];
      const detailsSpot = el('div');
      const ok = el('button', { class: 'primary', text: L('carry.link_btn') });
      const cancel = el('button', { text: L('cancel') });
      ok.disabled = active === null;

      function renderDetails(pv: CarryPreview | null, loading = false): void {
        if (loading) {
          detailsSpot.replaceChildren(el('div', { class: 'muted', text: L('carry.loading') }));
          return;
        }
        if (!pv) {
          const hint = chars.length ? L('carry.pv_chars_pick') : L('carry.pv_chars_none');
          detailsSpot.replaceChildren(el('div', { class: 'muted', text: hint }));
          return;
        }
        const modeText = L(pv.mode === 'regression' ? 'carry.mode_regression' : 'carry.mode_continue');
        const headLine = L('carry.pv_source', {
          source: carrySourceLabel(pv.source),
          mode: modeText,
          cutoff: carryCutoffLabel(lang, pv.cutoff.turn),
        });
        const items: HTMLElement[] = [
          el('div', { text: headLine }),
          el('div', { text: carryCountsLine(lang, pv.counts) }),
        ];
        if (pv.first_lines.length) {
          items.push(
            el('div', { class: 'muted', style: 'margin-top:6px', text: L('carry.pv_lines') }),
            ...pv.first_lines.map((line) => el('div', { text: `· ${line}` })),
          );
        } else {
          items.push(el('div', { class: 'muted', text: L('carry.pv_lines_empty') }));
        }
        if (pv.replaces) items.push(el('div', { class: 'warn', style: 'margin-top:6px', text: L('carry.pv_replaces') }));
        detailsSpot.replaceChildren(...items);
      }

      const box = el('div', { class: 'preview' }, el('b', { text: L('carry.pv_title') }));
      if (changed) box.append(el('div', { class: 'warn', text: L('carry.changed') }));

      if (req.mode === 'regression') {
        const allChars = [...chars, ...pickedNames.filter((n) => !chars.includes(n))];
        box.append(el('div', { style: 'margin-top:6px;font-weight:500', text: L('carry.pv_chars') }));
        if (allChars.length) {
          const boxes: HTMLInputElement[] = [];
          const syncCap = () => {
            const count = boxes.filter((b) => b.checked).length;
            for (const b of boxes) b.disabled = !b.checked && count >= CARRY_MAX_NAMES;
          };
          const charList = el('div', { class: 'pins' }, ...allChars.map((name) => {
            const cb = el('input', { type: 'checkbox', value: name });
            cb.checked = pickedNames.includes(name);
            boxes.push(cb);
            cb.addEventListener('change', async () => {
              syncCap();
              const chosen = boxes.filter((b) => b.checked).map((b) => b.value);
              pickedNames = chosen;
              say(msg, '');
              if (chosen.length === 0) {
                nextRound(previewSpot);
                active = null;
                ok.disabled = true;
                renderDetails(null);
                return;
              }
              const subRound = nextRound(previewSpot);
              active = null;
              ok.disabled = true;
              renderDetails(null, true);
              try {
                const pv = await deps.api<CarryPreview>('POST', `/v1/conversations/${conversation}/carry/preview`, {
                  source_conversation_id: req.source_conversation_id,
                  mode: 'regression',
                  entity_names: chosen,
                  cutoff_turn: req.cutoff_turn,
                }, 15_000);
                if (previewRound.get(previewSpot) !== subRound) return;
                active = pv;
                renderDetails(pv);
                ok.disabled = false;
              } catch (error) {
                if (previewRound.get(previewSpot) !== subRound) return;
                renderDetails(null);
                say(msg, carryErrorText(lang, error, errorText), 'err');
              }
            });
            return el('label', { class: 'check' }, cb, el('span', { text: name }));
          }));
          syncCap();
          box.append(charList);
        }
      }

      renderDetails(active);
      cancel.addEventListener('click', () => {
        nextRound(previewSpot);
        previewSpot.replaceChildren();
        trigger.disabled = false;
        say(msg, '');
      });
      ok.addEventListener('click', async () => {
        if (!active) return;
        const chosenNames = req.mode === 'regression' ? [...pickedNames] : [];
        if (req.mode === 'regression' && chosenNames.length === 0) return;
        ok.disabled = true;
        say(msg, '');
        const linkBody: CarryRequestBody = {
          source_conversation_id: req.source_conversation_id,
          mode: req.mode,
          entity_names: chosenNames,
          cutoff_turn: req.cutoff_turn,
          expect: active.fingerprint,
        };
        try {
          await deps.api('POST', `/v1/conversations/${conversation}/carry`, linkBody, 15_000);
          previewSpot.replaceChildren();
          await showCarry(conversation, card, 'carry.linked');
        } catch (error) {
          if (isCarryConflict(error)) {
            void openPreview(trigger, {
              source_conversation_id: req.source_conversation_id,
              mode: req.mode,
              entity_names: chosenNames,
              cutoff_turn: req.cutoff_turn,
            }, true);
            return;
          }
          say(msg, carryErrorText(lang, error, errorText), 'err');
          ok.disabled = false;
        }
      });

      box.append(
        detailsSpot,
        el('p', { class: 'sub', style: 'margin-top:8px', text: L('carry.pv_notice') }),
        el('div', { class: 'btns' }, ok, cancel),
      );
      previewSpot.replaceChildren(box);
    }

    if (state.in_force) {
      const link = state.in_force;
      const modeText = L(link.mode === 'regression' ? 'carry.mode_regression' : 'carry.mode_continue');
      const lt = localTime(link.created_at, lang);
      const takenEl = el('div', { class: 'muted', text: L('carry.taken_at', { time: lt ? lt.text : link.created_at }) });
      if (lt) takenEl.title = lt.title;
      const sourceText = carrySourceLabel(link.source);
      const summaryLines: HTMLElement[] = [
        el('div', { class: 'line' },
          el('span', { class: 'badge b-info', text: L('carry.linked_badge') }),
          el('strong', { text: sourceText })),
        el('div', { text: `${modeText} · ${carryCutoffLabel(lang, link.cutoff_turn)}` }),
        el('div', {
          text: link.mode === 'regression'
            ? L('carry.only_remember', { names: link.entity_names.join(', ') })
            : L('carry.linked_continue', { source: sourceText }),
        }),
        takenEl,
      ];

      const readAgainBtn = el('button', { text: L('carry.read_again') });
      const unlinkBtn = el('button', { text: L('carry.unlink') });
      let unlinkArmed = false;
      let unlinkTimer = 0;
      const disarmUnlink = () => {
        window.clearTimeout(unlinkTimer);
        unlinkArmed = false;
        unlinkBtn.textContent = L('carry.unlink');
        unlinkBtn.className = '';
      };

      readAgainBtn.addEventListener('click', () => {
        disarmUnlink();
        void openPreview(readAgainBtn, {
          source_conversation_id: link.source_conversation_id,
          mode: link.mode,
          entity_names: [...link.entity_names],
          cutoff_turn: link.cutoff_turn,
        });
      });

      unlinkBtn.addEventListener('click', async () => {
        if (!unlinkArmed) {
          unlinkArmed = true;
          unlinkBtn.textContent = L('carry.unlink_confirm');
          unlinkBtn.className = 'danger';
          unlinkTimer = window.setTimeout(disarmUnlink, 6000);
          return;
        }
        disarmUnlink();
        nextRound(previewSpot);
        previewSpot.replaceChildren();
        readAgainBtn.disabled = true;
        unlinkBtn.disabled = true;
        say(msg, '');
        try {
          await deps.api('DELETE', `/v1/conversations/${conversation}/carry`, undefined, 15_000);
          await showCarry(conversation, card, 'carry.unlinked');
        } catch (error) {
          readAgainBtn.disabled = false;
          unlinkBtn.disabled = false;
          say(msg, carryErrorText(lang, error, errorText), 'err');
        }
      });

      card.replaceChildren(
        ...carryHead(),
        ...summaryLines,
        el('div', { class: 'btns' }, readAgainBtn, unlinkBtn),
        previewSpot,
        msg,
      );
      card.style.display = '';
      return;
    }

    if (!knownChats.length) {
      try {
        const rows = await deps.api<{
          id: string; host_character_name?: string | null; host_chat_name?: string | null;
          title?: string | null; messages?: number; message_count?: number;
        }[]>('GET', '/v1/conversations?host=pocketrisu', undefined, 5000);
        if (Array.isArray(rows) && rows.length) {
          knownChats = rows.map((r) => {
            const ch = (r.host_character_name ?? '').trim();
            const ti = (r.host_chat_name ?? r.title ?? '').trim();
            const name = ch && ti && ti !== ch ? `${ch} · ${ti}` : (ch || ti || r.id.slice(0, 8));
            const turns = typeof r.messages === 'number' ? r.messages
              : (typeof r.message_count === 'number' ? r.message_count : undefined);
            return { id: r.id, name, character: ch, title: ti, turns };
          });
        }
      } catch { /* keep empty list if chat listing fails */ }
      if (!card.isConnected || actionConversation !== conversation) return;
    }

    const choices = knownChats.filter((c) => c.id !== conversation);
    if (!choices.length) {
      card.replaceChildren(
        ...carryHead(),
        el('div', { class: 'muted', text: L('carry.no_other') }),
        msg,
      );
      card.style.display = '';
      return;
    }

    const sourceSelect = el('select', { 'aria-label': L('carry.source') },
      ...choices.map((c) => el('option', { value: c.id, text: c.name })));
    const radioName = `nmos-carry-mode-${conversation}`;
    const continueRadio = el('input', { type: 'radio', name: radioName, value: 'continue' });
    continueRadio.checked = true;
    const regressionRadio = el('input', { type: 'radio', name: radioName, value: 'regression' });
    const cutoffInput = el('input', {
      type: 'number', min: '0', step: '1',
      placeholder: L('carry.cutoff_placeholder'),
      'aria-label': L('carry.cutoff'),
    });
    const previewBtn = el('button', { class: 'primary', text: L('carry.preview_btn') });

    const resetPreview = () => {
      nextRound(previewSpot);
      previewSpot.replaceChildren();
      previewBtn.disabled = false;
      say(msg, '');
    };
    sourceSelect.addEventListener('change', resetPreview);
    continueRadio.addEventListener('change', resetPreview);
    regressionRadio.addEventListener('change', resetPreview);
    cutoffInput.addEventListener('input', resetPreview);

    previewBtn.addEventListener('click', () => {
      const parsed = parseCutoffTurn(cutoffInput.value);
      if (cutoffInput.validity?.badInput || !parsed.ok) {
        say(msg, L('carry.cutoff_invalid'), 'err');
        return;
      }
      const mode: CarryMode = regressionRadio.checked ? 'regression' : 'continue';
      void openPreview(previewBtn, {
        source_conversation_id: sourceSelect.value,
        mode,
        entity_names: [],
        cutoff_turn: parsed.value,
      });
    });

    card.replaceChildren(
      ...carryHead(),
      field(L('carry.source'), sourceSelect),
      el('label', { text: L('carry.mode') }),
      el('label', { class: 'check' }, continueRadio, el('strong', { text: L('carry.mode_continue') })),
      el('p', { class: 'sub', text: L('carry.mode_continue_desc') }),
      el('label', { class: 'check' }, regressionRadio, el('strong', { text: L('carry.mode_regression') })),
      el('p', { class: 'sub', text: L('carry.mode_regression_desc') }),
      field(L('carry.cutoff'), cutoffInput),
      el('div', { class: 'btns' }, previewBtn),
      previewSpot,
      msg,
    );
    card.style.display = '';
  }
  /** This chat's pinned characters (ADR 0087), each with its Unpin; a list that fails is said in the card only. */
  async function showPins(conversation: string, card: HTMLElement, said?: StringKey): Promise<void> {
    const head = [el('h2', { text: L('pins.title') }), el('p', { class: 'sub', text: L('pin.sub') })];
    const msg = el('div', { class: 'msg', role: 'status' });
    if (said) say(msg, L(said), 'ok');
    let rows: PinRow[];
    try {
      const list = await deps.api<PinRow[]>('GET', `/v1/conversations/${conversation}/entities`, undefined, 15_000);
      if (!Array.isArray(list)) throw new Error('not a list');
      rows = list;
    } catch {
      card.replaceChildren(...head, el('div', { class: 'muted', text: L('pins.failed') }));
      return;
    }
    const lines = rows.filter((e) => typeof e.pinned === 'string' && e.pinned).map((e) => {
      const unpin = el('button', { class: 'mini', text: L('pins.unpin') });
      unpin.addEventListener('click', async () => {
        unpin.disabled = true;
        say(msg, '');
        try {
          await deps.api('POST', `/v1/conversations/${conversation}/repairs/${e.pinned}/remove`, {}, 15_000);
          await showPins(conversation, card, 'pin.undone');
        } catch (error) {
          unpin.disabled = false;
          say(msg, errorText(lang, error), 'err');
        }
      });
      return el('div', { class: 'btns' }, el('span', { text: e.name }), unpin);
    });
    card.replaceChildren(...head, ...(lines.length ? lines : [el('div', { class: 'muted', text: L('pins.none') })]), msg);
  }
  /** Run a chat's failed jobs again from the working screen (PHASE-52 D5), as today's Retry failed does. */
  async function retryFrom(conversation: string | null): Promise<void> {
    if (!conversation) return;
    say(actionMsg, L('act.working'));
    try {
      const r = await deps.api<{ retried?: Record<string, number> }>('POST',
        `/v1/conversations/${conversation}/retry-failed`, {}, 30_000);
      const n = Object.values(r.retried ?? {}).reduce((a, b) => a + (Number(b) || 0), 0);
      say(actionMsg, n ? L('act.retry_done', { n }) : L('act.retry_none'), 'ok');
      if (n) deps.hud.background(conversation);
      await showInspector();
    } catch (error) { say(actionMsg, actionError(error), 'err'); }
  }
  /** The hub for the chat open in the host (PHASE-52/59): or an explicit chat picked in the top switcher. */
  async function hubPath(explicitConversation?: string): Promise<string> {
    let chat: string | null = null;
    let off = false;
    let allOff = false;
    try { ({ id: chat, off } = await deps.chat.current()); } catch { /* the hub says it does not know the chat */ }
    try { allOff = !(await deps.status()).enabled; } catch { /* the hub says nothing about the switch */ }
    const q = [
      explicitConversation ? `conversation=${encodeURIComponent(explicitConversation)}`
        : (chat ? `chat=${encodeURIComponent(chat)}` : ''),
      off ? 'off=true' : '',
      allOff ? 'all_off=true' : '',
      viewsOn ? 'compact=1' : '',
    ].filter(Boolean).join('&');
    return `/v1/views/hub${q ? `?${q}` : ''}`;
  }
  /** The sidecar's stylesheet for its screens, once per page; one that could load anything is refused. */
  async function viewsStyle(): Promise<void> {
    if (document.getElementById('nmos-views-style')) return;
    try {
      const r = await deps.api<{ css?: unknown }>('GET', '/v1/views/style', undefined, 5000);
      if (typeof r.css === 'string' && !/@import|url\s*\(/i.test(r.css)) {
        document.head.append(el('style', { id: 'nmos-views-style', text: r.css }));
      }
    } catch { /* the pages still read without it */ }
  }

  function applyTarget(target?: PanelTarget): boolean {
    if (!target) return false;
    if (target === 'connection') {
      select('settings');
      if (viewsOn) openGroup('connection');
      return true;
    }
    if (!viewsOn) {
      select('status');
      return true;
    }
    if (target === 'calls') {
      openDiag('calls');
      return true;
    }
    if (target === 'working') {
      if (activeChatId ?? hubConversation) {
        openDiag('working');
      } else {
        select('inspector');
        void showInspector(inspectorPath).then(() => {
          if (activeChatId ?? hubConversation) openDiag('working');
        });
      }
      return true;
    }
    return false;
  }

  function selectWithTarget(next: Tab, target?: PanelTarget): void {
    if (applyTarget(target)) return;
    select(next);
  }

  root.append(toastEl);
  document.body.append(root);
  // A sidecar with the new screens (PHASE-52/59) opens on its unified shell + hub; an older one keeps legacy tabs.
  try {
    const features = (await deps.status()).features;
    viewsOn = !!features?.views;
    mapOn = viewsOn && !!features?.map;
    graphOn = mapOn && !!features?.map_graph;
  } catch { viewsOn = false; }
  if (viewsOn) {
    await viewsStyle();
    inspectorPath = await hubPath();
    if (tab === 'status') tab = 'inspector';
    buildShell();
    groupSettings();
  }
  dirtyReady = true;
  if (!applyTarget(initialTarget)) select(tab);
  await loadAll();
  syncDirtyDots();
  return { root, select: selectWithTarget };
}
