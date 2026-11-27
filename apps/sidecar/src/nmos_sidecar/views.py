"""The panel's screens (PHASE-52), rendered by the sidecar: the hub first, then memory, a person, working and the chats.

They are HTML fragments the panel shows through its sanitizer (`inspector.ts` `safeFragment`), so they use only what it
keeps: `div`, `p`, `h1`, `h2`, `span`, `b`, `br`, `a`, `details`, `summary`; `class`, `title`, Inspector and view
links, and `data-act` with a fixed set of values for what the plugin itself does (settings, backup, the author's note).
No table, no inline script or style. The browser shows the same fragments as full pages (`full_page`), with one
exception: the memory map's browser page adds its drawing as inline SVG, which the panel's fragment never carries
(PHASE-55 Q3).

The stylesheet is one string the panel injects once (`/v1/views/style`): every rule starts with `.nmos`, the panel's
root, so it cannot reach the host's page.
"""

from __future__ import annotations

import re
from typing import Any

from . import tokens
from .facts import earlier, symmetric
from .inspector import (_act, _close, _corrections, _epistemic_acts, _exclude_marks, _fix, _forgot_what,
                        _guise_grouped, _knowledge, _repair_target, _repair_value, _secret_status, _step,
                        _t as _it, _turn, _undo, _v, _with, cond_extra, cond_label, fact_line_text,
                        feeling_detail, feeling_dot, happened_mark, happened_text, note_blocks, timestamp, turn_link)
from .summaries import content
from .threads import KINDS as THREAD_KINDS

# The hub's blocks are flex rows that always end flush: each block grows to fill what its row leaves (PHASE-52 D1, PHASE-59).
STYLE = """
.nmos .v{font-size:var(--t-body,16px);line-height:1.65;color:var(--c-text);max-width:1060px}
.nmos .v a{color:inherit;text-decoration:none}
.nmos .v-head{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:6px 14px;margin:0 0 16px}
.nmos .v-h1{font-size:var(--t-h1,20px);font-weight:600;margin:0;color:var(--c-text-strong);letter-spacing:-0.015em}
.nmos .v-cap{font-size:var(--t-caption,13px);color:var(--c-text-muted);background:var(--c-raised);border:1px solid var(--c-line);padding:2px 10px;border-radius:99px}
.nmos .v-cap:empty{display:none}
.nmos .v-blocks{display:flex;flex-wrap:wrap;gap:12px}
.nmos .v-block{display:flex;flex-direction:column;gap:4px;background:var(--c-surface);border-radius:14px;padding:16px 18px;min-height:94px;cursor:pointer;border:1px solid var(--c-line);flex:1 1 140px;min-width:0;box-sizing:border-box;transition:border-color .15s ease,background .15s ease,transform .15s ease}
.nmos .v-block:hover{border-color:var(--c-line-hover);background:var(--c-raised)}
.nmos .v-wide,.nmos .v-big{flex-basis:100%}
.nmos .v-wide{min-height:0;background:linear-gradient(135deg,rgba(79,209,139,0.08),var(--c-surface) 55%);border:1px solid rgba(79,209,139,0.26);border-left:4px solid var(--c-ok);border-radius:14px}
.nmos .v-wide.warn{background:linear-gradient(135deg,rgba(232,172,67,0.09),var(--c-surface) 55%);border-color:rgba(232,172,67,0.3);border-left-color:var(--c-warn)}
.nmos .v-wide.err{background:linear-gradient(135deg,rgba(240,93,94,0.10),var(--c-surface) 55%);border-color:rgba(240,93,94,0.32);border-left-color:var(--c-err)}
.nmos .v-wide.off,.nmos .v-wide.idle{background:var(--c-surface);border-color:var(--c-line-strong);border-left-color:var(--c-text-ghost)}
.nmos .v-big{background:linear-gradient(180deg,var(--c-raised),var(--c-surface));border-color:var(--c-line-strong)}
.nmos .v-block.v-attn{flex-basis:100%;min-height:0;background:linear-gradient(135deg,rgba(232,172,67,0.12),var(--c-surface) 60%);border-color:rgba(232,172,67,0.34);flex-direction:row;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:8px 14px;padding:13px 18px}
.nmos .v-block.v-notes{background:linear-gradient(135deg,rgba(167,139,250,0.10),var(--c-surface) 65%);border-color:rgba(167,139,250,0.26)}
.nmos .v-block.v-map-tile{background:linear-gradient(135deg,rgba(56,189,248,0.09),var(--c-surface) 65%);border-color:rgba(56,189,248,0.24)}
.nmos .v-bt{font-size:var(--t-body,16px);font-weight:600;color:var(--c-text-strong);letter-spacing:-0.01em}
.nmos .v-bs{font-size:var(--t-secondary,14px);color:var(--c-text-soft)}
.nmos .v-attn .v-bt{color:var(--c-warn)}
.nmos .v-attn .v-bs{font-weight:600;color:var(--c-warn);background:rgba(232,172,67,0.14);border:1px solid rgba(232,172,67,0.34);padding:2px 10px;border-radius:99px}
.nmos .v-now-list{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
.nmos .v-now{display:inline-flex;align-items:center;font-size:var(--t-caption,13px);color:var(--c-text-soft);background:var(--c-sunken);border:1px solid var(--c-line);padding:4px 10px;border-radius:8px;max-width:100%}
.nmos .v-th-list{display:flex;flex-direction:column;gap:5px;margin-top:10px;padding-top:10px;border-top:1px solid var(--c-line)}
.nmos .v-th-prev{display:flex;align-items:baseline;gap:8px;font-size:var(--t-caption,13px);color:var(--c-text-soft)}
.nmos .v-prog-wrap{display:flex;flex-direction:column;gap:6px;margin-top:10px}
.nmos .v-prog-row{display:flex;flex-direction:column;gap:4px}
.nmos .v-prog-head{display:flex;justify-content:space-between;font-size:var(--t-caption,13px);color:var(--c-text-muted)}
.nmos .v-prog{position:relative;height:6px;border-radius:99px;background:var(--c-sunken);border:1px solid var(--c-line);overflow:hidden;margin-top:6px}
.nmos .v-prog-fill{position:absolute;top:0;bottom:0;left:0;border-radius:99px;background:var(--c-accent);min-width:2px}
.nmos .v-prog-fill.ok{background:var(--c-ok)}
.nmos .v-prog-fill.warn{background:var(--c-warn)}
.nmos .v-doc-grid{display:block}
.nmos .v-chips{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 14px}
.nmos .v-chips a{display:inline-flex;align-items:center;justify-content:space-between;gap:6px;font-size:var(--t-caption,13px);padding:6px 11px;border-radius:9px;background:var(--c-surface);border:1px solid var(--c-line);color:var(--c-text-soft);transition:background .15s ease,border-color .15s ease,color .15s ease}
.nmos .v-chips a:hover{background:var(--c-raised);border-color:var(--c-line-hover);color:var(--c-text-strong)}
.nmos .v-chip-n{font-size:12px;color:var(--c-text-muted);background:var(--c-sunken);padding:0 6px;border-radius:99px}
.nmos .v-doc-main{min-width:0}
.nmos .v-sec{margin:0 0 16px;padding:16px 18px;background:var(--c-surface);border:1px solid var(--c-line);border-radius:14px}
.nmos .v-h2{font-size:var(--t-h2,17px);font-weight:600;margin:0 0 10px;color:var(--c-text-strong);display:flex;align-items:center;gap:8px;letter-spacing:-0.01em}
.nmos .v-h2.v-small{font-size:var(--t-secondary,14px);margin:14px 0 6px;color:var(--c-text-soft)}
.nmos .v-n{font-size:var(--t-caption,13px);font-weight:600;color:var(--c-text-muted);background:var(--c-raised);border:1px solid var(--c-line);padding:1px 8px;border-radius:99px;margin-left:2px}
.nmos .v-line{padding:11px 0;border-top:1px solid var(--c-line);transition:background .12s ease}
.nmos .v-line:first-of-type{border-top:0;padding-top:4px}
.nmos .v-line .rp{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin:8px 0 0;opacity:.88}
.nmos .v-line.open .rp,.nmos .v-line:hover .rp{opacity:1}
.nmos .v-line .rp .rp-ask{font-size:var(--t-caption,13px);color:var(--c-text-muted);margin-right:2px}
.nmos .v-meta{font-size:var(--t-caption,13px);color:var(--c-text-muted);margin-top:4px;line-height:1.5}
.nmos .v-tag{display:inline-flex;align-items:center;font-size:12px;font-weight:550;padding:1px 8px;border-radius:99px;margin-right:6px;background:rgba(146,148,160,0.11);border:1px solid rgba(146,148,160,0.22);color:var(--c-text-muted);cursor:default;user-select:text;vertical-align:1px}
.nmos .v .chip{display:inline-flex;align-items:center;font-size:12px;font-weight:500;padding:1px 8px;border-radius:99px;background:rgba(146,148,160,0.10);border:1px solid rgba(255,255,255,0.07);color:var(--c-text-muted);cursor:default;user-select:text;vertical-align:middle}
.nmos .v-tag.k-promise{background:rgba(74,106,245,0.14);border-color:rgba(74,106,245,0.34);color:var(--c-link)}
.nmos .v-tag.k-goal{background:rgba(79,209,139,0.12);border-color:rgba(79,209,139,0.32);color:var(--c-ok)}
.nmos .v-tag.k-threat{background:rgba(240,93,94,0.14);border-color:rgba(240,93,94,0.34);color:var(--c-err)}
.nmos .v-tag.k-question{background:rgba(167,139,250,0.14);border-color:rgba(167,139,250,0.34);color:var(--c-violet)}
.nmos .v-tag.k-debt{background:rgba(232,172,67,0.14);border-color:rgba(232,172,67,0.34);color:var(--c-warn)}
.nmos .v-tag.k-echo{background:rgba(79,209,139,0.12);border-color:rgba(79,209,139,0.3);color:var(--c-ok);margin-right:0}
.nmos .v-diff{display:inline-flex;flex-wrap:wrap;align-items:center;gap:6px}
.nmos .v-diff-old{background:rgba(240,93,94,0.10);color:var(--c-text-soft);padding:1px 7px;border-radius:6px;text-decoration:line-through}
.nmos .v-diff-new{background:rgba(232,172,67,0.13);color:var(--c-warn);padding:1px 7px;border-radius:6px;font-weight:600}
.nmos .v a.v-name{color:var(--c-link);font-weight:600}
.nmos .v a.v-name:hover{text-decoration:underline}
.nmos .v a.v-src{color:var(--c-link)}
.nmos .v a.v-src:hover{text-decoration:underline}
.nmos .v-text{color:var(--c-text-soft);margin:0}
.nmos .v-note{font-size:var(--t-caption,13px);color:var(--c-text-muted);margin:8px 0 0}
.nmos .v-more>summary{cursor:pointer;list-style:none;font-size:var(--t-secondary,14px);color:var(--c-link);padding:8px 0 2px;font-weight:500}
.nmos .v-more>summary::-webkit-details-marker{display:none}
.nmos .v-mini{position:relative;height:24px;margin:10px 7px 4px}
.nmos .v-mini .v-axis{position:absolute;left:0;right:0;top:11px;border-top:2px solid var(--c-line-strong)}
.nmos .v-pin{position:absolute;top:9px;width:6px;height:6px;margin-left:-3px;border-radius:50%;background:var(--c-text-faint)}
.nmos .v-pin.major{top:5px;width:14px;height:14px;margin-left:-7px;box-sizing:border-box;border:2px solid var(--c-link);background:var(--c-bg);box-shadow:0 0 8px rgba(74,106,245,0.45)}
.nmos .v-ev{display:flex;gap:10px;align-items:flex-start;padding:9px 0;border-top:1px solid var(--c-line)}
.nmos .v-ev .v-t{flex:none;min-width:52px;font-size:var(--t-caption,13px);color:var(--c-text-muted);padding-top:3px;font-variant-numeric:tabular-nums}
.nmos .v-ev .v-d{flex:none;width:8px;height:8px;margin:9px 2px 0;border-radius:50%;background:var(--c-text-faint)}
.nmos .v-ev.major .v-d{width:12px;height:12px;margin:7px 0 0;box-sizing:border-box;border:2px solid var(--c-link);background:transparent}
.nmos .v-ev .v-x{color:var(--c-text-soft);min-width:0} .nmos .v-ev.major .v-x{color:var(--c-text-strong);font-weight:500}
.nmos .v-ends{display:flex;justify-content:space-between;font-size:var(--t-caption,13px);color:var(--c-text-muted)}
.nmos .v-warn{color:var(--c-warn)}
.nmos .fd{display:inline-block;width:8px;height:8px;border-radius:50%;margin:0 5px 1px 0;vertical-align:middle}
.nmos .fd.pos{background:var(--c-ok)} .nmos .fd.neg{background:var(--c-err)} .nmos .fd.mix{background:var(--c-warn)}
.nmos .v-filter input{width:100%;margin:0 0 12px}
.nmos .v-chat{padding:12px 14px;margin-bottom:8px;border:1px solid var(--c-line);border-radius:12px;background:var(--c-surface)}
.nmos .v-chat:first-of-type{border-top:1px solid var(--c-line);padding-top:12px}
.nmos .v-chat:hover{border-color:var(--c-line-hover);background:var(--c-raised)}
.nmos .v-foot{margin:20px 0 0;padding-top:12px;border-top:1px solid var(--c-line);font-size:var(--t-caption,13px);color:var(--c-text-muted);display:flex;flex-wrap:wrap;gap:6px 12px}
.nmos .v-foot a{color:var(--c-link)}
.nmos .v-stack{position:relative;height:10px;margin:8px 0 4px;border-radius:99px;overflow:hidden;background:var(--c-sunken);border:1px solid var(--c-line)}
.nmos .v-seg{position:absolute;top:0;bottom:0}
.nmos .v-seg.setting{background:var(--c-text-ghost)} .nmos .v-seg.over{background:var(--c-warn)}
.nmos .v-seg.story{background:var(--c-link)} .nmos .v-seg.owner{background:var(--c-ok)}
.nmos .g-m{color:var(--c-text-muted)} .nmos .g-m.story{color:var(--c-link)}
.nmos .g-m.changed,.nmos .g-m.over{color:var(--c-warn)} .nmos .g-m.owner{color:var(--c-ok)}
.nmos .v-graph{margin:10px 0 6px}
.nmos .v-graph svg{display:block;margin:0 auto;max-width:100%;height:auto;max-height:90vh}
.nmos .v-graph.one .g-t{font-size:20px}
.nmos .g-e{stroke:var(--c-text-ghost);stroke-width:1.5;vector-effect:non-scaling-stroke} .nmos .g-e.story{stroke:var(--c-link)}
.nmos .g-e.changed{stroke:var(--c-warn)} .nmos .g-e.split{stroke:var(--c-text-muted);stroke-dasharray:5 4}
.nmos .g-n{fill:var(--c-text-faint)} .nmos .g-n.lead{fill:var(--c-text-strong)}
.nmos .g-n.group,.nmos .g-n.place{fill:var(--c-bg);stroke:var(--c-text-muted);stroke-width:2}
.nmos .g-t{fill:var(--c-text-soft);font-size:16px} .nmos .g-t.lead{fill:var(--c-text-strong);font-weight:600}
.nmos svg.g-panel{display:block;width:100%;height:min(62vh,480px);touch-action:none;user-select:none;-webkit-user-select:none;background:var(--c-sunken);border:1px solid var(--c-line);border-radius:14px}
.nmos svg.g-panel .g-e.on{stroke-width:2.5}
.nmos svg.g-panel.sel .g-e:not(.on){opacity:.12} .nmos svg.g-panel.sel .g-node:not(.on){opacity:.3}
.nmos .v-graph-btns{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:8px 0 0}
.nmos .v-dash-grid{display:grid;grid-template-columns:1fr;gap:12px}
.nmos .v-dash-card{background:var(--c-surface);border:1px solid var(--c-line);border-radius:14px;padding:16px 18px;display:flex;flex-direction:column;gap:8px;min-width:0}
.nmos .v-dash-card.v-wide{border-left:4px solid var(--c-ok)}
.nmos .v-dash-card.v-wide.warn{border-left-color:var(--c-warn)}
.nmos .v-dash-card.v-wide.err{border-left-color:var(--c-err)}
.nmos .v-dash-card.v-wide.off,.nmos .v-dash-card.v-wide.idle{border-left-color:var(--c-text-ghost)}
.nmos .v-dash-head{display:flex;align-items:center;justify-content:space-between;gap:8px;flex-wrap:wrap}
.nmos .v-dash-title{font-size:15.5px;font-weight:650;color:var(--c-text-strong);letter-spacing:-0.01em}
.nmos .v-dash-links{display:flex;flex-wrap:wrap;gap:8px;margin-top:6px}
.nmos .v-pill-link{display:inline-flex;align-items:center;gap:5px;font-size:13px;font-weight:550;color:var(--c-link);background:rgba(74,106,245,0.10);border:1px solid rgba(74,106,245,0.28);padding:4px 11px;border-radius:99px;transition:background .15s ease,border-color .15s ease}
.nmos .v-pill-link:hover{background:rgba(74,106,245,0.18);border-color:rgba(74,106,245,0.45)}
.nmos .v-snap-line{font-size:13.5px;color:var(--c-text-soft);padding:6px 0;border-top:1px solid var(--c-line);word-break:break-word}
.nmos .v-snap-line:first-of-type{border-top:0;padding-top:2px}
.nmos .v-exp-toolbar-slot{margin:0 0 14px}
.nmos .v-exp-list{display:flex;flex-direction:column;gap:9px}
.nmos .v-card{background:var(--c-sunken);border:1px solid var(--c-line);border-radius:11px;padding:12px 14px;min-width:0;transition:border-color .15s ease}
.nmos .v-card:hover{border-color:var(--c-line-hover)}
.nmos .v-card.v-card-warn{border-color:rgba(232,172,67,0.36);background:linear-gradient(135deg,rgba(232,172,67,0.06),var(--c-sunken) 55%)}
.nmos .v-card-top{display:flex;align-items:flex-start;justify-content:space-between;gap:8px;flex-wrap:wrap}
.nmos .v-card-check{display:inline-flex;align-items:center;gap:6px;flex:none;margin-top:2px}
.nmos .v-card-badges{display:flex;flex-wrap:wrap;align-items:center;gap:5px;flex:1;min-width:0}
.nmos .v-card-turn{font-size:12px;color:var(--c-text-muted);white-space:nowrap;font-variant-numeric:tabular-nums;margin-left:auto}
.nmos .v-card-turn a{color:var(--c-link);font-weight:500}
.nmos .v-card-turn a:hover{text-decoration:underline}
.nmos .v-card-main{font-size:14.5px;line-height:1.55;color:var(--c-text-strong);margin-top:5px;word-break:break-word;min-width:0}
.nmos .v-card-sub{font-size:13px;color:var(--c-text-muted);margin-top:4px;line-height:1.5;word-break:break-word}
.nmos .v-card-acts{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin-top:9px;padding-top:8px;border-top:1px solid var(--c-line)}
.nmos .v-tag.k-setting{background:rgba(146,148,160,0.12);border-color:rgba(146,148,160,0.3);color:var(--c-text-muted)}
.nmos .v-tag.k-owner{background:rgba(79,209,139,0.13);border-color:rgba(79,209,139,0.34);color:var(--c-ok)}
.nmos .v-tag.k-locked{background:rgba(232,172,67,0.14);border-color:rgba(232,172,67,0.36);color:var(--c-warn)}
.nmos .v-tag.k-warn{background:rgba(232,172,67,0.14);border-color:rgba(232,172,67,0.36);color:var(--c-warn)}
.nmos .v-tag.k-err{background:rgba(240,93,94,0.14);border-color:rgba(240,93,94,0.36);color:var(--c-err)}
.nmos .v-tag.k-info{background:rgba(56,189,248,0.12);border-color:rgba(56,189,248,0.32);color:var(--c-cyan)}
.nmos .v-edit{margin-top:8px;padding-top:7px;border-top:1px dashed var(--c-line)}
.nmos .v-edit>summary{cursor:pointer;list-style:none;font-size:12.5px;font-weight:550;color:var(--c-text-soft);background:var(--c-raised);border:1px solid var(--c-line-strong);border-radius:7px;padding:4px 10px;display:inline-flex;align-items:center;gap:5px;user-select:none;box-shadow:0 1px 2px rgba(0,0,0,0.22);transition:background .15s ease,border-color .15s ease,color .15s ease}
.nmos .v-edit>summary::-webkit-details-marker{display:none}
.nmos .v-edit>summary::before{content:"\\25B8";font-size:11px;color:var(--c-text-muted);line-height:1}
.nmos .v-edit[open]>summary::before{content:"\\25BE";color:var(--c-link)}
.nmos .v-edit>summary:hover,.nmos .v-edit[open]>summary{background:rgba(74,106,245,0.14);border-color:rgba(74,106,245,0.42);color:var(--c-text-strong)}
.nmos .v-edit-body{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin-top:8px}
.nmos .v-edit-row{width:100%;display:flex;flex-wrap:wrap;align-items:center;gap:6px;padding:6px 0;border-top:1px solid var(--c-line)}
.nmos .v-edit-row:first-child{border-top:0;padding-top:0}
.nmos .v-edit-lbl{font-size:12.5px;color:var(--c-text-soft);margin-right:4px;word-break:break-word}
.nmos .v-note-box{margin-top:7px;padding:7px 10px;border-radius:8px;background:rgba(79,209,139,0.08);border:1px solid rgba(79,209,139,0.24);font-size:13.5px;line-height:1.5;color:var(--c-text-strong);display:flex;align-items:baseline;gap:6px;flex-wrap:wrap;word-break:break-word}
.nmos .v-diff-block{display:flex;flex-direction:column;gap:5px;margin-top:6px}
.nmos .v-diff-row{font-size:13.5px;line-height:1.5;padding:6px 10px;border-radius:8px;background:var(--c-surface);border:1px solid var(--c-line);word-break:break-word}
.nmos .v-empty{padding:26px 18px;text-align:center;color:var(--c-text-muted);font-size:14.5px;border:1px dashed var(--c-line-strong);border-radius:12px;background:var(--c-sunken)}
@media (min-width:700px){.nmos .v-block:not(.v-wide):not(.v-big):not(.v-attn){flex-basis:240px}}
@media (min-width:760px){.nmos .v-dash-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.nmos .v-dash-full{grid-column:1/-1}}
@media (min-width:860px){.nmos .v-doc-grid{display:grid;grid-template-columns:196px minmax(0,1fr);gap:18px;align-items:start}.nmos .v-doc-grid .v-chips{position:sticky;top:76px;flex-direction:column;flex-wrap:nowrap;margin:0;padding:10px;background:var(--c-surface);border:1px solid var(--c-line);border-radius:14px}.nmos .v-doc-grid .v-chips a{width:100%;padding:7px 10px;background:transparent;border-color:transparent}.nmos .v-doc-grid .v-chips a:hover{background:var(--c-raised);border-color:var(--c-line)}}
@media (max-width:699px){.nmos .v-graph.whole{display:none}}
"""

T: dict[str, tuple[str, str]] = {
    "s-told": ("누가 누구에게 들었나", "Who told whom"),
    "told_about": ("{who}에 대해", "about {who}"),
    # a chat that carries another chat's memory (PHASE-60 S6)
    "s-carry": ("이전 채팅에서 이어받은 기억", "Carried from an earlier chat"),
    "carry_from": ("{source}에서 이어받음 · 이 채팅의 턴이 아님", "Carried from {source} · not this chat's own turns"),
    "carry_regress": ("이전 타임라인 · {names}만 기억", "Earlier timeline · remembered only by {names}"),
    "carry_upto": ("t{t}까지", "up to t{t}"),
    "carry_turn": ("이전 채팅 t{t}", "earlier chat t{t}"),
    "carry_left": ("외 {n}줄", "{n} more"),
    "carry_forgot": ("이 채팅은 이전 타임라인을 이어받았지만, 이 인물은 그것을 기억하지 않습니다",
                     "This chat carries an earlier timeline, which this person does not remember"),
    "carry_aka": ("다른 이름", "also called"), "carry_has": ("가진 것", "has"), "carry_told": ("말해 줌", "told"),
    "carry_believes": ("믿음", "believes"),
    "carry_not": ("(아님)", "(not)"),
    "carried": ("이어받음", "carried"),
    "ok": ("작동 중", "Working"),
    "warn": ("확인이 필요해요", "Needs a look"),
    "err": ("작동하지 않아요", "Not working"),
    "off": ("꺼져 있음", "Off"),
    "idle": ("연결됨", "Connected"),
    "placed": ("이번 답장에 기억이 들어갔어요 · {s}초 · {n}줄", "This reply got its memory · {s}s · {n} lines"),
    "not_placed": ("최근 답장에 들어간 기억이 없어요", "The last reply went without memory"),
    "no_reply": ("아직 이 채팅에서 받은 요청이 없어요", "No request from this chat yet"),
    "failed": ("실패 {f} · 대기 {p}", "Failed {f} · waiting {p}"),
    "no_extraction": ("사실 추출 꺼짐 (모델 없음)", "fact extraction off (no model)"),
    "off_chat": ("이 채팅은 NMOS가 꺼져 있어요", "NMOS is off for this chat"),
    "off_all": ("NMOS가 전체적으로 꺼져 있어요", "NMOS is off for every chat"),
    "unknown": ("아직 이 채팅의 기록이 없어요", "NMOS has no record of this chat yet"),
    "memory": ("기억", "Memory"),
    "memory_sub": ("인물 {c} · 열린 일 {o} · 바뀐 설정 {g}", "{c} characters · {o} open threads · {g} changed"),
    "attention": ("확인 필요", "Needs a look"),
    "notes": ("작가의 노트", "Author's note"),
    "notes_sub": ("이 채팅의 정리 만들기", "Make this chat's note"),
    "usage": ("사용량", "Usage"),
    "usage_sub": ("모델 호출 {n}", "{n} model calls"),
    "settings": ("설정", "Settings"),
    "settings_sub": ("모델 · 기억 · 상태창 · 이 채팅", "Models · memory · status windows · this chat"),
    "backup": ("백업", "Backup"),
    "backup_sub": ("내보내기 · 복원", "Export · restore"),
    "chats": ("다른 채팅", "Other chats"),
    "chats_sub": ("NMOS가 아는 채팅 {n}", "{n} chats NMOS knows"),
    "s-now": ("지금", "Now"),
    "s-open": ("열린 일", "Open threads"),
    "s-people": ("사람들", "People"),
    "s-sofar": ("지금까지", "So far"),
    "s-secrets": ("비밀", "Secrets"),
    "s-changed": ("바뀐 설정", "Changed from the setting"),
    # extract-v21's beliefs and forgettings (PHASE-66 part 5); a chat without them never shows these sections
    "s-beliefs": ("믿음", "Beliefs"), "s-forgotten": ("잊은 것", "Forgotten"),
    "b_held": ("믿는 중", "held"), "b_ended": ("끝남: {what}", "ended: {what}"),
    "f_all": ("모든 기억", "everything"), "f_since": ("t{n}부터의 기억", "everything since t{n}"),
    "f_withdrew": ("거둬들인 것 {n}", "{n} withdrawn"),
    "more": ("{n}개 더 보기", "{n} more"),
    "stale": ("한동안 언급 없는 열린 일 {n}개는 여기 넣지 않았어요. 자세히에서 확인하거나 닫을 수 있어요.",
              "{n} open threads not mentioned for a while are left out here; check or close them in details."),
    "since": ("t{t}부터", "since t{t}"),
    "hz.scene": ("이번 장면", "this scene"), "hz.arc": ("이야기 줄기", "storyline"), "hz.lasting": ("오래 감", "lasting"),
    "none_yet": ("아직 없어요", "Nothing yet"),
    "kept": ("{who}에게 숨김", "kept from {who}"),
    "by": ("{who}이(가) 앎", "known by {who}"),
    "was": ("설정 {old} → 지금 {new}", "setting {old} → now {new}"),
    "story": ("지금까지의 이야기", "The story so far"),
    "scenes": ("장면 요약 {n}개", "{n} scene summaries"),
    "next_summary": ("다음 장면 요약 (t{a}–{b}): t{at} 응답 후 자동 작성 · {n}턴 남음",
                     "Next scene summary (t{a}–{b}): written after t{at} · {n} turns left"),
    "next_summary_one": ("다음 장면 요약 (t{a}–{b}): t{at} 응답 후 자동 작성 · 1턴 남음",
                         "Next scene summary (t{a}–{b}): written after t{at} · 1 turn left"),
    "facts": ("모든 사실 {n}", "All facts {n}"),
    "details": ("자세히", "Details"),
    "s-rels": ("관계", "Relationships"),
    "s-threads": ("약속 · 목표", "Promises and goals"),
    "s-knows": ("아는 것 · 모르는 것", "Knows and does not know"),
    "s-time": ("시간축", "Timeline"),
    "aka": ("다른 이름: {names}", "Also called: {names}"),
    "knows": ("알고 있음", "knows"),
    "unaware": ("모름 · {who}이(가) 숨김", "does not know · kept by {who}"),
    "back_memory": ("기억으로", "Back to memory"),
    "not_char": ("캐릭터가 아닌가요? 몬스터나 상태창 봇이라면 인물 목록에서 뺄 수 있어요.",
                 "Not a character? A monster or a status-window bot can leave the cast."),
    "is_not_char": ("캐릭터 아님으로 표시됨 · 되돌리기는 자세히의 수정 목록에서", "Marked not a character · undo it in details, under repairs"),
    "tl_hint": ("굵은 원은 큰 사건이나 관계 변화예요. 위 막대는 그 일들이 언제쯤이었는지 보여줘요.",
                "Rings are major events or relationship changes; the bar above shows when they happened."),
    "now_turn": ("지금 t{t}", "now t{t}"),
    "s-reply": ("이번 답장", "This reply"),
    "s-sent": ("방금 들어간 기억", "The memory just sent"),
    "s-work": ("처리", "Processing"),
    "s-usage": ("사용량", "Usage"),
    "reply_ok": ("기억이 들어갔어요 · {n}줄 · 약 {tok}토큰 · {s}초", "Memory went in · {n} lines · about {tok} tokens · {s}s"),
    "reply_none": ("이 답장에는 들어간 기억이 없어요", "No memory went into this reply"),
    "echoed": ("답장에 반영된 것 같아요", "the reply seems to use it"),
    "k_state": ("상태", "Status"), "k_summary": ("이야기 요약", "Story"), "k_cast": ("등장인물", "Cast"),
    "k_thread": ("약속 · 목표", "Promises and goals"), "k_fact": ("사실", "Facts"), "k_claim": ("주장", "Claims"),
    "k_secret": ("비밀", "Secrets"), "k_excerpt": ("원문 발췌", "Excerpts"), "k_quote": ("인용", "Quotes"),
    "w_extraction": ("사실 추출", "Fact extraction"), "w_embeddings": ("검색용 임베딩", "Search embeddings"),
    "w_summaries": ("장면 요약", "Scene summaries"), "w_canon": ("설정(원전) 읽기", "Reading the setting"),
    "w_counts": ("실패 {f} · 대기 {p}", "failed {f} · waiting {p}"),
    "w_made": ("{n}개 만듦", "{n} made"),
    "retry": ("실패한 작업 다시 시도", "Retry failed"),
    "c_title": ("다른 채팅", "Other chats"),
    "c_open": ("지금 열린 채팅", "open now"),
    "c_msgs": ("메시지 {n}", "{n} messages"),
    "c_failed": ("실패 {n}", "{n} failed"),
    "c_unnamed": ("(이름 없는 채팅)", "(unnamed chat)"),
    "u_calls": ("모델 호출", "Model calls"), "u_tokens": ("토큰 (입력 · 출력)", "Tokens (in · out)"),
    "promise": ("약속", "promise"), "goal": ("목표", "goal"), "question": ("질문", "question"),
    "threat": ("위협", "threat"), "debt": ("빚", "debt"),
    "located_in": ("위치", "location"), "has_status": ("상태", "status"), "relationship": ("관계", "relationship"),
    "role_toward": ("역할", "role"), "feels_toward": ("감정", "feels"), "addresses": ("호칭", "calls"),
    "possesses": ("소지자", "held by"), "destroyed": ("소멸", "destroyed"),
    # extract-v21's own predicates (PHASE-66 part 5); a chat without them never meets these words
    "vital_status": ("생사", "vital status"), "lives_in": ("사는 곳", "lives in"),
    "cover_identity": ("위장 신분", "cover identity"), "disguised_as": ("변장", "disguised as"),
    "holds_rank": ("직위", "rank"), "contained_in": ("안에 있음", "inside"),
    # the memory map (PHASE-55)
    "map": ("기억 지도", "Memory map"),
    "map_sub": ("출처 · 관계 · 사건", "Sources · ties · events"),
    "s-src": ("어디서 왔나", "Where it came from"),
    "s-ties": ("누가 누구와", "Who is tied to whom"),
    "s-events": ("무슨 일이 있었나", "What happened"),
    "s-depth": ("사건 기록", "What an event record holds"),
    "src.setting": ("설정만", "setting only"), "src.over": ("설정 위에 이야기", "story over the setting"),
    "src.story": ("이야기만", "story only"), "src.owner": ("직접 고침", "corrected by you"),
    "src_head": ("지금 사실 {n}개 · 설정에서만 {a}% · 이야기에서 {b}%", "{n} facts now · {a}% the setting's only · {b}% from the story"),
    "src_turn": ("이야기에서 온 지금 사실: 한 턴에 약 {x}개 · t0–t{last}", "Facts from the story now: about {x} a turn · t0–t{last}"),
    "mk.setting": ("설정", "setting"), "mk.story": ("이야기", "story"), "mk.changed": ("설정에서 바뀜", "changed from the setting"),
    "you": ("나", "you"),
    "g_group": ("소속", "Groups"), "g_place": ("있는 곳", "Places"),
    "member": ("소속", "member of"), "here": ("위치", "is at"),
    "suspect": ("한 사람일지도?", "Maybe one person?"),
    "suspect_meta": ("이름이 겹쳐요 · 같은 사람이면 인물 화면의 자세히에서 합칠 수 있어요",
                     "The names overlap; if they are one person, join them under the person's details"),
    "no_ties": ("아직 관계가 없는 인물 {n}명은 넣지 않았어요", "{n} characters with no ties yet are left out"),
    "left_out": ("인물에서 뺀 이름 {n}개는 그리지 않았어요", "{n} names left out of the cast are not drawn"),
    "drawn_left": ("그림에서 뺀 것: {what}", "Left out of the drawing: {what}"),
    "n_character": ("인물 {n}", "{n} characters"), "n_group": ("소속 {n}", "{n} groups"), "n_place": ("장소 {n}", "{n} places"),
    "show_all": ("전체 보기", "Show all"), "show_less": ("줄여 보기", "Show fewer"),
    "whole_map": ("전체 지도로", "Back to the whole map"), "focus": ("{name} 중심", "Around {name}"),
    "sheet": ("인물 화면", "Their sheet"),
    "legend": ("선: 회색 설정 · 파랑 이야기 · 주황 설정에서 바뀜 · 점선 한 사람일지도",
               "Lines: grey setting · blue story · orange changed from the setting · dashed maybe one person"),
    "panel_graph": ("그림은 브라우저에서 이 화면을 열면 보여요: /views/c/{cid}/map",
                    "The drawing shows when this screen is opened in a browser: /views/c/{cid}/map"),
    "g_fit": ("맞춤", "Fit"), "g_tap": ("한 번 더 누르면 이 사람 중심 지도로 가요", "Tap again for this person's own map"),
    "g_ties": ("관계 {n}", "{n} ties"),
    "with": ("함께: {who}", "with {who}"), "because": ("이유: {why}", "because {why}"),
    "ev_span": ("t{lo}–t{hi} · 사건 {n}", "t{lo}–t{hi} · {n} events"),
    "ev_left": ("이전 사건 {n}개는 여기 넣지 않았어요", "{n} earlier events are left out here"),
    "d_part": ("다른 인물이 나옴", "names someone else"), "d_because": ("이유가 있음", "has a reason"),
    "d_outcome": ("결과가 있음", "has an outcome"),
    "d_weight": ("큰 사건 {a} · 작은 사건 {b} · 표시 없음 {c}", "{a} major · {b} minor · {c} unmarked"),
    "d_note": ("사건 기록에는 누가 누구에게 했는지, 어디서 일어났는지, 어느 앞 사건 때문인지를 적을 칸이 없어요.",
               "An event record has no place for who did what to whom, where it happened, or which earlier event "
               "caused it."),
    "d_gen": ("추출 세대별", "By extractor generation"),
    # PHASE-69: Memory Explorer, Focused Attention, Dashboard Home & Upgraded Person Sheet
    "explore": ("탐색 · 수정", "Explore & edit"),
    "raw_inspector": ("원본 인스펙터", "Raw inspector"),
    "raw_person": ("원본 인스펙터에서 보기", "View in raw inspector"),
    "stale_rich": ("한동안 언급 없는 열린 일 {n}개는 여기 넣지 않았어요. 확인 필요 탭에서 검토하거나 닫을 수 있어요.",
                   "{n} open threads not mentioned for a while are left out here; review or close them under Needs attention."),
    "explore_all_facts": ("탐색 · 수정 (전체 사실 {n})", "Explore & edit ({n} facts)"),
    "hub_diag_link": ("처리 상태 · 패킷 진단", "Processing & packet diagnostics"),
    "hub_calls_link": ("모델 호출 로그", "Model calls"),
    "hub_last_reply": ("방금 답장에 들어간 기억", "Memory sent in last reply"),
    "hub_reply_meta": ("{n}줄 · 약 {tok}토큰 · {s}초", "{n} lines · ~{tok} tokens · {s}s"),
    "hub_full_packet": ("전체 패킷 보기", "Full packet"),
    "hub_scene_title": ("지금 장면 & 열린 일", "Current scene & open threads"),
    "hub_open_summary": ("요약 보기", "Open summary"),
    "hub_open_explore": ("탐색 · 수정 열기", "Open explore & edit"),
    "hub_attn_banner": ("확인이 필요한 항목 {n}건", "{n} items need attention"),
    "hub_attn_sub": ("눌러서 충돌·오래된 약속·보류 항목 정리하기", "Tap to review conflicts, stale threads & held items"),
    "hub_no_chat_hint": ("상단 채팅 전환기에서 다른 채팅을 고르거나, PocketRisu에서 대화를 보내면 자동으로 기록이 시작됩니다.",
                         "Pick a chat from the top switcher, or send a message in PocketRisu to start recording."),
    "s-facts": ("사실", "Facts"),
    "s-pairs": ("관계 · 호칭", "Relationships & address"),
    "s-epistemic": ("비밀 · 믿음 · 망각", "Secrets, beliefs & memory"),
    "s-items": ("아이템", "Items"),
    "s-entities": ("인물 · 대상", "People & entities"),
    "s-canon": ("카드 · 로어북 설정", "Card & lorebook setting"),
    "s-attention": ("확인이 필요한 항목", "Needs attention"),
    "s-conflicts": ("충돌", "Conflicts"),
    "s-repairs": ("직접 수정한 기록", "Direct edits"),
    "s-held": ("가진 아이템", "Held items"),
    "s-disguises": ("변장", "Disguises"),
    "ps_facts": ("이 인물의 사실", "Facts about them"),
    "ps_who": ("인물 전환", "Switch person"),
    "ps_pinned": ("항상 고정됨", "Pinned"),
    "ps_excluded": ("인물 목록 제외", "Excluded"),
    "ps_is_not_char": ("캐릭터 아님으로 표시됨 · 되돌리기는 확인 필요 → 직접 수정한 기록에서 할 수 있어요.",
                       "Marked not a character · undo under Needs attention → Direct edits."),
    "ex_edit": ("수정", "Edit"),
    "ex_setting": ("설정", "Setting"),
    "ex_owner": ("직접 수정", "Edited"),
    "ex_locked": ("고정됨", "Locked"),
    "ex_neg": ("부정", "Negated"),
    "ex_disputed": ("충돌", "Disputed"),
    "ex_secret": ("비밀", "Secret"),
    "ex_belief": ("믿음", "Belief"),
    "ex_forgot": ("망각", "Forgot"),
    "ex_disguise": ("변장", "Disguise"),
    "ex_told": ("전달", "Told"),
    "ex_mentions": ("언급 {n}회", "{n} mentions"),
    "ex_open_sheet": ("인물 시트", "Person sheet"),
    "ex_item_hist": ("변화 기록 {n}건", "{n} history steps"),
    "ex_chars": ("{n}자", "{n} chars"),
    "ex_canon_empty": ("기록된 카드·로어북 항목이 아직 없어요.", "No card or lorebook entries recorded yet."),
    "ex_empty": ("이 항목은 아직 기록이 없어요.", "Nothing recorded in this category yet."),
    "at_clear": ("확인할 항목이 없습니다. 기억이 깔끔하게 정리되어 있어요.", "Nothing needs attention right now."),
    "at_no_conflicts": ("충돌하는 기억이 없습니다.", "No conflicting memories."),
    "at_no_repairs": ("직접 수정한 기록이 아직 없습니다.", "No direct edits yet."),
    "at_existing": ("기존 / 설정", "Existing / setting"),
    "at_new_story": ("새 이야기", "New story"),
    "at_open_explore": ("탐색 · 수정으로", "Explore & edit"),
    "ex_note": ("메모", "Note"),
    "ex_item_now": ("현재 상태", "Current state"),
}

ACTS = ("notes", "settings", "backup", "retry")  # what the plugin does itself; its sanitizer keeps only these values


def t(lang: str, key: str, **kw: Any) -> str:
    text = T[key][lang == "en"]
    return text.format(**kw) if kw else text


# The browser page places the timeline's marks itself; in the panel, `placeMarks` does (it runs no page script).
PLACE = ("document.querySelectorAll('[data-l]').forEach(function(m){var l=Number(m.getAttribute('data-l'));"
         "if(l>=0&&l<=100)m.style.left=l+'%';var w=m.getAttribute('data-w');"
         "if(w!==null&&Number(w)>=0&&Number(w)<=100)m.style.width='calc('+Number(w)+'% - 2px)';});"
         "document.querySelectorAll('.v-filter').forEach(function(f){var i=document.createElement('input');i.type='search';"
         "f.appendChild(i);i.addEventListener('input',function(){var q=i.value.toLowerCase();"
         "document.querySelectorAll('.v-chat').forEach(function(r){r.style.display="
         "r.textContent.toLowerCase().indexOf(q)<0?'none':'';});});});"
         "(function(){"
         "var topBtn=document.querySelector('.nm-top');"
         "if(topBtn){"
         "var syncTop=function(){topBtn.classList.toggle('show',window.scrollY>280);};"
         "window.addEventListener('scroll',syncTop,{passive:true});"
         "topBtn.addEventListener('click',function(){window.scrollTo({top:0,behavior:'smooth'});});"
         "syncTop();}"
         "var slot=document.querySelector('.v-explore .v-exp-toolbar-slot');"
         "var main=document.querySelector('.vb-main');"
         "if(!slot)return;"
         "var secs=Array.prototype.slice.call(document.querySelectorAll('.v-explore .v-sec[data-cat]'));"
         "var cards=Array.prototype.slice.call(document.querySelectorAll('.v-explore .v-exp-card'));"
         "if(!secs.length)return;"
         "var bar=document.createElement('div');bar.className='vb-exp-bar';"
         "var chips=document.createElement('div');chips.className='vb-exp-chips';"
         "var allLbl=(main&&main.getAttribute('data-all-cat'))||'All';"
         "var searchPh=(main&&main.getAttribute('data-search'))||'Search...';"
         "var active='all';var btns=[];"
         "function addBtn(cat,label){"
         "var b=document.createElement('button');b.type='button';b.className='vb-chip'+(cat==='all'?' on':'');"
         "b.setAttribute('data-cat',cat);b.textContent=label;"
         "b.addEventListener('click',function(){active=cat;btns.forEach(function(x){x.b.classList.toggle('on',x.cat===cat);});"
         "apply();if(window.scrollY>220)window.scrollTo({top:0,behavior:'smooth'});});"
         "btns.push({cat:cat,label:label,b:b});chips.appendChild(b);}"
         "addBtn('all',allLbl);"
         "secs.forEach(function(s){"
         "var cat=s.getAttribute('data-cat')||'';"
         "var h2=s.querySelector('.v-h2');"
         "var lbl=h2&&h2.firstChild&&h2.firstChild.nodeType===3?h2.firstChild.textContent.trim():cat;"
         "if(cards.some(function(c){return c.getAttribute('data-cat')===cat;}))addBtn(cat,lbl);});"
         "var inp=document.createElement('input');inp.type='search';inp.className='vb-exp-search';"
         "inp.placeholder=searchPh;inp.setAttribute('aria-label',searchPh);"
         "function apply(){"
         "var q=inp.value.trim().toLowerCase();var per={};var total=0;"
         "cards.forEach(function(c){"
         "var cat=c.getAttribute('data-cat')||'';"
         "var ok=!q||(c.textContent||'').toLowerCase().indexOf(q)>=0;"
         "if(ok){per[cat]=(per[cat]||0)+1;total+=1;}"
         "c.style.display=(ok&&(active==='all'||cat===active))?'':'none';});"
         "btns.forEach(function(x){var n=x.cat==='all'?total:(per[x.cat]||0);x.b.textContent=x.label+' ('+n+')';});"
         "secs.forEach(function(s){"
         "var cat=s.getAttribute('data-cat')||'';"
         "var shown=cards.filter(function(c){return c.getAttribute('data-cat')===cat&&c.style.display!=='none';}).length;"
         "var catOk=active==='all'||cat===active;"
         "s.style.display=(catOk&&(shown>0||(!q&&active==='all'&&!cards.some(function(c){return c.getAttribute('data-cat')===cat;}))))?'':'none';"
         "var badge=s.querySelector('.v-h2 .v-n');if(badge)badge.textContent=String(shown);});}"
         "inp.addEventListener('input',apply);"
         "bar.appendChild(chips);bar.appendChild(inp);"
         "while(slot.firstChild)slot.removeChild(slot.firstChild);slot.appendChild(bar);"
         "apply();})();")


def full_page(title: str, body: str, lang: str = "ko", active: str = "hub") -> str:
    """A screen as a page of its own, for the browser: the panel's root class, favicon, and unified top chrome."""
    from .inspector import FAVICON
    all_cat = "전체" if lang == "ko" else "All"
    search_ph = ("사실, 인물, 약속, 비밀, 로어북 검색…" if lang == "ko"
                 else "Search facts, people, promises, secrets, lorebook…")
    root = (
        "*{box-sizing:border-box}body{margin:0;background:var(--c-bg);color:var(--c-text);"
        "font:15px/1.6 system-ui,-apple-system,\"Apple SD Gothic Neo\",\"Malgun Gothic\",\"Noto Sans KR\",sans-serif;"
        "-webkit-font-smoothing:antialiased}"
        ":root{color-scheme:dark;" + tokens.css_vars() + "}"
        + tokens.BROWSER_BAR_STYLE
        + ".nmos{" + tokens.css_vars() + ";min-height:100vh}"
        ".nmos .vb-main{max-width:1120px;margin:0 auto;padding:20px 22px 48px}"
        ".nmos .v{max-width:none}"
        ".nmos .v-filter input,.nmos .vb-exp-search{width:100%;background:var(--c-sunken);color:var(--c-text);"
        "border:1px solid var(--c-line-strong);border-radius:8px;padding:8px 12px;font:inherit;font-size:14px}"
        ".nmos .v-filter input:focus,.nmos .vb-exp-search:focus{border-color:rgba(74,106,245,0.7);outline:none;box-shadow:0 0 0 3px rgba(74,106,245,0.22)}"
        ".nmos .vb-exp-bar{display:flex;flex-direction:column;gap:8px;padding:10px 12px;border-radius:12px;"
        "background:var(--c-surface);border:1px solid var(--c-line)}"
        ".nmos .vb-exp-chips{display:flex;flex-wrap:wrap;gap:6px}"
        ".nmos .vb-chip{padding:4px 10px;border-radius:999px;font:inherit;font-size:12.5px;background:var(--c-sunken);"
        "border:1px solid var(--c-line);color:var(--c-text-soft);cursor:pointer;transition:background .15s ease,border-color .15s ease,color .15s ease}"
        ".nmos .vb-chip:hover{background:var(--c-raised);color:var(--c-text-strong)}"
        ".nmos .vb-chip.on{background:rgba(74,106,245,0.18);border-color:rgba(74,106,245,0.48);color:var(--c-text-strong);font-weight:600}"
        "@media (min-width:721px){.nmos .v-explore .v-exp-toolbar-slot{position:sticky;top:56px;z-index:16}"
        ".nmos .vb-exp-bar{background:rgba(30,33,42,0.95);backdrop-filter:blur(12px);box-shadow:0 6px 18px rgba(0,0,0,0.28)}}"
        "@media (max-width:720px){.nmos .vb-main{padding:14px 14px 40px}}"
    )
    return (
        f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{_v(title)}</title><link rel="icon" type="image/svg+xml" href="{_v(FAVICON)}">'
        f'<style>{root}{STYLE}</style></head>'
        f'<body><div class="nmos">{tokens.browser_bar(active, lang)}'
        f'<main class="vb-main" data-all-cat="{_v(all_cat)}" data-search="{_v(search_ph)}">{body}</main>'
        f'{tokens.browser_top_button(lang)}</div><script>{PLACE}</script></body></html>'
    )


def _block(title: str, sub: str, href: str | None = None, act: str | None = None, cls: str = "",
           extra: str = "") -> str:
    target = f' href="{_v(href)}"' if href else f' data-act="{act}"'
    return (f'<a class="v-block{(" " + cls) if cls else ""}"{target}><span class="v-bt">{_v(title)}</span>'
            f'<span class="v-bs">{_v(sub)}</span>{extra}</a>')


def _working(w: dict[str, Any], lang: str) -> tuple[str, str]:
    title, sub = _working_line(w, lang)
    if w.get("no_extraction") and w.get("state") == "ok":
        sub += " · " + t(lang, "no_extraction")
    return title, sub


def _working_line(w: dict[str, Any], lang: str) -> tuple[str, str]:
    state = w.get("state") or "idle"
    if state == "off":
        return t(lang, "off"), t(lang, "off_all" if w.get("all_off") else "off_chat")
    if state == "idle":
        return t(lang, "idle"), t(lang, "unknown")
    if w.get("failed"):
        return t(lang, "warn"), t(lang, "failed", f=w["failed"], p=w.get("pending") or 0)
    reply = w.get("reply")
    if reply is None:
        return t(lang, state), t(lang, "no_reply")
    if not reply.get("placed"):
        return t(lang, state), t(lang, "not_placed")
    return t(lang, state), t(lang, "placed", s=f"{(reply.get('ms') or 0) / 1000:.1f}", n=reply["placed"])


def _progress(done: int, due: int, warn: bool = False) -> str:
    """A quiet progress bar placed by `placeMarks` (`data-l` / `data-w`, no inline style)."""
    if due <= 0:
        return ""
    pct = round(min(max(done * 100 / due, 0), 100), 1)
    cls = " warn" if warn else (" ok" if pct >= 100 else "")
    return f'<div class="v-prog"><span class="v-prog-fill{cls}" data-l="0" data-w="{pct:g}"></span></div>'


def _kind_tag(kind: str | None, lang: str) -> str:
    k = str(kind or "")
    label = t(lang, k) if k in T else k
    safe_cls = f" k-{k}" if k in ("promise", "goal", "threat", "question", "debt") else ""
    return f'<span class="v-tag{safe_cls}">{_v(label)}</span>' if label else ""


def hub(data: dict[str, Any], lang: str, map_: bool = False, compact: bool = False) -> str:
    """The panel's first screen (PHASE-52 D1, PHASE-59 D2, PHASE-69 S4): the working line, then a block per category.
    With `compact=True` (the Phase 59/69 persistent shell), omits duplicate nav tiles that already sit in the top bar
    and focuses on live status, processing progress, attention banner, latest-reply memory snapshot and current scene."""
    if compact:
        return _hub_compact(data, lang)
    conv = data.get("conv")
    w = data.get("working") or {"state": "idle"}
    title, sub = _working(w, lang)
    state = w.get("state") or "idle"
    state = "warn" if w.get("failed") and state == "ok" else state
    blocks: list[str] = []
    if conv is not None:
        cid = conv["id"]
        detail = f"/inspector/c/{cid}"
        blocks.append(_block(title, sub, href=f"/views/c/{cid}/working", cls=f"v-wide {state}"))
        m = data.get("memory") or {}
        now_items = "".join(f'<span class="v-now">{_v(x)}</span>' for x in (m.get("now") or [])[:3])
        extra = f'<div class="v-now-list">{now_items}</div>' if now_items else ""
        th_prev = m.get("threads") or []
        if th_prev:
            rows = "".join(
                f'<span class="v-th-prev">{_kind_tag(th.get("kind"), lang)}'
                f'<span>{_v(str(th.get("text") or "")[:90])}</span></span>'
                for th in th_prev[:2]
            )
            extra += f'<div class="v-th-list">{rows}</div>'
        blocks.append(_block(t(lang, "memory"), t(lang, "memory_sub", c=m.get("cast", 0), o=m.get("open", 0),
                                                  g=m.get("changed", 0)), href=f"/views/c/{cid}/memory", cls="v-big",
                             extra=extra))
        if map_:
            blocks.append(_block(t(lang, "map"), t(lang, "map_sub"), href=f"/views/c/{cid}/map", cls="v-map-tile"))
        if data.get("attention"):
            blocks.append(_block(t(lang, "attention"), str(data["attention"]), href=f"{detail}#s-attention",
                                 cls="v-attn"))
        blocks.append(_block(t(lang, "notes"), t(lang, "notes_sub"), act="notes", cls="v-notes"))
        work = data.get("work") or {}
        work_bars = []
        for k in ("extraction", "embeddings"):
            item = work.get(k) or {}
            if item.get("due"):
                work_bars.append(
                    f'<div class="v-prog-row"><div class="v-prog-head"><span>{_v(t(lang, "w_" + k))}</span>'
                    f'<span>{item.get("done", 0)}/{item.get("due", 0)}</span></div>'
                    f'{_progress(int(item.get("done", 0)), int(item.get("due", 0)), bool(w.get("failed")))}</div>'
                )
        usage_extra = f'<div class="v-prog-wrap">{"".join(work_bars)}</div>' if work_bars else ""
        blocks.append(_block(t(lang, "usage"), t(lang, "usage_sub", n=(data.get("usage") or {}).get("calls", 0)),
                             href=f"/views/c/{cid}/working#s-usage", extra=usage_extra))
    else:
        blocks.append(_block(title, sub, href="/views/chats", cls=f"v-wide {state}"))
    blocks.append(_block(t(lang, "settings"), t(lang, "settings_sub"), act="settings"))
    blocks.append(_block(t(lang, "backup"), t(lang, "backup_sub"), act="backup"))
    blocks.append(_block(t(lang, "chats"), t(lang, "chats_sub", n=data.get("chats", 0)), href="/views/chats"))
    cap = " · ".join(str(x) for x in ((conv or {}).get("name"), (conv or {}).get("character"),
                                     f"t{conv['turns']}" if conv and conv.get("turns") is not None else None) if x)
    return (f'<div class="v v-hub"><div class="v-head"><h1 class="v-h1">NMOS</h1>'
            f'<span class="v-cap">{_v(cap)}</span></div><div class="v-blocks">{"".join(blocks)}</div></div>')


def _hub_compact(data: dict[str, Any], lang: str) -> str:
    """PHASE-69 S4: Dashboard Home for the persistent shell — no duplicate nav tiles, focused on live chat context."""
    conv = data.get("conv")
    w = data.get("working") or {"state": "idle"}
    title, sub = _working(w, lang)
    state = w.get("state") or "idle"
    state = "warn" if w.get("failed") and state == "ok" else state
    if conv is None:
        chats_n = int(data.get("chats") or 0)
        links = (f'<div class="v-dash-links"><a class="v-pill-link" href="/views/chats">'
                 f'{_v(t(lang, "chats_sub", n=chats_n))}</a></div>') if chats_n else ""
        body = (f'<div class="v-dash-card v-wide {state} v-dash-full">'
                f'<div class="v-dash-head"><span class="v-dash-title">{_v(title)}</span></div>'
                f'<span class="v-bs">{_v(sub)}</span>'
                f'<p class="v-note">{_v(t(lang, "hub_no_chat_hint"))}</p>{links}</div>')
        return f'<div class="v v-hub v-hub-compact"><div class="v-dash-grid">{body}</div></div>'

    cid = conv["id"]
    cards: list[str] = []

    # 1. Working status + extraction/embedding progress + calls count
    work = data.get("work") or {}
    work_bars = []
    for k in ("extraction", "embeddings"):
        item = work.get(k) or {}
        if item.get("due"):
            work_bars.append(
                f'<div class="v-prog-row"><div class="v-prog-head"><span>{_v(t(lang, "w_" + k))}</span>'
                f'<span>{item.get("done", 0)}/{item.get("due", 0)}</span></div>'
                f'{_progress(int(item.get("done", 0)), int(item.get("due", 0)), bool(w.get("failed")))}</div>'
            )
    prog_html = f'<div class="v-prog-wrap">{"".join(work_bars)}</div>' if work_bars else ""
    calls_n = int((data.get("usage") or {}).get("calls") or 0)
    calls_cap = f'<span class="v-cap">{_v(t(lang, "usage_sub", n=calls_n))}</span>' if calls_n else ""
    cards.append(
        f'<div class="v-dash-card v-wide {state} v-dash-full">'
        f'<div class="v-dash-head"><span class="v-dash-title">{_v(title)}</span>{calls_cap}</div>'
        f'<span class="v-bs">{_v(sub)}</span>{prog_html}'
        f'<div class="v-dash-links">'
        f'<a class="v-pill-link" href="/views/c/{cid}/working">{_v(t(lang, "hub_diag_link"))}</a>'
        f'<a class="v-pill-link" href="/inspector/calls">{_v(t(lang, "hub_calls_link"))}</a>'
        f'</div></div>'
    )

    # 2. Attention banner (only when > 0) -> opens dedicated /attention screen directly
    if attn := int(data.get("attention") or 0):
        cards.append(
            f'<a class="v-block v-attn v-dash-full" href="/views/c/{cid}/attention">'
            f'<div><span class="v-bt">{_v(t(lang, "hub_attn_banner", n=attn))}</span>'
            f'<div class="v-meta">{_v(t(lang, "hub_attn_sub"))}</div></div>'
            f'<span class="v-bs">{attn}</span></a>'
        )

    # 3. Latest reply memory snapshot
    reply = w.get("reply")
    if reply and reply.get("placed"):
        tok = f"{int(reply.get('tokens') or 0):,}"
        sec = f"{(reply.get('ms') or 0) / 1000:.1f}"
        meta = t(lang, "hub_reply_meta", n=reply["placed"], tok=tok, s=sec)
        snap_rows = []
        for x in (reply.get("lines") or [])[:10]:
            echo = f' <span class="v-tag k-echo">{_v(t(lang, "echoed"))}</span>' if x.get("echoed") else ""
            snap_rows.append(f'<div class="v-snap-line">{_v(plain(str(x.get("text") or ""), lang))}{echo}</div>')
        snap_body = more(snap_rows, lang, 4) if snap_rows else ""
        reply_inner = f'<span class="v-bs">{_v(meta)}</span>{snap_body}'
    else:
        reply_inner = f'<span class="v-bs">{_v(t(lang, "no_reply" if reply is None else "not_placed"))}</span>'
    cards.append(
        f'<div class="v-dash-card">'
        f'<div class="v-dash-head"><span class="v-dash-title">{_v(t(lang, "hub_last_reply"))}</span></div>'
        f'{reply_inner}'
        f'<div class="v-dash-links">'
        f'<a class="v-pill-link" href="/views/c/{cid}/working">{_v(t(lang, "hub_full_packet"))}</a>'
        f'</div></div>'
    )

    # 4. Current scene & open threads preview
    m = data.get("memory") or {}
    mem_sub = t(lang, "memory_sub", c=m.get("cast", 0), o=m.get("open", 0), g=m.get("changed", 0))
    now_items = "".join(f'<span class="v-now">{_v(x)}</span>' for x in (m.get("now") or [])[:4])
    scene_extra = f'<div class="v-now-list">{now_items}</div>' if now_items else ""
    th_prev = m.get("threads") or []
    if th_prev:
        rows = "".join(
            f'<span class="v-th-prev">{_kind_tag(th.get("kind"), lang)}'
            f'<span>{_v(str(th.get("text") or "")[:90])}</span></span>'
            for th in th_prev[:3]
        )
        scene_extra += f'<div class="v-th-list">{rows}</div>'
    cards.append(
        f'<div class="v-dash-card">'
        f'<div class="v-dash-head"><span class="v-dash-title">{_v(t(lang, "hub_scene_title"))}</span></div>'
        f'<span class="v-bs">{_v(mem_sub)}</span>{scene_extra}'
        f'<div class="v-dash-links">'
        f'<a class="v-pill-link" href="/views/c/{cid}/memory">{_v(t(lang, "hub_open_summary"))}</a>'
        f'<a class="v-pill-link" href="/views/c/{cid}/explore">{_v(t(lang, "hub_open_explore"))}</a>'
        f'</div></div>'
    )

    cap = " · ".join(str(x) for x in (conv.get("character"),
                                     f"t{conv['turns']}" if conv.get("turns") is not None else None) if x)
    head_name = conv.get("name") or "NMOS"
    return (f'<div class="v v-hub v-hub-compact"><div class="v-head"><h1 class="v-h1">{_v(head_name)}</h1>'
            f'<span class="v-cap">{_v(cap)}</span></div><div class="v-dash-grid">{"".join(cards)}</div></div>')


NOW = ("located_in", "has_status", "vital_status")  # vital_status: extract-v21's alive / dead / missing (PHASE-66)


def now_said(facts: list[dict[str, Any]], name: str | list[str]) -> list[str]:
    """Where a character is and how, as the story says now (canon left out); `name` may be all their names."""
    keys = {n.casefold() for n in ([name] if isinstance(name, str) else name)}
    said = [f.get("object") or f.get("value") for f in facts if f["predicate"] in NOW and not f.get("canon")
            and f.get("polarity") != "negative"
            and keys & {str(f.get("subject") or "").casefold(),
                        str((f.get("subject_entity") or {}).get("name") or "").casefold()}]
    return list(dict.fromkeys(str(s) for s in said if s))


def now_lines(facts: list[dict[str, Any]], cast: list[str]) -> list[str]:
    """Where each character of the scene is and how (the newest request's cast, in its order): "Hana · the lighthouse ·
    tired". Characters with neither are left out."""
    return [" · ".join([name, *said]) for name in cast if (said := now_said(facts, name))]



def section(key: str, lang: str, body: str, count: int | None = None) -> str:
    n = f'<span class="v-n">{count}</span>' if count is not None else ""
    return f'<div class="v-sec" id="{key}"><h2 class="v-h2">{_v(t(lang, key))}{n}</h2>{body}</div>'


def _pair_bits(p: dict[str, Any], lang: str) -> list[str]:
    """A pair's roles, feelings and forms of address, each escaped: "A→B 감정 애정", a feeling with its sign's dot and its
    strength (PHASE-58 S4); one without detail reads as before."""
    bits = []
    for k, pred in (("role", "role_toward"), ("feels", "feels_toward"), ("speech", "addresses")):
        for f in p[k]:
            value = f'"{f.get("value")}"' if pred == "addresses" else f.get("value")
            cond = f" [{label}]" if (label := cond_label(f, lang)) else ""  # PHASE-64; PHASE-66 part 5: any slot
            cond += "".join(f" ({x})" for x in cond_extra(f, lang))
            h = happened_mark(_own(f), lang)
            m = carried_mark(f, lang)
            bits.append(_v(f"{_named(f, 'subject')}→{_named(f, 'object')} {t(lang, pred)}{cond} ") + feeling_dot(f, lang)
                        + _v(f"{value}") + feeling_detail(f, lang) + (f" {h}" if h else "") + (f" {m}" if m else ""))
    return bits


def _slotted(f: dict[str, Any], lang: str) -> str:
    """A relationship's value with its slot (PHASE-66 part 5: an extract-v21 relationship held only in public, in
    private or in a situation), raw text; the value alone for every earlier row."""
    value = f.get("value")
    label = cond_label(f, lang)
    return f"{value} [{label}]" if label and value else value


def belief_lines(rows: list[dict[str, Any]] | None, lang: str) -> list[str]:
    """What characters believe (PHASE-66 part 5), escaped: the content, then who, held or what ended it, the turn;
    retract and correct behind a tap, as every repair here."""
    out = []
    for b in rows or []:
        e = b.get("ended_by")
        state = t(lang, "b_ended", what=" ".join(str(x) for x in (e.get("predicate"), e.get("object"), e.get("value"))
                                                 if x)) if e else t(lang, "b_held")
        out.append(line(_v(b.get("value")), _v(" · ".join(str(x) for x in (_named(b, "subject"), state,
                                                                         f"t{b.get('turn')}") if x)),
                        _epistemic_acts(b)))
    return out


def forgot_lines(rows: list[dict[str, Any]] | None, lang: str) -> list[str]:
    """Who forgot what and since when (PHASE-66 part 5), escaped, with how much it withdrew."""
    out = []
    for g in rows or []:
        what = (t(lang, "f_all") if g.get("scope") == "all"
                else t(lang, "f_since", n=g["since"]) if g.get("scope") == "since" and g.get("since") is not None
                else str(g.get("value") or ""))
        meta = " · ".join(str(x) for x in (g.get("who") or g.get("subject"), f"t{g.get('turn')}",
                                           t(lang, "f_withdrew", n=len(g.get("withdrew") or []))) if x)
        out.append(line(_v(what), _v(meta), _epistemic_acts(g)))
    return out


def carried_mark(row: dict[str, Any], lang: str) -> str:
    """A small word on a row that came through a carry link (PHASE-60 S6), or "" (the row then reads as before)."""
    return f'<span class="v-tag">{_v(t(lang, "carried"))}</span>' if row.get("carried") else ""


def _own(row: dict[str, Any]) -> dict[str, Any]:
    """A carried row without its turn, which is not this chat's (it sits before turn 0); any other row as it is."""
    return {k: v for k, v in row.items() if k != "turn"} if row.get("carried") else row


def line(main: str, meta: str = "", extra: str = "") -> str:
    """One item: its text (already escaped), a muted line under it, and what the panel adds (a repair marker)."""
    return f'<div class="v-line">{main}{f"<div class=\'v-meta\'>{meta}</div>" if meta else ""}{extra}</div>'


def more(items: list[str], lang: str, n: int = 3) -> str:
    """The first `n` items, the rest under one fold."""
    if len(items) <= n:
        return "".join(items)
    return "".join(items[:n]) + (f'<details class="v-more"><summary>{_v(t(lang, "more", n=len(items) - n))}</summary>'
                                 f'{"".join(items[n:])}</details>')


def thread_meta(th: dict[str, Any], lang: str) -> str:
    """A thread's kind, how long it is meant to last when known (PHASE-51), since when, and when it happened (PHASE-60 S7);
    a carried thread (PHASE-60 S6) has no "since": its turn is not this chat's."""
    kind = t(lang, th["kind"]) if th["kind"] in T else th["kind"]
    horizon = t(lang, f"hz.{th['horizon']}") if th.get("horizon") in ("scene", "arc", "lasting") else None
    since = None if th.get("carried") else t(lang, "since", t=th.get("turn"))
    return " · ".join(x for x in (kind, horizon, since, happened_text(_own(th), lang)) if x)


def _close_own(th: dict[str, Any]) -> str:
    """The thread's close button, or "" for a carried thread (PHASE-60 S6): it is the other chat's, and closing it
    here answers 422, so the row stays readable with its carried mark and offers nothing."""
    return "" if th.get("carried") else _close(th)


def _thread_meta(th: dict[str, Any], lang: str) -> str:
    """`thread_meta` escaped, with the carried mark when the thread came through a link."""
    m = carried_mark(th, lang)
    return _v(thread_meta(th, lang)) + (f" · {m}" if m else "")


def name_link(cid: str, entities: dict[str, str], name: str | None) -> str:
    """A character's name, leading to their sheet when NMOS knows them."""
    eid = entities.get(str(name or "").casefold())
    return f'<a class="v-name" href="/views/c/{cid}/person/{eid}">{_v(name)}</a>' if eid else _v(name)


def _named(f: dict[str, Any], side: str) -> str:
    if side == "object" and f.get("toward_guise"):  # PHASE-66: held toward the guise, named as the guise
        return str(f.get("object") or "")
    e = f.get(f"{side}_entity") or {}
    return str(e.get("name") or f.get(side) or "")


# A chat that carries another chat's memory (PHASE-60 S6, ADR 0085): `d["carry"]` is there only while a link is in force.
CARRY_MAX = 50  # carried lines shown in one section; the rest are counted
# A carried line reads subject, word, object/value; where the panel's word reads the other way ("held by") or has none
# in Korean, its own word.
CARRY_WORDS = {"also_called": "carry_aka", "possesses": "carry_has", "told": "carry_told"}
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)


def _turn_of(value: Any) -> int | None:
    """A turn the panel's sanitizer keeps in a link (`/t/` and at most seven digits), or None."""
    if isinstance(value, int) and not isinstance(value, bool) and 0 <= value < 10_000_000:
        return value
    return None


def carry_href(row: dict[str, Any]) -> str | None:
    """Where a carried line came from, in the only two shapes the panel keeps: the source chat's turn
    (`/inspector/c/<id>/t/<turn>`) or, without one, the source chat (`/inspector/c/<id>`); None without a source id."""
    src = row.get("carried_from")
    conv = str(src.get("conversation") or "") if isinstance(src, dict) else ""
    if not _UUID.fullmatch(conv):
        return None
    turn = _turn_of(src.get("turn"))
    return f"/inspector/c/{conv}" + (f"/t/{turn}" if turn is not None else "")


def _is_thread(row: dict[str, Any]) -> bool:
    if row.get("line") in ("fact", "thread", "belief"):  # a carried belief's own line (PHASE-66) is no thread
        return row["line"] == "thread"
    if row.get("kind") in ("fact", "thread", "belief"):  # the carry line's own mark (`d['carry']['lines']`)
        return row["kind"] == "thread"
    return "predicate" not in row and ("by" in row or "text" in row)


def carry_text(row: dict[str, Any], lang: str) -> str:
    """A carried line as plain text (not escaped): "세라 위치 등대", "세라 → 카이토 관계 소꿉친구", or a thread's
    "세라 → 카이토: 등대에서 만나기"."""
    if row.get("kind") == "belief" or row.get("line") == "belief":
        who = _named(row, "subject")
        val = str(row.get("value") or "")
        return f"{who} {t(lang, 'carry_believes')}: {val}" if who else val
    if _is_thread(row):  # a thread row's by / to / text, or a carry line's subject / object / value
        by = row.get("by") if "by" in row else _named(row, "subject")
        to = row.get("to") if "by" in row else _named(row, "object")
        text = row.get("text") if "text" in row else row.get("value")
        who = " → ".join(str(x) for x in (by, to) if x)
        return f"{who}: {text or ''}" if who else str(text or "")
    pred = str(row.get("predicate") or "")
    said = t(lang, CARRY_WORDS[pred]) if pred in CARRY_WORDS else word(pred, lang)
    subject, obj, value = _named(row, "subject"), _named(row, "object"), row.get("value")
    if pred == "event" and value not in (None, ""):  # what happened, as the timeline shows an event
        text = f"{subject}: {value}" if subject else str(value)
    elif obj and value not in (None, ""):
        text = f"{subject} → {obj} {said} {value}"
    else:
        text = " ".join(str(x) for x in (subject, said, obj or value) if x not in (None, ""))
    return text + (" " + t(lang, "carry_not") if row.get("polarity") == "negative" else "")


def carry_head(c: dict[str, Any], lang: str) -> str:
    """Where the carried lines come from, in words (plain text, not escaped)."""
    if c.get("mode") == "regression":
        head = t(lang, "carry_regress", names=", ".join(str(n) for n in c.get("names") or []))
    else:
        src = c.get("source") or {}
        label = " · ".join(str(x) for x in (src.get("character"), src.get("chat")) if x)
        head = t(lang, "carry_from", source=label or str(src.get("id") or "")[:8])
    cut = _turn_of(c.get("cutoff_turn"))
    return head + (" · " + t(lang, "carry_upto", t=cut) if cut is not None else "")


def carry_line(row: dict[str, Any], lang: str) -> str:
    """One carried line: a thread's kind, its words linked to where it was said in the source chat, when it happened
    (without a turn: a carried row's turn is not this chat's), and the source chat's turn under it."""
    text = _v(carry_text(row, lang))
    href = carry_href(row)
    main = f'<a class="v-src" href="{_v(href)}">{text}</a>' if href else text
    if _is_thread(row):  # a carry line's kind is the mark "thread": its opening's predicate names the kind, and
        # without an opening the data side sends the thread's kind itself in its place ("promise")
        p = str(row.get("predicate"))
        kind = (THREAD_KINDS.get(p, p if p in THREAD_KINDS.values() else None) if row.get("kind") == "thread"
                else row.get("kind"))
        main = _kind_tag(kind, lang) + main
    h = happened_mark({k: v for k, v in row.items() if k != "turn"}, lang)
    src = row.get("carried_from")
    turn = _turn_of(src.get("turn")) if isinstance(src, dict) else None
    return line(main + (f" {h}" if h else ""), _v(t(lang, "carry_turn", t=turn)) if turn is not None else "")


def carry_lines(c: dict[str, Any], lang: str, empty: str) -> str:
    """The section's body: where from, then at most CARRY_MAX lines folded as the other lists, and how many more."""
    rows = c.get("lines") or []
    body = f'<p class="v-text">{_v(carry_head(c, lang))}</p>'
    body += more([carry_line(r, lang) for r in rows[:CARRY_MAX]], lang) or empty
    if len(rows) > CARRY_MAX:
        left = _v(t(lang, "carry_left", n=len(rows) - CARRY_MAX))
        src = str((c.get("source") or {}).get("id") or "")
        body += (f'<p class="v-note">'
                 + (f'<a class="v-src" href="/inspector/c/{src}">{left}</a>' if _UUID.fullmatch(src) else left)
                 + "</p>")
    return body


def _person_carry(c: dict[str, Any] | None, e: dict[str, Any], lang: str, empty: str) -> str:
    """The person sheet's carried lines (only theirs, chosen by the data side). Without any: for `continue` no section;
    for `regression`, where from and nothing yet when they are one of those who remember, else a note that they do not."""
    if not c:
        return ""
    n = len(c.get("lines") or [])
    if n:
        return section("s-carry", lang, carry_lines(c, lang, empty), n)
    if c.get("mode") != "regression":
        return ""
    names = {str(x).casefold() for x in [e.get("name"), *(e.get("names") or [])] if x}
    if names & {str(x).casefold() for x in c.get("names") or []}:
        return section("s-carry", lang, carry_lines(c, lang, empty))
    return section("s-carry", lang, f'<p class="v-note">{_v(t(lang, "carry_forgot"))}</p>')


def memory(d: dict[str, Any], lang: str, map_: bool = False, rich: bool = False) -> str:
    """A chat's memory as one document (PHASE-52 D2, PHASE-59 D3): now, open threads, people, so far, secrets, changed
    from the setting; sticky desktop TOC + mobile jump pills; at the foot, the way into everything else.
    With `rich=False` (default), renders byte-identical to the Phase 60 baseline; `rich=True` (PHASE-69) points
    footer links to the dedicated Explorer and Attention screens."""
    conv, ents = d["conv"], d.get("entities") or {}
    cid = conv["id"]
    nm = lambda name: name_link(cid, ents, name)  # noqa: E731
    nothing = f'<p class="v-text">{_v(t(lang, "none_yet"))}</p>'
    now = [line(nm(x["name"]), " · ".join(_v(s) for s in x["said"])) for x in d.get("now") or []]
    threads = d.get("threads") or []
    opened = [line(f"{_kind_tag(th.get('kind'), lang)}{nm(th['by'])}{' → ' + nm(th['to']) if th.get('to') else ''}: {_v(th['text'])}",
                   _thread_meta(th, lang),
                   _close_own(th)) for th in threads]
    stale = f'<p class="v-note">{_v(t(lang, "stale_rich" if rich else "stale", n=d["stale"]))}</p>' if d.get("stale") else ""
    people = []
    for p in d.get("pairs") or []:
        names = sorted(p["names"].values())
        rel = [_slotted(f, lang) for f in p["relationship"]]
        head = " ↔ ".join(nm(n) for n in names) + (f" · {_v(', '.join(str(r) for r in rel if r))}" if rel else "")
        bits = _pair_bits(p, lang)
        if len(p["relationship"]) > 1 or any(not symmetric(f.get("value")) for f in p["relationship"]):
            bits = [_v(f"{_named(f, 'subject')}→{_named(f, 'object')} {t(lang, 'relationship')} {_slotted(f, lang)}")
                    + (f" {h}" if (h := happened_mark(_own(f), lang)) else "")
                    + (f" {m}" if (m := carried_mark(f, lang)) else "")
                    for f in p["relationship"]] + bits
        else:
            bits = [h for f in p["relationship"]
                    if (h := " ".join(x for x in (happened_mark(_own(f), lang), carried_mark(f, lang)) if x))] + bits
        people.append(line(head, " · ".join(bits)))
    story, scenes = d.get("story"), d.get("scenes") or []
    sofar = (f'<p class="v-text">{_v(story["text"])}</p><div class="v-meta">{_v(t(lang, "story"))} · '
             f't{story["first_turn"]}–{story["last_turn"]}</div>') if story else ""
    if scenes:
        sofar += (f'<details class="v-more"><summary>{_v(t(lang, "scenes", n=len(scenes)))}</summary>'
                  + "".join(line(_v(s["text"]), f"t{s['first_turn']}–{s['last_turn']}") for s in scenes) + "</details>")
    next_note = ""
    if rich and (nxt := d.get("next_summary")):
        rem = int(nxt["remaining"])
        nk = "next_summary_one" if rem == 1 else "next_summary"
        next_note = f'<p class="v-note">{_v(t(lang, nk, a=nxt["first_turn"], b=nxt["last_turn"], at=nxt["ready_turn"], n=rem))}</p>'
    secrets = [line(_v(content(s)), _v(" · ".join(x for x in (
        t(lang, "by", who=", ".join(s.get("holders") or [])) if s.get("holders") else "",
        t(lang, "kept", who=", ".join(s.get("open") or [])), f"t{s.get('turn')}",
        happened_text(s, lang)) if x)))
        for s in d.get("secrets") or [] if s.get("open")]
    changed = [line(
        f"{nm(_named(c['fact'], 'subject'))} {_v(t(lang, c['fact']['predicate']) if c['fact']['predicate'] in T else c['fact']['predicate'])}",
        f'<span class="v-diff"><span class="v-diff-old">{_v(c["old"])}</span> → <span class="v-diff-new">{_v(c["new"])}</span>'
        + ("" if c["fact"].get("carried") else f'<span>· t{c["fact"].get("turn")}</span>') + "</span>"
        + (f' · {h}' if (h := happened_mark(_own(c["fact"]), lang)) else "")
        + (f' · {m}' if (m := carried_mark(c["fact"], lang)) else ""))
               for c in d.get("changes") or []]
    counts = {"s-now": len(now), "s-open": len(threads), "s-people": len(people),
              "s-sofar": len(scenes) + (1 if story else 0), "s-secrets": len(secrets), "s-changed": len(changed)}
    keys = ["s-now", "s-open", "s-people", "s-sofar", "s-secrets", "s-changed"]
    epistemic = ""  # PHASE-66 part 5: only a chat whose view has beliefs or forgettings
    for key, rows in (("s-beliefs", belief_lines(d.get("beliefs"), lang)),
                      ("s-forgotten", forgot_lines(d.get("forgotten"), lang))):
        if rows:
            counts[key] = len(rows)
            keys.insert(keys.index("s-changed"), key)
            epistemic += section(key, lang, more(rows, lang), len(rows))
    link = d.get("carry")
    carried = ""
    if link:  # PHASE-60 S6: only while a link is in force
        n = len(link.get("lines") or [])
        counts["s-carry"] = n
        keys.insert(1, "s-carry")
        carried = section("s-carry", lang, carry_lines(link, lang, nothing), n or None)
    chips = '<div class="v-chips">' + "".join(
        f'<a href="#{k}"><span>{_v(t(lang, k))}</span>'
        + (f'<span class="v-chip-n">{counts[k]}</span>' if counts[k] else "") + "</a>"
        for k in keys) + "</div>"
    body = (section("s-now", lang, more(now, lang, 6) or nothing) + carried
            + section("s-open", lang, (more(opened, lang) or nothing) + stale, len(threads))
            + section("s-people", lang, more(people, lang) or nothing, len(people))
            + section("s-sofar", lang, (sofar or nothing) + next_note)
            + section("s-secrets", lang, more(secrets, lang) or nothing, len(secrets)) + epistemic
            + section("s-changed", lang, more(changed, lang) or nothing, len(changed)))
    detail = f"/inspector/c/{cid}"
    if rich:
        foot = (f'<div class="v-foot"><a href="/views/c/{cid}/explore">{_v(t(lang, "explore_all_facts", n=d.get("facts", 0)))}</a>'
                + (f' · <a href="/views/c/{cid}/attention">{_v(t(lang, "attention"))} {d["attention"]}</a>' if d.get("attention") else "")
                + (f' · <a href="/views/c/{cid}/map">{_v(t(lang, "map"))}</a>' if map_ else "")
                + f' · <a href="{detail}">{_v(t(lang, "raw_inspector"))}</a></div>')
    else:
        foot = (f'<div class="v-foot"><a href="{detail}#s-facts">{_v(t(lang, "facts", n=d.get("facts", 0)))}</a>'
                + (f' · <a href="{detail}#s-attention">{_v(t(lang, "attention"))} {d["attention"]}</a>' if d.get("attention") else "")
                + (f' · <a href="/views/c/{cid}/map">{_v(t(lang, "map"))}</a>' if map_ else "")
                + f' · <a href="{detail}">{_v(t(lang, "details"))}</a></div>')
    cap = " · ".join(str(x) for x in (conv.get("character"), f"t{conv['turns']}" if conv.get("turns") is not None else None) if x)
    return (f'<div class="v v-doc"><div class="v-head"><h1 class="v-h1">{_v(conv.get("name") or t(lang, "memory"))}</h1>'
            f'<span class="v-cap">{_v(cap)}</span></div><div class="v-doc-grid">{chips}'
            f'<div class="v-doc-main">{body}{foot}</div></div></div>')



def word(predicate: str, lang: str) -> str:
    """A predicate in the panel's words ("위치", "관계"…)."""
    return (T[predicate][0 if lang == "ko" else 1] if predicate in T
            else PLAIN_KO.get(predicate) if lang == "ko" else None) or predicate.replace("_", " ")


def change_text(text: str, predicate: str | None, lang: str) -> str:
    """A person's change in the panel's words: an event as it is, anything else after its kind ("위치: …")."""
    if not predicate or predicate == "event":
        return text
    return f"{word(predicate, lang)}: {text}"


def _event(m: tuple[Any, ...], major: bool, lang: str) -> str:
    text = change_text(str(m[2]), m[3] if len(m) > 3 else None, lang)
    extra = m[4] if len(m) > 4 else None
    if isinstance(extra, dict):
        row = extra if "turn" in extra else {"turn": m[0], **extra}
    elif isinstance(extra, str):
        row = {"turn": m[0], "when_happened": extra}
    else:
        row = None
    mark = happened_mark(row, lang) if row is not None else ""
    return (f'<div class="v-ev{" major" if major else ""}"><span class="v-t">t{m[0]}</span><span class="v-d"></span>'
            f'<span class="v-x">{_v(text)}{f" {mark}" if mark else ""}</span></div>')


def _timeline(d: dict[str, Any], lang: str) -> str:
    """The person's changes (PHASE-52 D4, amendment 2): an overview bar to look at, not to tap (the chat's span in 30
    parts, at most five rings where the most major changes are), then the changes as lines, a ring's first major
    change first, the rest under one fold, each list in turn order."""
    from .timeline import circles
    first, last = d.get("first", 0) or 0, d.get("last", 0) or 0
    marks = sorted(d.get("marks") or [], key=lambda m: m[0])
    spans = circles(marks, first, last)
    lead = set()
    for b in spans:
        if b["major"]:
            lead.add(next(i for i, m in enumerate(marks) if b["lo"] <= m[0] <= b["hi"] and m[1]))
    head = [_event(m, True, lang) for i, m in enumerate(marks) if i in lead]
    rest = [_event(m, False, lang) for i, m in enumerate(marks) if i not in lead]
    return overview(spans, first, last, lang) + more(head + rest, lang, n=len(head) or 3)


def overview(spans: list[dict[str, Any]], first: int, last: int, lang: str) -> str:
    """The overview bar (PHASE-52 D4 amendment 2): `timeline.circles`' spans as pins on the chat's span of turns."""
    span = max(last - first, 1)
    pins = []
    for b in spans:
        left = round(min(max(((b["lo"] + b["hi"]) / 2 - first) / span * 100, 0), 100), 3)
        pins.append(f'<span class="v-pin{" major" if b["major"] else ""}" data-l="{left:g}"></span>')
    return ('<div class="v-mini" aria-hidden="true"><span class="v-axis"></span>' + "".join(pins) + "</div>"
            f'<div class="v-ends"><span>t{first}</span><span>{_v(t(lang, "now_turn", t=last))}</span></div>')


def person(d: dict[str, Any], lang: str, rich: bool = False) -> str:
    """A person's sheet (PHASE-52 D3, PHASE-69 S3): now, relationships, promises and goals, what they know and do not,
    the timeline. With `rich=False` (default), renders byte-identical to the Phase 60 baseline; `rich=True` adds
    editable facts about them, held items, disguises, status badges, and a character switcher."""
    conv, e, ents = d["conv"], d["entity"], d.get("entities") or {}
    cid = conv["id"]
    nm = lambda name: name_link(cid, ents, name)  # noqa: E731
    nothing = f'<p class="v-text">{_v(t(lang, "none_yet"))}</p>'
    aka = [n for n in e.get("names") or [] if n != e.get("name")]
    now = f'<p class="v-text">{" · ".join(_v(x) for x in d.get("now") or [])}</p>' if d.get("now") else nothing
    if rich and e.get("note"):
        now += _entity_note_box(e["note"], lang)
    rels = []
    for p in d.get("pairs") or []:
        other = [n for i, n in p["names"].items() if str(i) != str(e["id"])]
        rel = [str(_slotted(f, lang)) for f in p["relationship"] if f.get("value")]
        pair_edit = _edit_drawer(_pair_edit_rows(p, lang), lang) if rich else ""
        rels.append(line(" · ".join([nm(o) for o in other] + [_v(r) for r in rel]), " · ".join(_pair_bits(p, lang)), pair_edit))
    threads = [line(f"{_v(th['text'])}" + (f" → {nm(th['to'])}" if th.get("to") and th.get("by") == e.get("name") else ""),
                    _thread_meta(th, lang),
                    _close_own(th)) for th in d.get("threads") or []]
    knows = [line(_v(content(s)), _v(t(lang, "knows") + f" · t{s.get('turn')}")) for s in d.get("knows") or []]
    knows += [line(_v(content(s)), _v(t(lang, "unaware", who=", ".join(s.get("holders") or [])) + f" · t{s.get('turn')}"))
              for s in d.get("kept") or []]
    time = (_timeline(d, lang) + f'<p class="v-note">{_v(t(lang, "tl_hint"))}</p>') if d.get("marks") else nothing
    extra_facts = ""
    extra_held = ""
    extra_disguises = ""
    if rich:
        if p_facts := d.get("facts") or []:
            grouped, under = _guise_grouped(p_facts[:120])
            cards = [_fact_card(f, cid, ents, lang, under=id(f) in under, with_cat=False) for f in grouped]
            extra_facts = (f'<div class="v-sec" id="s-facts"><h2 class="v-h2">{_v(t(lang, "ps_facts"))}'
                           f'<span class="v-n">{len(p_facts)}</span></h2>'
                           f'<div class="v-exp-list">{more(cards, lang, 8)}</div></div>')
        if p_held := d.get("held") or []:
            h_cards = [_fact_card(f, cid, ents, lang, with_cat=False) for f in p_held[:60]]
            extra_held = section("s-held", lang, f'<div class="v-exp-list">{more(h_cards, lang, 6)}</div>', len(p_held))
        if p_disguises := d.get("disguises") or []:
            d_cards = [_disguise_card(dg, cid, ents, lang, with_cat=False) for dg in p_disguises[:30]]
            extra_disguises = section("s-disguises", lang, f'<div class="v-exp-list">{"".join(d_cards)}</div>', len(p_disguises))
    body = (section("s-now", lang, now) + section("s-rels", lang, more(rels, lang) or nothing, len(rels))
            + extra_facts + extra_held
            + section("s-threads", lang, more(threads, lang) or nothing, len(threads))
            + section("s-knows", lang, more(knows, lang) or nothing, len(knows))
            + extra_disguises
            + "".join(section(k, lang, more(rows, lang), len(rows)) for k, rows in (  # PHASE-66 part 5
                ("s-beliefs", belief_lines(d.get("beliefs"), lang)), ("s-forgotten", forgot_lines(d.get("forgotten"), lang)))
                if rows)
            + _told_section(cid, d.get("told"), ents, lang) + _person_carry(d.get("carry"), e, lang, nothing)
            + section("s-time", lang, time))
    cap = t(lang, "aka", names=", ".join(aka)) if aka else ""
    if not e.get("persona"):  # PHASE-47 S6: the button, behind a tap like every repair here
        not_char_key = "ps_is_not_char" if rich else "is_not_char"
        body += (f'<p class="v-note">{_v(t(lang, not_char_key))}</p>' if e.get("excluded")
                 else line(_v(t(lang, "not_char")), "", _act("entity_exclude", e["id"], e.get("name"))))
    who_picker = ""
    badges = ""
    if rich:
        b_list = []
        if e.get("persona"):
            b_list.append(f'<span class="v-tag k-info">{_v(t(lang, "you"))}</span>')
        if e.get("pinned"):
            b_list.append(f'<span class="v-tag k-locked">{_v(t(lang, "ps_pinned"))}</span>')
        if e.get("excluded"):
            b_list.append(f'<span class="v-tag k-warn">{_v(t(lang, "ps_excluded"))}</span>')
        badges = " " + "".join(b_list) if b_list else ""
        chars = d.get("characters") or []
        if len(chars) > 1:
            choices = [f'<b>{_v(c["name"])}</b>' if str(c["id"]) == str(e["id"])
                       else f'<a href="/views/c/{cid}/person/{c["id"]}">{_v(c["name"])}</a>'
                       for c in chars[:50]]
            who_picker = f'<p class="who"><span>{_v(t(lang, "ps_who"))}</span> ' + " · ".join(choices) + "</p>"
        foot = (f'<div class="v-foot"><a href="/views/c/{cid}/memory">{_v(t(lang, "back_memory"))}</a> · '
                f'<a href="/views/c/{cid}/explore">{_v(t(lang, "explore"))}</a> · '
                f'<a href="/inspector/c/{cid}/e/{e["id"]}">{_v(t(lang, "raw_person"))}</a></div>')
    else:
        foot = (f'<div class="v-foot"><a href="/views/c/{cid}/memory">{_v(t(lang, "back_memory"))}</a> · '
                f'<a href="/inspector/c/{cid}/e/{e["id"]}">{_v(t(lang, "details"))}</a></div>')
    return (f'<div class="v v-doc"><div class="v-head"><h1 class="v-h1">{_v(e.get("name"))}{badges}</h1>'
            f'<span class="v-cap">{_v(cap)}</span></div>{who_picker}{body}{foot}</div>')



PHRASES = {"located in": "located_in", "has status": "has_status", "possesses": "possesses", "knows": "knows",
           "relationship": "relationship", "role toward": "role_toward", "feels toward": "feels_toward",
           "addresses": "addresses", "identity": "identity", "has trait": "has_trait", "member of": "member_of",
           "world fact": "world_fact", "event": "event", "goal": "goal", "promised": "promised", "owes": "owes",
           "question": "question", "threat": "threat"}
PLAIN_KO = {"knows": "앎", "identity": "정체", "has_trait": "특징", "member_of": "소속", "world_fact": "세계",
            "event": "사건", "promised": "약속", "owes": "빚"}


def plain(text: str, lang: str) -> str:
    """A ledger line in the panel's words (PHASE-52 D5): the predicate's English name after the subject in the
    chat's language, and "story 0–71:" as "t0–71:"."""
    text = re.sub(r"^(story|scene) (\d+[–-]\d+):", r"t\2:", text)
    if lang == "en":
        return text
    for phrase, pred in PHRASES.items():
        word = PLAIN_KO.get(pred) or (T[pred][0] if pred in T else None)
        if word and f" {phrase}" in text:
            return text.replace(f" {phrase}", f" {word}", 1)
    return text


KIND_ORDER = ("state", "summary", "cast", "thread", "fact", "claim", "secret", "excerpt", "quote")


def working(d: dict[str, Any], lang: str) -> str:
    """Whether NMOS is working for this chat, in plain words (PHASE-52 D5): this reply, the memory just sent as lines
    grouped by kind, processing with retry, usage; the machinery is under details."""
    conv = d["conv"]
    cid = conv["id"]
    r = d.get("reply")
    if r is None:
        reply = f'<p class="v-text">{_v(t(lang, "no_reply"))}</p>'
        sent = f'<p class="v-text">{_v(t(lang, "none_yet"))}</p>'
    else:
        placed = [x for x in r.get("lines") or [] if x.get("placed")]
        head = t(lang, "reply_ok", n=len(placed), tok=f"{r.get('tokens') or 0:,}", s=f"{(r.get('ms') or 0) / 1000:.1f}") \
            if placed else t(lang, "reply_none")
        reply = line(_v(head), _v(str(r.get("at") or "")[:16].replace("T", " ")))
        groups = []
        for kind in KIND_ORDER + tuple(sorted({x.get("kind") for x in placed} - set(KIND_ORDER) - {None})):
            items = [line(_v(plain(x.get("text") or "", lang)),
                          f'<span class="v-tag k-echo">{_v(t(lang, "echoed"))}</span>' if x.get("echoed") else "")
                     for x in placed if x.get("kind") == kind]
            if items:
                label = t(lang, f"k_{kind}") if f"k_{kind}" in T else kind
                groups.append(f'<h2 class="v-h2 v-small">{_v(label)}'
                              f'<span class="v-n">{len(items)}</span></h2>{more(items, lang)}')
        sent = "".join(groups) or f'<p class="v-text">{_v(t(lang, "reply_none"))}</p>'
    w = d.get("work") or {}
    rows = []
    failed = 0
    for key, done, due in (("extraction", "compiled", "eligible"), ("embeddings", "embedded", "eligible"),
                           ("summaries", None, None), ("canon", "read", "wanted")):
        x = w.get(key) or {}
        f_count = int(x.get("failed") or 0)
        failed += f_count
        main = f"{t(lang, 'w_' + key)} · " + (f"{x.get(done, 0)}/{x.get(due, 0)}" if done else t(lang, "w_made", n=x.get("produced", 0)))
        bar = _progress(int(x.get(done, 0) or 0), int(x.get(due, 0) or 0), f_count > 0) if done else ""
        rows.append(line(_v(main), _v(t(lang, "w_counts", f=f_count, p=x.get("pending", 0))), bar))
    retry = ""
    if failed:
        errs = "".join(f'<p class="v-note">{_v(str(e)[:200])}</p>' for e in (d.get("errors") or [])[:3])
        retry = (f'<span class="has-failed"></span>{errs}'
                 f'<p><a class="v-name" data-act="retry">{_v(t(lang, "retry"))}</a></p>')
    u = d.get("usage") or {}
    usage = (line(_v(f"{t(lang, 'u_calls')} · {u.get('calls', 0):,}"))
             + line(_v(f"{t(lang, 'u_tokens')} · {u.get('input', 0):,} · {u.get('output', 0):,}")))
    body = (section("s-reply", lang, reply) + section("s-sent", lang, sent) + section("s-work", lang, "".join(rows) + retry)
            + section("s-usage", lang, usage))
    return (f'<div class="v v-doc"><div class="v-head"><h1 class="v-h1">{_v(t(lang, "ok") if not failed else t(lang, "warn"))}</h1>'
            f'<span class="v-cap">{_v(conv.get("name") or "")}</span></div>{body}'
            f'<div class="v-foot"><a href="/inspector/c/{cid}">{_v(t(lang, "details"))}</a></div></div>')



def chats(rows: list[dict[str, Any]], lang: str, current: str | None = None) -> str:
    """The chats NMOS knows (PHASE-52 D7), the most recently used first; each opens its hub. The search box is put in
    `.v-filter` by the panel (its sanitizer keeps no input) or by the browser page's script."""
    items = []
    for r in rows:
        cid = str(r["id"])
        when = r.get("last_retrieval") or r.get("created_at")
        iso = when.isoformat() if hasattr(when, "isoformat") else str(when or "")
        meta = [r.get("host_character_name") or "", t(lang, "c_msgs", n=r.get("messages") or 0)]
        failed = f' · <span class="v-warn">{_v(t(lang, "c_failed", n=r["failed"]))}</span>' if r.get("failed") else ""
        now = f' · <b>{_v(t(lang, "c_open"))}</b>' if cid == current else ""
        main = f'<a class="v-name" href="/views/hub?conversation={cid}">{_v(r.get("host_chat_name") or t(lang, "c_unnamed"))}</a>'
        items.append(f'<div class="v-line v-chat">{main}<div class="v-meta">{_v(" · ".join(m for m in meta if m))} · '
                     f'<span class="ts" title="{_v(iso)}">{_v(iso[:16].replace("T", " "))}</span>{failed}{now}</div></div>')
    return (f'<div class="v v-doc"><div class="v-head"><h1 class="v-h1">{_v(t(lang, "c_title"))}</h1>'
            f'<span class="v-cap">{len(rows)}</span></div><div class="v-filter"></div>{"".join(items)}</div>')



# --- the memory map (PHASE-55) -------------------------------------------------------------------------------------------

def _pct(n: int, total: int) -> int:
    return round(n * 100 / total) if total else 0


def _stack(counts: dict[str, int]) -> str:
    """A quiet stacked bar of the four sources, placed like the timeline's marks (`data-l`, `data-w`)."""
    from .memorymap import SOURCES
    total, left, segs = sum(counts.get(s, 0) for s in SOURCES), 0.0, []
    for s in SOURCES:
        if not counts.get(s) or not total:
            continue
        w = round(counts[s] * 100 / total, 1)
        segs.append(f'<span class="v-seg {s}" data-l="{round(min(left, 100), 1):g}" data-w="{min(w, 100):g}"></span>')
        left += w
    return f'<div class="v-stack">{"".join(segs)}</div>'


def _src_counts(row: dict[str, int], lang: str) -> str:
    from .memorymap import SOURCES
    return " · ".join(f'<span class="g-m {s}">{_v(t(lang, "src." + s))}</span> {row[s]}' for s in SOURCES if row.get(s))


def _sources(src: dict[str, Any], lang: str) -> str:
    """Section 1: the whole on top (its shares and the story's facts per turn), then a line per kind of fact."""
    total, n = src["total"], src["facts"]
    head = t(lang, "src_head", n=n, a=_pct(total["setting"], n),
             b=_pct(total["over"] + total["story"] + total["owner"], n))
    out = line(_v(head), _src_counts(total, lang), _stack(total)) if n else \
        f'<p class="v-text">{_v(t(lang, "none_yet"))}</p>'
    if src.get("per_turn") is not None:
        out += f'<p class="v-note">{_v(t(lang, "src_turn", x=f"{src['per_turn']:g}", last=src["turns"] - 1))}</p>'
    rows = [line(_v(word(r["predicate"], lang)), _src_counts(r, lang), _stack(r)) for r in src["rows"]]
    return out + more(rows, lang, 6)


def _tie_text(e: dict[str, Any], lang: str) -> str:
    """What an edge carries: each fact with its direction when it holds one way, the forms of address last (Q4)."""
    if e["kind"] != "tie":
        return f'{t(lang, "member" if e["kind"] == "group" else "here")} {_named(e["facts"][0], "object")}'
    bits = []
    for f in e["facts"] + e["speech"]:
        value = f'"{f.get("value")}"' if f["predicate"] == "addresses" else f.get("value")
        cond = f" [{label}]" if (label := cond_label(f, lang)) else ""  # PHASE-64; PHASE-66 part 5: any slot
        if f["predicate"] == "relationship" and symmetric(f.get("value")):
            bits.append(f"{word('relationship', lang)}{cond} {value}")
        else:
            bits.append(f"{_named(f, 'subject')}→{_named(f, 'object')} {word(f['predicate'], lang)}{cond} {value}")
    return ", ".join(bits)


def _map_link(cid: str, n: dict[str, Any], lang: str, sheet: bool = False) -> str:
    """A node's name, leading to that person's own map (Q6) or to their sheet; the persona marked as "you"."""
    you = f' <span class="v-meta">{_v(t(lang, "you"))}</span>' if n.get("persona") else ""
    if n.get("entity") and n["kind"] == "character":
        href = f"/views/c/{cid}/person/{n['entity']}" if sheet else f"/views/c/{cid}/map?focus={n['entity']}"
        return f'<a class="v-name" href="{href}">{_v(n["name"])}</a>{you}'
    return _v(n["name"]) + you


def _ties(cid: str, g: dict[str, Any], lang: str, focus: str | None) -> str:
    """Section 2 as lines: each character with their ties, most first, each marked setting, story or changed; then the
    groups and places; then the names that may be one person (Q5)."""
    by = {n["id"]: n for n in g["nodes"]}
    of: dict[str, list[dict[str, Any]]] = {}
    for e in g["edges"]:
        of.setdefault(e["a"], []).append(e)
        if e["kind"] == "tie":
            of.setdefault(e["b"], []).append(e)
    chars = sorted((n for n in g["nodes"] if n["kind"] == "character" and of.get(n["id"])),
                   key=lambda n: (-len(of[n["id"]]), n["name"]))
    if focus is not None:
        chars = [n for n in chars if n["id"] == focus]
    lines = []
    for n in chars:
        bits = []
        for e in sorted(of[n["id"]], key=lambda e: e["kind"] != "tie"):
            other = by[e["b"] if e["a"] == n["id"] else e["a"]]
            who = f"{_map_link(cid, other, lang)}: " if e["kind"] == "tie" else ""
            mk = f'<span class="g-m {e["mark"]}">{_v(t(lang, "mk." + e["mark"]))}</span>'
            bits.append(f'{who}{_v(_tie_text(e, lang))} {mk}')
        lines.append(line(_map_link(cid, n, lang, sheet=focus is not None), "<br>".join(bits)))
    out = more(lines, lang) or f'<p class="v-text">{_v(t(lang, "none_yet"))}</p>'
    if focus is None:
        for kind in ("group", "place"):
            items = []
            for n in sorted((x for x in g["nodes"] if x["kind"] == kind), key=lambda x: (-x["ties"], x["name"])):
                who = [by[e["a"]] for e in g["edges"] if e["b"] == n["id"]]
                items.append(line(_v(n["name"]), ", ".join(_map_link(cid, w, lang) for w in who)))
            if items:
                out += (f'<h2 class="v-h2 v-small">{_v(t(lang, "g_" + kind))}<span class="v-n">{len(items)}</span></h2>'
                        + more(items, lang))
    sus = [s for s in g["suspects"] if focus is None or focus in (s["full"]["id"], s["short"]["id"])]
    if sus:
        items = [line(" · ".join(_map_link(cid, {**s[k], "entity": s[k]["id"], "kind": "character"}, lang, sheet=True)
                                 for k in ("full", "short")), _v(t(lang, "suspect_meta"))) for s in sus]
        out += (f'<h2 class="v-h2 v-small">{_v(t(lang, "suspect"))}<span class="v-n">{len(items)}</span></h2>'
                + more(items, lang))
    if focus is None:
        notes = [t(lang, "no_ties", n=g["idle"]) if g.get("idle") else "",
                 t(lang, "left_out", n=g["excluded"]) if g.get("excluded") else ""]
        out += "".join(f'<p class="v-note">{_v(x)}</p>' for x in notes if x)
    return out


DRAWN_WIDTH = 760  # the page's width: a drawing wider than this is shown smaller
DRAWN_NAMES_TO = 1400  # past this width names would overlap into a blot (PHASE-55 amendment 2)
NAME_MAX = 24  # a drawn name's length (graph.ts NAME_MAX); the whole name is in its <title> and the lines below


def _svg(cid: str, d: dict[str, Any], lang: str, every_name: bool = False) -> str:
    """The drawing (Q2): inline SVG of circles, lines and text, no script; a character leads to their own map. It fits
    the page's width whatever its size, so dots and names grow with a large drawing to stay readable, and past
    DRAWN_NAMES_TO only the scene's cast and the persona keep a name on it (`every_name`: all of them, one person's map):
    the others' are in their <title> and the lines below. A name by a side of the drawing runs inward, so it stays in."""
    pos, r = d["pos"], d["radius"]
    grow = max(1.0, 2 * (r + 40) / DRAWN_WIDTH)
    mx = my = 40 * grow
    w, h = round(2 * (r + mx)), round(2 * (r + my) + 30 * grow)
    size_style = f' style="font-size:{16 * grow:.0f}px"' if grow > 1 else ""
    lines = []
    for e in d["edges"]:
        (x1, y1), (x2, y2) = pos[e["a"]], pos[e["b"]]
        lines.append(f'<line class="g-e {e["mark"]}" x1="{x1:g}" y1="{y1:g}" x2="{x2:g}" y2="{y2:g}"/>')
    for s in d["suspects"]:
        (x1, y1), (x2, y2) = pos[s["full"]["id"]], pos[s["short"]["id"]]
        lines.append(f'<line class="g-e split" x1="{x1:g}" y1="{y1:g}" x2="{x2:g}" y2="{y2:g}"/>')
    dots = []
    for n in d["nodes"]:
        x, y = pos[n["id"]]
        lead = " lead" if n["scene"] or n["persona"] else ""
        size = round((11 if lead else 8) * grow, 1)
        name = n["name"] + (f" ({t(lang, 'you')})" if n["persona"] else "")
        short = name if len(name) <= NAME_MAX else name[:NAME_MAX - 1] + "…"
        side = "start" if x < -r / 3 else "end" if x > r / 3 else "middle"
        label = (f'<text class="g-t{lead}" x="{x:g}" y="{y + size + 18 * grow:g}" text-anchor="{side}"{size_style}>'
                 f'{_v(short)}</text>') if lead or every_name or w <= DRAWN_NAMES_TO else ""
        dot = (f'<g><title>{_v(name)}</title><circle class="g-n {n["kind"]}{lead}" cx="{x:g}" cy="{y:g}" r="{size:g}"/>'
               f'{label}</g>')
        if n.get("entity") and n["kind"] == "character":
            dot = f'<a href="/views/c/{cid}/map?focus={n["entity"]}">{dot}</a>'
        dots.append(dot)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="{-r - mx:g} {-r - my:g} {w} {h}"'
            f' role="img" aria-label="{_v(t(lang, "s-ties"))}">{"".join(lines)}{"".join(dots)}</svg>')


def _drawing(cid: str, g: dict[str, Any], lang: str, focus: str | None, everyone: bool) -> str:
    """The browser page's drawing above the lines: the whole map hidden on a phone (Q6), one person's map shown; what
    the caps leave out is counted, with a link that draws everyone (Q7, owner 2026-11-02)."""
    from .memorymap import drawn
    d = drawn(g, focus, everyone)
    if not d["edges"]:
        return ""
    cls = "v-graph one" if focus is not None else "v-graph whole"  # one person's map fits a phone's width
    toggle = ""
    if d["left"]:
        what = ", ".join(t(lang, f"n_{k}", n=n) for k, n in d["left"].items())
        toggle = (f'{_v(t(lang, "drawn_left", what=what))} · '
                  f'<a class="v-name" href="/views/c/{cid}/map?all=1#s-ties">{_v(t(lang, "show_all"))}</a>')
    elif everyone:
        toggle = f'<a class="v-name" href="/views/c/{cid}/map#s-ties">{_v(t(lang, "show_less"))}</a>'
    return (f'<div class="{cls}">{_svg(cid, d, lang, focus is not None)}<p class="v-note">{_v(t(lang, "legend"))}</p>'
            + (f'<p class="v-note">{toggle}</p>' if toggle else "") + "</div>")


def _event_line(cid: str, e: dict[str, Any], ents: dict[str, str], lang: str) -> str:
    meta = " · ".join(x for x in (t(lang, "with", who=", ".join(e["participants"])) if e["participants"] else "",
                                  t(lang, "because", why=e["because"]) if e.get("because") else "") if x)
    turn = f't{e["turn"]}' if isinstance(e["turn"], int) else ""
    return (f'<div class="v-ev{" major" if e.get("salience") == "major" else ""}"><span class="v-t">{turn}</span>'
            f'<span class="v-d"></span><span class="v-x">{name_link(cid, ents, e["subject"])} — {_v(e["text"])}'
            + (f'<br><span class="v-meta">{_v(meta)}</span>' if meta else "") + "</span></div>")


def _events(cid: str, evs: list[dict[str, Any]], last: int, ents: dict[str, str], lang: str) -> str:
    """Section 3 as PHASE-52 D4 amendment 2 draws a person's changes, for the whole chat: the overview bar, then the
    lines by span of turns, the latest span open, the earlier ones folded (Q7: at most EVENT_LINES, the earliest
    counted)."""
    from .memorymap import EVENT_LINES
    from .timeline import circles
    if not evs:
        return f'<p class="v-text">{_v(t(lang, "none_yet"))}</p>'
    spans = circles([(e["turn"], e.get("salience") == "major", e["text"]) for e in evs if isinstance(e["turn"], int)],
                    0, last)
    shown = evs[-EVENT_LINES:]
    size = max(10, -(-(last + 1) // 6))  # at most six spans
    groups: dict[int, list[dict[str, Any]]] = {}
    for e in shown:
        groups.setdefault((e["turn"] if isinstance(e["turn"], int) else 0) // size, []).append(e)
    out = overview(spans, 0, last, lang)
    for i, (k, items) in enumerate(sorted(groups.items(), reverse=True)):
        body = "".join(_event_line(cid, e, ents, lang) for e in items)
        if i == 0:
            out += body
        else:
            label = t(lang, "ev_span", lo=k * size, hi=min(k * size + size - 1, last), n=len(items))
            out += f'<details class="v-more"><summary>{_v(label)}</summary>{body}</details>'
    if len(evs) > len(shown):
        out += f'<p class="v-note">{_v(t(lang, "ev_left", n=len(evs) - len(shown)))}</p>'
    return out + f'<p class="v-note">{_v(t(lang, "tl_hint"))}</p>'


DEPTH = (("d_part", "participants"), ("d_because", "because"), ("d_outcome", "outcome"))


def _depth(dp: dict[str, Any], lang: str) -> str:
    """Section 4: the shares of the story's events with someone else, a reason and an outcome, their weights, and what
    an event record cannot hold; per extractor generation under details (an identifier, PHASE-52 D8)."""
    n = dp["events"]
    if not n:
        return f'<p class="v-text">{_v(t(lang, "none_yet"))}</p>'
    out = "".join(line(_v(f"{t(lang, key)} · {dp[k]}/{n} · {_pct(dp[k], n)}%")) for key, k in DEPTH)
    out += line(_v(t(lang, "d_weight", a=dp["major"], b=dp["minor"], c=dp["none"])))
    out += f'<p class="v-note">{_v(t(lang, "d_note"))}</p>'
    rows = "".join(line(_v(k), _v(" · ".join(f"{t(lang, key)} {g[k2]}/{g['events']}" for key, k2 in DEPTH)))
                   for k, g in (dp.get("by_generation") or {}).items())
    return out + (f'<details class="v-more"><summary>{_v(t(lang, "d_gen"))}</summary>{rows}</details>' if rows else "")


def map_graph(d: dict[str, Any], lang: str, focus: str | None = None, everyone: bool = False) -> dict[str, Any]:
    """The drawing as data, for the panel to draw itself (PHASE-55 step 6): positions from the same rings (Q2), names
    as text the plugin never parses as markup, the marks from a fixed set, and the panel's words for its controls."""
    from .memorymap import drawn
    g = d["map"]["graph"]
    if focus not in {n["id"] for n in g["nodes"]}:
        focus = None
    dr = drawn(g, focus, everyone)
    nodes = [{"id": n["id"], "name": n["name"] + (f" ({t(lang, 'you')})" if n["persona"] else ""), "kind": n["kind"],
              "lead": bool(n["scene"] or n["persona"]), "entity": n["entity"] if n["kind"] == "character" else None,
              "x": dr["pos"][n["id"]][0], "y": dr["pos"][n["id"]][1]} for n in dr["nodes"]]
    left = ", ".join(t(lang, f"n_{k}", n=n) for k, n in dr["left"].items())
    return {"nodes": nodes, "edges": [{"a": e["a"], "b": e["b"], "kind": e["kind"], "mark": e["mark"]} for e in dr["edges"]],
            "suspects": [{"a": s["full"]["id"], "b": s["short"]["id"]} for s in dr["suspects"]],
            "focus": focus, "everyone": everyone, "capped": bool(dr["left"]),
            "words": {"legend": t(lang, "legend"), "fit": t(lang, "g_fit"), "all": t(lang, "show_all"),
                      "fewer": t(lang, "show_less"), "tap": t(lang, "g_tap"), "ties": t(lang, "g_ties", n="{n}"),
                      "left": t(lang, "drawn_left", what=left) if left else ""}}


def memory_map(d: dict[str, Any], lang: str, focus: str | None = None, everyone: bool = False,
               page: bool = False) -> str:
    """The memory map (PHASE-55): where the facts came from, who is tied to whom, what happened when, and how much an
    event record holds. The panel's fragment is lines in its tags only (Q3); the browser page (`page`) adds the
    drawing as inline SVG, the one place where a browser page carries markup the panel's fragment does not. With
    `focus` (an entity on the map), that person and their ties only (Q6); `everyone` draws past the caps (Q7)."""
    conv, m, ents = d["conv"], d["map"], d.get("entities") or {}
    cid, g = conv["id"], m["graph"]
    by = {n["id"]: n for n in g["nodes"]}
    if focus not in by:
        focus = None
    drawing = _drawing(cid, g, lang, focus, everyone) if page else \
        f'<p class="v-note v-graph-note">{_v(t(lang, "panel_graph", cid=cid))}</p>'
    ties = section("s-ties", lang, drawing + _ties(cid, g, lang, focus))
    if focus is not None:
        head, body = t(lang, "focus", name=by[focus]["name"]), ties
        foot = (f'<div class="v-foot"><a href="/views/c/{cid}/map">{_v(t(lang, "whole_map"))}</a> · '
                f'<a href="/views/c/{cid}/person/{focus}">{_v(t(lang, "sheet"))}</a></div>')
    else:
        told = _told_section(cid, d.get("told"), ents, lang)
        keys = ["s-src", "s-ties", "s-events", "s-depth"] + (["s-told"] if told else [])
        chips = '<div class="v-chips">' + "".join(f'<a href="#{k}">{_v(t(lang, k))}</a>' for k in keys) + "</div>"
        head = t(lang, "map")
        body = (chips + section("s-src", lang, _sources(m["sources"], lang)) + ties
                + section("s-events", lang, _events(cid, m["events"], m["last"], ents, lang), len(m["events"]))
                + section("s-depth", lang, _depth(m["depth"], lang)) + told)
        foot = (f'<div class="v-foot"><a href="/views/c/{cid}/memory">{_v(t(lang, "back_memory"))}</a> · '
                f'<a href="/inspector/c/{cid}">{_v(t(lang, "details"))}</a></div>')
    cap = " · ".join(str(x) for x in (conv.get("name"), f"t{conv['turns']}" if conv.get("turns") is not None else None)
                     if x)
    return (f'<div class="v v-doc v-map"><div class="v-head"><h1 class="v-h1">{_v(head)}</h1>'
            f'<span class="v-cap">{_v(cap)}</span></div>{body}{foot}</div>')


def _told_section(cid: str, rows: list[dict[str, Any]] | None, ents: dict[str, str], lang: str) -> str:
    """Who told whom (PHASE-60 S8): chains oldest first, names linked to their sheet; empty without rows."""
    if not rows:
        return ""
    from .memorymap import told_chains
    chains = told_chains(rows)
    if not chains:
        return ""
    items = []
    for chain in chains:
        people = [chain[0]["teller"], *(link["hearer"] for link in chain)]
        who = " → ".join(name_link(cid, ents, name) for name in people)
        turns = [f"t{link['turn']}" for link in chain
                 if isinstance(link.get("turn"), int) and not isinstance(link.get("turn"), bool)]
        when = f" ({' → '.join(turns)})" if turns else ""
        about = list(dict.fromkeys(w for link in chain for w in link.get("about") or ()))
        meta = _v(t(lang, "told_about", who=", ".join(about))) if about else ""
        items.append(line(f"{who}: {_v(chain[0]['what'])}{when}", meta))
    return section("s-told", lang, more(items, lang), len(items))


# --- PHASE-69: Memory Explorer & Focused Attention & Repairs (card-based, zero tables) ----------------------------------

_CTRL = re.compile(r"[\x00-\x1f\x7f|]+")
_RQ_MARK = re.compile(r'<span class="rq" data-bulk="[^"]*"></span>')


def _who_attr(names: Any) -> str:
    """Safe read-only `data-who` attribute for client-side character filtering (PHASE-69 S1)."""
    seen: list[str] = []
    used: set[str] = set()
    total = 0
    for raw in names:
        clean = _CTRL.sub(" ", str(raw or "")).strip()
        if not clean:
            continue
        key = clean.casefold()
        if key in used:
            continue
        add = len(clean) + (1 if seen else 0)
        if total + add > 240:
            if not seen:
                seen.append(clean[:240])
            break
        used.add(key)
        seen.append(clean)
        total += add
    return f' data-who="{_v("|".join(seen))}"' if seen else ""


def _edit_drawer(acts_html: str, lang: str) -> str:
    """Tidy collapsible edit drawer wrapping existing repair markers (`span.rp`)."""
    if not acts_html:
        return ""
    return (f'<details class="v-edit"><summary>{_v(t(lang, "ex_edit"))}</summary>'
            f'<div class="v-edit-body">{acts_html}</div></details>')


def _fact_acts(f: dict[str, Any], *, include_hidden: bool = False) -> str:
    """Repair markers for one current fact row (PHASE-69 / PHASE-70): retract, correct, hidden-from, lock, undo."""
    if f.get("carried") or f.get("id") is None:
        return ""
    acts = ""
    if f.get("owner"):
        if f.get("repair"):
            acts += _act("undo", f["repair"])
        if not f.get("locked"):
            acts += _act("fact_lock", f["id"])
        if f.get("locked"):
            acts += _act("undo", f["locked"])
        return acts
    acts += _act("fact_retract", f["id"]) + "".join(_act("fact_correct", f["id"], x) for x in _corrections(f))
    if include_hidden and not f.get("canon"):
        acts += _act("fact_hidden", f["id"])
    if f.get("canon") and not f.get("locked"):
        acts += _act("fact_lock", f["id"])
    if f.get("locked"):
        acts += _act("undo", f["locked"])
    return acts


def _pair_edit_rows(p: dict[str, Any], lang: str) -> str:
    """Per-fact editable rows for a relationship/role/feeling/address pair card (PHASE-70)."""
    rows: list[str] = []
    for key in ("relationship", "role", "feels", "speech"):
        for f in p.get(key) or ():
            f_acts = _fact_acts(f, include_hidden=True)
            if not f_acts:
                continue
            lbl = f"{word(str(f.get('predicate') or ''), lang)} · {_named(f, 'subject')}→{_named(f, 'object')}: {_slotted(f, lang)}"
            rows.append(f'<div class="v-edit-row"><span class="v-edit-lbl">{_v(lbl)}</span>{f_acts}</div>')
    return "".join(rows)


def _entity_note_box(note: dict[str, Any] | None, lang: str) -> str:
    """Visible callout showing an entity's owner description note (PHASE-70, ADR 0096)."""
    text = str((note or {}).get("text") or "").strip()
    if not text:
        return ""
    return (f'<div class="v-note-box"><span class="v-tag k-owner">{_v(t(lang, "ex_note"))}</span>'
            f'<span class="v-note-text">{_v(text)}</span></div>')


def _entity_note_acts(eid: str | None, note: dict[str, Any] | None) -> str:
    """Inline repair buttons for adding/editing/removing an entity's owner note (PHASE-70)."""
    if not eid:
        return ""
    rid = (note or {}).get("repair") or (note or {}).get("id")
    return _act("entity_note", eid, "edit" if note else "add") + (_act("undo", rid) if rid else "")


def _turn_badge(row: dict[str, Any], lang: str) -> str:
    """A source-turn link (`tN`) or setting/carried label on the right of a card header."""
    if row.get("carried"):
        src = row.get("carried_from")
        turn = _turn_of(src.get("turn")) if isinstance(src, dict) else None
        label = t(lang, "carry_turn", t=turn) if turn is not None else t(lang, "carried")
        href = carry_href(row)
        return f'<a href="{_v(href)}">{_v(label)}</a>' if href else _v(label)
    if row.get("canon"):
        return f'<span title="{_v(row["canon"])}">{_v(t(lang, "ex_setting"))}</span>'
    turn = row.get("turn")
    if isinstance(turn, int) and not isinstance(turn, bool):
        return turn_link(turn, f"t{turn}")
    pos = row.get("position")
    return _v(f"#{pos}") if pos is not None else ""


def _fact_card(f: dict[str, Any], cid: str, ents: dict[str, str], lang: str, *, under: bool = False,
               with_cat: bool = True) -> str:
    """One fact as a responsive card with source badges, turn link, and collapsible repair drawer."""
    pred = str(f.get("predicate") or "")
    badges = [f'<span class="v-tag">{_v(word(pred, lang))}</span>']
    if f.get("canon"):
        badges.append(f'<span class="v-tag k-setting">{_v(t(lang, "ex_setting"))}</span>')
    if f.get("owner"):
        badges.append(f'<span class="v-tag k-owner">{_v(t(lang, "ex_owner"))}</span>')
    if f.get("locked"):
        badges.append(f'<span class="v-tag k-locked">{_v(t(lang, "ex_locked"))}</span>')
    if f.get("carried"):
        badges.append(carried_mark(f, lang))
    if f.get("polarity") == "negative":
        badges.append(f'<span class="v-tag k-err">{_v(t(lang, "ex_neg"))}</span>')
    if f.get("disputed_by"):
        badges.append(f'<span class="v-tag k-warn">{_v(t(lang, "ex_disputed"))}</span>')
    if label := cond_label(f, lang):
        badges.append(f'<span class="v-tag k-info">{_v(label)}</span>')
    if f.get("predicate") == "event" and f.get("salience") in ("major", "minor"):
        badges.append(f'<span class="v-tag">{_v(_it(lang, "s." + f["salience"]))}</span>')

    subj = _named(f, "subject")
    obj = _named(f, "object") if f.get("object") else ""
    val = f.get("value")
    subj_html = name_link(cid, ents, subj)
    obj_html = name_link(cid, ents, obj) if obj else ""
    prefix = "↳ " if under else ""
    if obj_html and val not in (None, ""):
        main = f'{prefix}{subj_html} → {obj_html}: {_v(val)}'
    elif obj_html:
        main = f'{prefix}{subj_html} → {obj_html}'
    elif val not in (None, ""):
        main = f'{prefix}{subj_html}: {_v(val)}'
    else:
        main = f'{prefix}{subj_html}'
    if cond_notes := cond_extra(f, lang):
        main += " " + " ".join(f'<span class="v-meta">({_v(x)})</span>' for x in cond_notes)
    if f.get("item_kind") == "fungible":
        badges.append(f'<span class="v-tag">{_v(_it(lang, "fungible"))}</span>')

    sub_bits: list[str] = []
    if with_html := _with(f, lang):
        sub_bits.append(f'{_v(t(lang, "with", who="").strip())} {with_html}')
    if f.get("because"):
        cause = f"{t(lang, 'because', why=f['because'])}"
        if ce := f.get("cause_event"):
            when = ce["turn"] if ce.get("turn") is not None else ce.get("position")
            cause += f" · t{when}: {ce.get('text') or ''}"
        sub_bits.append(_v(cause))
    if h := happened_text(_own(f), lang):
        sub_bits.append(_v(h))
    if f.get("known_by") or f.get("hidden_from") or f.get("forgotten_by") or f.get("knowledge") in ("limited", "secret"):
        sub_bits.append(_knowledge(f, lang))

    acts = _fact_acts(f, include_hidden=True)

    who_names = [subj, obj] + [
        (p.get("entity") or {}).get("name") or p.get("name") for p in f.get("participant_entities") or []
    ]
    canon_attr = ' data-canon="1"' if f.get("canon") and not f.get("owner") else ""
    cat_attr = ' data-cat="facts"' if with_cat else ""
    cls = "v-card v-exp-card v-fact-card" if with_cat else "v-card v-fact-card"
    return (f'<div class="{cls}"{cat_attr}{_who_attr(who_names)}{canon_attr}>'
            f'<div class="v-card-top"><div class="v-card-badges">{"".join(badges)}</div>'
            f'<span class="v-card-turn">{_turn_badge(f, lang)}</span></div>'
            f'<div class="v-card-main">{main}</div>'
            + (f'<div class="v-card-sub">{" · ".join(sub_bits)}</div>' if sub_bits else "")
            + _edit_drawer(acts, lang) + "</div>")


def _disguise_card(dg: dict[str, Any], cid: str, ents: dict[str, str], lang: str, *, with_cat: bool = True) -> str:
    """One disguise entry as a card (extract-v21, PHASE-66 / PHASE-69)."""
    wearer = _named(dg, "subject")
    status = _it(lang, "dg.current" if dg.get("current") else "dg.over")
    badges = [f'<span class="v-tag k-info">{_v(t(lang, "ex_disguise"))}</span>',
              f'<span class="v-tag">{_v(status)}</span>']
    main = f'{name_link(cid, ents, wearer)} → {_v(dg.get("guise") or "")}'
    subs = []
    if kept := dg.get("kept_from") or []:
        subs.append(_v(t(lang, "kept", who=", ".join(str(x) for x in kept))))
    if rev := [str(x.get("to")) for x in dg.get("revealed") or [] if x.get("to")]:
        subs.append(_v(t(lang, "by", who=", ".join(rev))))
    cat_attr = ' data-cat="epistemic"' if with_cat else ""
    cls = "v-card v-exp-card" if with_cat else "v-card"
    return (f'<div class="{cls}"{cat_attr}{_who_attr([wearer, *(dg.get("kept_from") or [])])}>'
            f'<div class="v-card-top"><div class="v-card-badges">{"".join(badges)}</div>'
            f'<span class="v-card-turn">{_turn_badge(dg, lang)}</span></div>'
            f'<div class="v-card-main">{main}</div>'
            + (f'<div class="v-card-sub">{" · ".join(subs)}</div>' if subs else "") + "</div>")


def _canon_card(r: dict[str, Any], history: dict[str, dict[str, Any]], held: dict[str, dict[str, Any]],
                read: dict[str, dict[str, Any]] | None, lang: str) -> str:
    """One canon (card / lorebook / persona / note) entry as a stacked card — no 9-column table."""
    key = str(r.get("key") or "")
    src_kind = key.split(":")[0]
    src_label = _it(lang, f"cn.{src_kind}") if f"cn.{src_kind}" in _inspector_keys() else src_kind
    badges = [f'<span class="v-tag k-setting">{_v(src_label)}</span>']
    if read is not None:
        rx = read.get(key)
        if rx is None:
            r_txt = _it(lang, "cn.unread" if key.startswith("lore:") else "cn.none")
            badges.append(f'<span class="v-tag">{_v(r_txt)}</span>')
        elif rx.get("job") in ("queued", "running"):
            badges.append(f'<span class="v-tag k-info">{_v(_it(lang, "cn.reading"))}</span>')
        elif rx.get("job") == "dead":
            badges.append(f'<span class="v-tag k-err">{_v(_it(lang, "cn.failed"))}</span>')
        elif rx.get("calls"):
            badges.append(f'<span class="v-tag k-owner">{_v(_it(lang, "cn.read").format(n=rx["calls"]))}</span>')

    m = r.get("metadata") or {}
    meta_bits = [m.get("scope"), m.get("mode"), "always" if m.get("always_active") else None,
                 _it(lang, "cn.keys").format(n=len(m["keys"])) if m.get("keys") else None]
    content_str = r.get("content")
    if content_str is not None:
        meta_bits.append(t(lang, "ex_chars", n=f"{len(content_str):,}"))
    if h := held.get(key):
        meta_bits.append(_it(lang, "cn.held").format(n=h["requests"]))
    else:
        meta_bits.append(_it(lang, "cn.never"))
    vers = (history.get(key) or {}).get("versions", 1)
    if vers and vers > 1:
        meta_bits.append(f"v{vers}")

    preview = (_v(content_str[:180] + ("…" if len(content_str) > 180 else "")) if content_str is not None
               else f'<span class="v-warn">{_v(_it(lang, "cn.missing"))}</span>')
    return (f'<div class="v-card v-exp-card" data-cat="canon">'
            f'<div class="v-card-top"><div class="v-card-badges">{"".join(badges)}'
            f'<b>{_v(key)}</b></div></div>'
            f'<div class="v-card-main">{preview}</div>'
            f'<div class="v-card-sub">{_v(" · ".join(str(b) for b in meta_bits if b))}</div></div>')


def _inspector_keys() -> dict[str, Any]:
    from . import inspector as _insp
    return _insp.T


def explore(d: dict[str, Any], lang: str) -> str:
    """PHASE-69 S1: Card-based Memory Explorer promoting all reading & editing power of `자세히` with zero tables."""
    conv, ents = d["conv"], d.get("entities_map") or {}
    cid = conv["id"]
    nm = lambda name: name_link(cid, ents, name)  # noqa: E731
    persona_ids = frozenset(str(e["id"]) for e in d.get("entities") or [] if e.get("persona"))

    # 1. Facts
    raw_facts = (d.get("facts") or [])[:300]
    fact_by_id = {f["id"]: f for f in d.get("facts") or [] if f.get("id") is not None}
    notes_by_eid = {str(n["entity_id"]): n for n in d.get("entity_notes") or [] if n.get("entity_id")}
    excluded_map = d.get("excluded") or {}
    item_eid_by_name = {
        str(e.get("name") or "").casefold(): str(e["id"])
        for e in d.get("entities") or [] if e.get("type") == "item" and e.get("id")
    }
    grouped_facts, under = _guise_grouped(raw_facts)
    fact_cards = [_fact_card(f, cid, ents, lang, under=id(f) in under) for f in grouped_facts]

    # 2. Pairs (relationships, roles, feelings, addresses)
    pair_cards = []
    for p in (d.get("pairs") or [])[:100]:
        names_list = sorted(p["names"].values())
        rel = [_slotted(f, lang) for f in p["relationship"] if f.get("value")]
        head = " ↔ ".join(nm(n) for n in names_list) + (f" · {_v(', '.join(str(r) for r in rel))}" if rel else "")
        bits = _pair_bits(p, lang)
        if len(p["relationship"]) > 1 or any(not symmetric(f.get("value")) for f in p["relationship"]):
            bits = [_v(f"{_named(f, 'subject')}→{_named(f, 'object')} {t(lang, 'relationship')} {_slotted(f, lang)}")
                    + (f" {h}" if (h := happened_mark(_own(f), lang)) else "")
                    + (f" {m}" if (m := carried_mark(f, lang)) else "")
                    for f in p["relationship"]] + bits
        # Include previous value history if present
        hist_notes = []
        for k in ("relationship", "role", "feels", "speech"):
            for f in p[k]:
                if prev := earlier(f):
                    hist_notes.append(f"{_named(f, 'subject')}→{_named(f, 'object')}: {_it(lang, 'before')} {prev.get('value') or ''}")
        said_all = [f for k in ("relationship", "role", "feels", "speech") for f in p[k]]
        canon_only = bool(said_all) and all(f.get("canon") and not f.get("owner") for f in said_all)
        canon_attr = ' data-canon="1"' if canon_only else ""
        badges = [f'<span class="v-tag k-setting">{_v(t(lang, "ex_setting"))}</span>'] if canon_only else []
        edit_rows = _pair_edit_rows(p, lang)
        excl_marks = _exclude_marks(p, persona_ids)
        acts = edit_rows + (f'<div class="v-edit-row">{excl_marks}</div>' if excl_marks else "")
        pair_cards.append(
            f'<div class="v-card v-exp-card" data-cat="pairs"{_who_attr(names_list)}{canon_attr}>'
            + (f'<div class="v-card-top"><div class="v-card-badges">{"".join(badges)}</div></div>' if badges else "")
            + f'<div class="v-card-main">{head}</div>'
            + (f'<div class="v-card-sub">{"<br>".join(bits)}</div>' if bits else "")
            + (f'<div class="v-card-sub">{_v(" · ".join(hist_notes[:4]))}</div>' if hist_notes else "")
            + _edit_drawer(acts, lang) + "</div>"
        )

    # 3. Threads (promises, goals, questions, threats, debts — open first, then closed)
    raw_threads = (d.get("threads") or [])[:100]
    sorted_threads = sorted(raw_threads, key=lambda th: (0 if th.get("status") == "open" else 1))
    thread_cards = []
    for th in sorted_threads:
        st = str(th.get("status") or "open")
        st_label = _it(lang, f"t.{st}") if f"t.{st}" in _inspector_keys() else st
        badges = [_kind_tag(th.get("kind"), lang),
                  f'<span class="v-tag{" k-owner" if st == "open" else ""}">{_v(st_label)}</span>']
        if th.get("horizon") in ("scene", "arc", "lasting"):
            badges.append(f'<span class="v-tag">{_v(t(lang, "hz." + th["horizon"]))}</span>')
        if th.get("carried"):
            badges.append(carried_mark(th, lang))
        who_head = nm(th.get("by")) + (f" → {nm(th['to'])}" if th.get("to") else "")
        main = f'{who_head}: {_v(th.get("text") or "")}'
        subs = []
        if restated := [str(r["turn"] if r.get("turn") is not None else r["position"]) for r in th.get("restated") or []]:
            subs.append(_v(f"{_it(lang, 'h.restated')}: {', '.join(restated)}"))
        if c := th.get("closed_by"):
            c_txt = fact_line_text(c) if c.get("predicate") else (c.get("evidence") or _it(lang, "or.closed"))
            subs.append(_v(f"{_it(lang, 'h.closed')}: {c_txt}"))
        if h := happened_text(_own(th), lang):
            subs.append(_v(h))
        acts = ""
        if not th.get("carried"):
            if st == "open":
                acts = _close(th)
            elif not (th.get("closed_by") or {}).get("owner"):
                acts = _act("thread_reopen", th["id"])
        thread_cards.append(
            f'<div class="v-card v-exp-card" data-cat="threads"{_who_attr([th.get("by"), th.get("to")])}>'
            f'<div class="v-card-top"><div class="v-card-badges">{"".join(badges)}</div>'
            f'<span class="v-card-turn">{_turn_badge(th, lang)}</span></div>'
            f'<div class="v-card-main">{main}</div>'
            + (f'<div class="v-card-sub">{" · ".join(subs)}</div>' if subs else "")
            + _edit_drawer(acts, lang) + "</div>"
        )

    # 4. Epistemic (secrets, beliefs, forgotten, disguises, told chains)
    ep_cards = []
    for s in (d.get("secrets") or [])[:100]:
        is_open = bool(s.get("open"))
        badges = [f'<span class="v-tag{" k-warn" if is_open else ""}">{_v(t(lang, "ex_secret"))}</span>']
        holders = s.get("holders") or []
        kept_from = s.get("kept_from") or s.get("open") or []
        subs = []
        if holders:
            subs.append(_v(t(lang, "by", who=", ".join(holders))))
        if s.get("kept_from"):
            subs.append(_secret_status(s, lang))
        elif s.get("open"):
            subs.append(_v(t(lang, "kept", who=", ".join(s["open"]))))
        if h := happened_text(s, lang):
            subs.append(_v(h))
        sf = fact_by_id.get(s.get("id"))
        s_acts = _fact_acts(sf, include_hidden=True) if sf is not None else ""
        ep_cards.append(
            f'<div class="v-card v-exp-card" data-cat="epistemic"{_who_attr([*holders, *kept_from])}>'
            f'<div class="v-card-top"><div class="v-card-badges">{"".join(badges)}</div>'
            f'<span class="v-card-turn">{_turn_badge(s, lang)}</span></div>'
            f'<div class="v-card-main">{_v(content(s))}</div>'
            + (f'<div class="v-card-sub">{"<br>".join(subs)}</div>' if subs else "")
            + _edit_drawer(s_acts, lang) + "</div>"
        )
    for b in (d.get("beliefs") or [])[:100]:
        subj = _named(b, "subject")
        e = b.get("ended_by")
        state = t(lang, "b_ended", what=" ".join(str(x) for x in (e.get("predicate"), e.get("object"), e.get("value")) if x)) \
            if e else t(lang, "b_held")
        badges = [f'<span class="v-tag k-info">{_v(t(lang, "ex_belief"))}</span>',
                  f'<span class="v-tag">{_v(state)}</span>']
        ep_cards.append(
            f'<div class="v-card v-exp-card" data-cat="epistemic"{_who_attr([subj])}>'
            f'<div class="v-card-top"><div class="v-card-badges">{"".join(badges)}</div>'
            f'<span class="v-card-turn">{_turn_badge(b, lang)}</span></div>'
            f'<div class="v-card-main">{nm(subj)}: {_v(b.get("value") or "")}</div>'
            + _edit_drawer(_epistemic_acts(b), lang) + "</div>"
        )
    for g in (d.get("forgotten") or [])[:100]:
        who = str(g.get("who") or g.get("subject") or "")
        badges = [f'<span class="v-tag">{_v(t(lang, "ex_forgot"))}</span>']
        wd = g.get("withdrew") or []
        sub_txt = _v(t(lang, "f_withdrew", n=len(wd))) if wd else ""
        ep_cards.append(
            f'<div class="v-card v-exp-card" data-cat="epistemic"{_who_attr([who])}>'
            f'<div class="v-card-top"><div class="v-card-badges">{"".join(badges)}</div>'
            f'<span class="v-card-turn">{_turn_badge(g, lang)}</span></div>'
            f'<div class="v-card-main">{nm(who)}: {_v(_forgot_what(g, lang))}</div>'
            + (f'<div class="v-card-sub">{sub_txt}</div>' if sub_txt else "")
            + _edit_drawer(_epistemic_acts(g), lang) + "</div>"
        )
    for dg in (d.get("disguises") or [])[:50]:
        ep_cards.append(_disguise_card(dg, cid, ents, lang))
    if told_rows := d.get("told") or []:
        from .memorymap import told_chains
        for chain in told_chains(told_rows, include_id=True)[:60]:
            people = [chain[0]["teller"], *(link["hearer"] for link in chain)]
            who_html = " → ".join(nm(p) for p in people)
            turns = [turn_link(link["turn"], f"t{link['turn']}") for link in chain
                     if isinstance(link.get("turn"), int) and not isinstance(link.get("turn"), bool)]
            about = list(dict.fromkeys(w for link in chain for w in link.get("about") or ()))
            acts = "".join(_act("told_retract", link["id"]) for link in chain if link.get("id") is not None)
            ep_cards.append(
                f'<div class="v-card v-exp-card" data-cat="epistemic"{_who_attr([*people, *about])}>'
                f'<div class="v-card-top"><div class="v-card-badges">'
                f'<span class="v-tag">{_v(t(lang, "ex_told"))}</span></div>'
                f'<span class="v-card-turn">{" → ".join(turns)}</span></div>'
                f'<div class="v-card-main">{who_html}: {_v(chain[0]["what"])}</div>'
                + (f'<div class="v-card-sub">{_v(t(lang, "told_about", who=", ".join(about)))}</div>' if about else "")
                + _edit_drawer(acts, lang) + "</div>"
            )

    # 5. Items
    item_cards = []
    for item in (d.get("items") or [])[:100]:
        hist = item.get("history") or []
        canon_only = bool(hist) and all(h.get("canon") for h in hist)
        canon_attr = ' data-canon="1"' if canon_only else ""
        latest = next((h for h in reversed(hist) if h.get("outcome") == "current"), hist[-1] if hist else None)
        badges = [f'<span class="v-tag">{_v(_it(lang, "e.item"))}</span>']
        if canon_only:
            badges.append(f'<span class="v-tag k-setting">{_v(t(lang, "ex_setting"))}</span>')
        cur_html = _step(latest, lang) if latest else ""
        hist_fold = ""
        if len(hist) > 1:
            steps = "".join(f'<div class="v-card-sub">{_step(h, lang)}</div>' for h in hist)
            hist_fold = (f'<details class="v-more"><summary>{_v(t(lang, "ex_item_hist", n=len(hist)))}</summary>'
                         f'{steps}</details>')
        who_names = [h.get("subject") for h in hist if h.get("subject")]
        item_name = str(item.get("item") or "")
        item_eid = str(item["entity_id"]) if item.get("entity_id") else item_eid_by_name.get(item_name.casefold())
        ent_note = notes_by_eid.get(item_eid) if item_eid else None
        cur_fact = fact_by_id.get(item.get("fact_id"))
        edit_rows: list[str] = []
        if cur_fact is not None and (f_acts := _fact_acts(cur_fact, include_hidden=True)):
            edit_rows.append(f'<div class="v-edit-row"><span class="v-edit-lbl">{_v(t(lang, "ex_item_now"))}</span>{f_acts}</div>')
        if item_eid and (excluded_map.get(item_eid) or {}).get("scope") != "memory":
            edit_rows.append(
                f'<div class="v-edit-row"><span class="v-edit-lbl">{_v(t(lang, "ex_note"))}</span>'
                f'{_entity_note_acts(item_eid, ent_note)}</div>'
            )
        item_title = (f'<a class="v-name" href="/inspector/c/{cid}/e/{_v(item_eid)}">{_v(item_name)}</a>'
                      if item_eid else f'<b>{_v(item_name)}</b>')
        item_cards.append(
            f'<div class="v-card v-exp-card" data-cat="items"{_who_attr(who_names)}{canon_attr}>'
            f'<div class="v-card-top"><div class="v-card-badges">{"".join(badges)}{item_title}</div></div>'
            + (f'<div class="v-card-main">{cur_html}</div>' if cur_html else "")
            + _entity_note_box(ent_note, lang)
            + hist_fold
            + _edit_drawer("".join(edit_rows), lang) + "</div>"
        )

    # 6. Entities
    pinned_ids = {str(p.get("entity_id")) for p in d.get("pins") or []}
    sorted_ents = sorted(
        (d.get("entities") or [])[:150],
        key=lambda e: (0 if e.get("type") == "character" else 1, -int(e.get("mentions") or 0), str(e.get("name") or "")),
    )
    ent_cards = []
    for e in sorted_ents:
        eid = str(e["id"])
        etype = str(e.get("type") or "character")
        etype_lbl = _it(lang, f"e.{etype}") if f"e.{etype}" in _inspector_keys() else etype
        badges = [f'<span class="v-tag">{_v(etype_lbl)}</span>']
        if e.get("persona"):
            badges.append(f'<span class="v-tag k-info">{_v(t(lang, "you"))}</span>')
        if eid in pinned_ids:
            badges.append(f'<span class="v-tag k-locked">{_v(t(lang, "ps_pinned"))}</span>')
        if eid in excluded_map:
            badges.append(f'<span class="v-tag k-warn">{_v(t(lang, "ps_excluded"))}</span>')
        href = f"/views/c/{cid}/person/{eid}" if etype == "character" else f"/inspector/c/{cid}/e/{eid}"
        aka = [n for n in e.get("names") or [] if n != e.get("name")]
        who_names = [e.get("name"), *aka] if etype == "character" else []
        sheet_link = (f'<a class="v-pill-link" href="{href}">{_v(t(lang, "ex_open_sheet"))}</a>'
                      if etype == "character" else "")
        ent_note = notes_by_eid.get(eid)
        note_acts = _entity_note_acts(eid, ent_note) if (excluded_map.get(eid) or {}).get("scope") != "memory" else ""
        ent_cards.append(
            f'<div class="v-card v-exp-card" data-cat="entities"{_who_attr(who_names)}>'
            f'<div class="v-card-top"><div class="v-card-badges">{"".join(badges)}'
            f'<a class="v-name" href="{href}">{_v(e.get("name"))}</a></div>'
            f'<span class="v-card-turn">{_v(t(lang, "ex_mentions", n=e.get("mentions") or 0))}</span></div>'
            + (f'<div class="v-card-sub">{_v(t(lang, "aka", names=", ".join(aka)))}</div>' if aka else "")
            + _entity_note_box(ent_note, lang)
            + (f'<div class="v-dash-links">{sheet_link}</div>' if sheet_link else "")
            + _edit_drawer(note_acts, lang) + "</div>"
        )

    # 7. Canon (card / lorebook / persona / author's note)
    canon_rows = (d.get("canon_rows") or [])[:200]
    canon_hist = d.get("canon_history") or {}
    canon_held = d.get("canon_held") or {}
    canon_read = d.get("canon_read")
    canon_cards = [_canon_card(r, canon_hist, canon_held, canon_read, lang) for r in canon_rows]
    canon_note = note_blocks(canon_rows, conv.get("turns"), lang)

    cat_sections = [
        ("facts", "s-facts", fact_cards, ""),
        ("pairs", "s-pairs", pair_cards, ""),
        ("threads", "s-threads", thread_cards, ""),
        ("epistemic", "s-epistemic", ep_cards, ""),
        ("items", "s-items", item_cards, ""),
        ("entities", "s-entities", ent_cards, ""),
        ("canon", "s-canon", canon_cards, canon_note),
    ]
    jump_chips = '<div class="v-chips">' + "".join(
        f'<a href="#{sec_id}"><span>{_v(t(lang, sec_id))}</span>'
        + (f'<span class="v-chip-n">{len(cards)}</span>' if cards else "") + "</a>"
        for _, sec_id, cards, _ in cat_sections if cards
    ) + "</div>"

    sec_html = []
    for cat, sec_id, cards, extra_note in cat_sections:
        inner = (f'<div class="v-exp-list">{"".join(cards)}</div>' if cards
                 else f'<p class="v-text">{_v(t(lang, "ex_canon_empty" if cat == "canon" else "ex_empty"))}</p>')
        sec_html.append(
            f'<div class="v-sec" id="{sec_id}" data-cat="{cat}">'
            f'<h2 class="v-h2">{_v(t(lang, sec_id))}<span class="v-n">{len(cards)}</span></h2>'
            f'{extra_note}{inner}</div>'
        )

    cap = " · ".join(str(x) for x in (conv.get("character"),
                                     f"t{conv['turns']}" if conv.get("turns") is not None else None,
                                     t(lang, "facts", n=len(raw_facts))) if x)
    foot = (f'<div class="v-foot"><a href="/views/c/{cid}/memory">{_v(t(lang, "back_memory"))}</a> · '
            f'<a href="/views/c/{cid}/attention">{_v(t(lang, "attention"))}</a> · '
            f'<a href="/inspector/c/{cid}">{_v(t(lang, "raw_inspector"))}</a></div>')
    return (f'<div class="v v-doc v-explore"><div class="v-head">'
            f'<h1 class="v-h1">{_v(conv.get("name") or t(lang, "explore"))}</h1>'
            f'<span class="v-cap">{_v(cap)}</span></div>'
            f'<div class="v-exp-toolbar-slot">{jump_chips}</div>'
            f'{"".join(sec_html)}{foot}</div>')


def attention(d: dict[str, Any], lang: str) -> str:
    """PHASE-69 S2: Dedicated 3-section Attention & Repairs triage screen (zero tables, full Phase 57 bulk support)."""
    conv = d["conv"]
    cid = conv["id"]

    # 1. Needs attention queue (cards wrapping inspector._attention rows, preserving span.rq bulk & span.rp repair)
    queue = d.get("queue") or []
    attn_cards = []
    for issue_html, text_html, turn_html, acts_html in queue:
        rqs = "".join(_RQ_MARK.findall(acts_html))
        rps = _RQ_MARK.sub("", acts_html).strip()
        check_html = f'<span class="v-card-check">{rqs}</span>' if rqs else ""
        turn_str = str(turn_html or "")
        turn_disp = turn_link(int(turn_str), f"t{turn_str}") if turn_str.isdigit() else turn_str
        attn_cards.append(
            f'<div class="v-card v-card-warn">'
            f'<div class="v-card-top">{check_html}'
            f'<div class="v-card-badges"><span class="v-tag k-warn">{issue_html}</span></div>'
            + (f'<span class="v-card-turn">{turn_disp}</span>' if turn_disp else "")
            + f'</div><div class="v-card-main">{text_html}</div>'
            + (f'<div class="v-card-acts">{rps}</div>' if rps else "") + "</div>"
        )
    attn_body = (f'<div class="v-exp-list">{"".join(attn_cards)}</div>' if attn_cards
                 else f'<div class="v-empty">{_v(t(lang, "at_clear"))}</div>')

    # 2. Conflicts
    owned = d.get("owned_facts") or {}
    conflicts = (d.get("conflicts") or [])[:100]
    conflict_cards = []
    for c in conflicts:
        ckind = str(c.get("kind") or "disputed")
        ckind_lbl = _it(lang, f"cf.{ckind}") if f"cf.{ckind}" in _inspector_keys() else ckind
        against = c.get("against") or {}
        fields = _corrections(against) if against.get("predicate") else []
        acts = ""
        if ckind == "canon" and against.get("id") is not None:
            acts = (_act("fact_lock", against["id"]) + _act("fact_retract", against["id"])
                    + _fix(against["id"], fields, lock=True) + _fix(c["fact"], fields))
        elif ckind != "locked":
            mine = c.get("fact") in owned
            acts = (_act("undo", owned[c["fact"]]) if mine
                    else _act("fact_retract", c["fact"]) + _fix(c["fact"], fields))
            if against.get("id") is not None:
                acts += _fix(against["id"], fields)
        conflict_cards.append(
            f'<div class="v-card v-card-warn">'
            f'<div class="v-card-top"><div class="v-card-badges">'
            f'<span class="v-tag k-warn">{_v(ckind_lbl)}</span></div></div>'
            f'<div class="v-diff-block">'
            f'<div class="v-diff-row"><span class="v-tag k-setting">{_v(t(lang, "at_existing"))}</span>'
            f'{_v(fact_line_text(against)) if against.get("predicate") else ""} '
            f'<span class="v-card-turn">{_turn(against, lang) if against else ""}</span></div>'
            f'<div class="v-diff-row"><span class="v-tag k-info">{_v(t(lang, "at_new_story"))}</span>'
            f'{_v(c.get("text") or "")} <span class="v-card-turn">{_turn(c, lang)}</span></div>'
            f'</div>'
            + (f'<div class="v-card-acts">{acts}</div>' if acts else "") + "</div>"
        )
    conflicts_body = (f'<div class="v-exp-list">{"".join(conflict_cards)}</div>' if conflict_cards
                      else f'<p class="v-text">{_v(t(lang, "at_no_conflicts"))}</p>')

    # 3. Direct edits / Repairs
    repairs_list = (d.get("repairs") or [])[:100]
    batches: dict[str, list[dict[str, Any]]] = {}
    for rep in repairs_list:
        if rep.get("batch_id") and not rep.get("removed_at"):
            batches.setdefault(str(rep["batch_id"]), []).append(rep)
    batch_html = "".join(
        f'<div class="v-card"><div class="v-card-main">{_v(_it(lang, "rs.batch").format(n=len(reps)))} '
        f'{timestamp(reps[-1]["created_at"])}</div>'
        f'<div class="v-card-acts">{_act("undo_batch", batch)}</div></div>'
        for batch, reps in batches.items()
    )
    repair_cards = []
    for rep in repairs_list:
        rkind = str(rep.get("kind") or "")
        rkind_lbl = _it(lang, f"rk.{rkind}") if f"rk.{rkind}" in _inspector_keys() else rkind
        if rep.get("removed_at"):
            st_badge = f'<span class="v-tag">{_v(_it(lang, "rs.removed"))}</span>'
            acts = ""
        elif rep.get("via"):
            st_badge = f'<span class="v-tag k-warn">{_v(_it(lang, "rs.via").format(names=", ".join(rep["via"])))}</span>'
            acts = _undo(rep)
        elif rep.get("applied"):
            st_badge = f'<span class="v-tag k-owner">{_v(_it(lang, "rs.applied"))}</span>'
            acts = _undo(rep)
        else:
            st_badge = f'<span class="v-tag k-warn">{_v(_it(lang, "rs.unmatched"))}</span>'
            acts = _undo(rep)
        val_html = _repair_value(rep, lang)
        repair_cards.append(
            f'<div class="v-card">'
            f'<div class="v-card-top"><div class="v-card-badges">'
            f'<span class="v-tag">{_v(rkind_lbl)}</span>{st_badge}</div>'
            f'<span class="v-card-turn">{timestamp(rep.get("created_at"))}</span></div>'
            f'<div class="v-card-main">{_repair_target(rep)}'
            + (f' <span class="v-meta">{val_html}</span>' if val_html else "") + '</div>'
            + (f'<div class="v-card-acts">{acts}</div>' if acts else "") + "</div>"
        )
    repairs_body = (
        (f'<div class="v-exp-list">{batch_html}{"".join(repair_cards)}</div>' if (batch_html or repair_cards)
         else f'<p class="v-text">{_v(t(lang, "at_no_repairs"))}</p>')
        + f'<p class="v-note">{_v(_it(lang, "or.note"))}</p>'
    )

    body = (section("s-attention", lang, attn_body, len(queue))
            + section("s-conflicts", lang, conflicts_body, len(conflicts))
            + section("s-repairs", lang, repairs_body, len(repairs_list)))
    cap = " · ".join(str(x) for x in (conv.get("name"),
                                     f"t{conv['turns']}" if conv.get("turns") is not None else None) if x)
    foot = (f'<div class="v-foot"><a href="/views/c/{cid}/explore">{_v(t(lang, "at_open_explore"))}</a> · '
            f'<a href="/views/c/{cid}/memory">{_v(t(lang, "back_memory"))}</a> · '
            f'<a href="/inspector/c/{cid}">{_v(t(lang, "raw_inspector"))}</a></div>')
    return (f'<div class="v v-doc v-attention"><div class="v-head">'
            f'<h1 class="v-h1">{_v(t(lang, "attention"))}</h1>'
            f'<span class="v-cap">{_v(cap)}</span></div>{body}{foot}</div>')
