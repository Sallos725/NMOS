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
from .facts import symmetric
from .inspector import _act, _close, _v
from .summaries import content

# The hub's blocks are flex rows that always end flush: each block grows to fill what its row leaves (PHASE-52 D1).
STYLE = """
.nmos .v{font-size:var(--t-body,16px);line-height:1.65;color:var(--c-text);max-width:980px}
.nmos .v a{color:inherit;text-decoration:none}
.nmos .v-head{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:4px 12px;margin:0 0 14px}
.nmos .v-h1{font-size:var(--t-h1,20px);font-weight:600;margin:0;color:var(--c-text-strong)}
.nmos .v-cap{font-size:var(--t-caption,13px);color:var(--c-text-muted)}
.nmos .v-blocks{display:flex;flex-wrap:wrap;gap:10px}
.nmos .v-block{display:flex;flex-direction:column;gap:2px;background:var(--c-raised);border-radius:var(--r-block,12px);padding:14px 16px;min-height:84px;cursor:pointer;border:1px solid transparent;flex:1 1 140px;min-width:0;box-sizing:border-box}
.nmos .v-block:hover{border-color:var(--c-line-hover)}
.nmos .v-wide,.nmos .v-big{flex-basis:100%}
.nmos .v-wide{min-height:0;border-left:3px solid var(--c-ok);border-radius:0 var(--r-block,12px) var(--r-block,12px) 0}
.nmos .v-wide.warn{border-left-color:var(--c-warn)} .nmos .v-wide.err{border-left-color:var(--c-err)}
.nmos .v-wide.off,.nmos .v-wide.idle{border-left-color:var(--c-text-ghost)}
.nmos .v-bt{font-size:var(--t-body,16px);font-weight:600;color:var(--c-text-strong)}
.nmos .v-bs{font-size:var(--t-secondary,14px);color:var(--c-text-soft)}
.nmos .v-attn .v-bt{color:var(--c-warn)}
.nmos .v-now{display:block;font-size:var(--t-secondary,14px);color:var(--c-text-soft);margin-top:6px}
.nmos .v-chips{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 6px}
.nmos .v-chips a{font-size:var(--t-caption,13px);padding:3px 10px;border-radius:var(--r-control,6px);background:var(--c-raised);color:var(--c-text-soft)}
.nmos .v-sec{margin:22px 0 0}
.nmos .v-h2{font-size:var(--t-h2,17px);font-weight:600;margin:0 0 6px;color:var(--c-text-strong)}
.nmos .v-h2.v-small{font-size:var(--t-secondary,14px);margin-top:12px}
.nmos .v-n{font-size:var(--t-caption,13px);font-weight:400;color:var(--c-text-muted);margin-left:6px}
.nmos .v-line{padding:8px 0;border-top:1px solid var(--c-line)}
.nmos .v-line .rp{display:none} .nmos .v-line.open .rp{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:8px 0 0}
.nmos .v-line .rp .rp-ask{font-size:var(--t-secondary,14px);color:var(--c-text-muted)}
.nmos .v-meta{font-size:var(--t-caption,13px);color:var(--c-text-muted)}
.nmos .v a.v-name{color:var(--c-link)}
.nmos .v-text{color:var(--c-text-soft);margin:0}
.nmos .v-note{font-size:var(--t-caption,13px);color:var(--c-text-muted);margin:6px 0 0}
.nmos .v-more>summary{cursor:pointer;list-style:none;font-size:var(--t-secondary,14px);color:var(--c-text-muted);padding:6px 0}
.nmos .v-more>summary::-webkit-details-marker{display:none}
.nmos .v-mini{position:relative;height:20px;margin:10px 7px 2px}
.nmos .v-mini .v-axis{position:absolute;left:0;right:0;top:9px;border-top:2px solid var(--c-line-strong)}
.nmos .v-pin{position:absolute;top:7px;width:6px;height:6px;margin-left:-3px;border-radius:50%;background:var(--c-text-faint)}
.nmos .v-pin.major{top:3px;width:14px;height:14px;margin-left:-7px;box-sizing:border-box;border:2px solid var(--c-text-strong);background:var(--c-bg)}
.nmos .v-ev{display:flex;gap:10px;align-items:flex-start;padding:8px 0;border-top:1px solid var(--c-line)}
.nmos .v-ev .v-t{flex:none;min-width:52px;font-size:var(--t-caption,13px);color:var(--c-text-muted);padding-top:3px}
.nmos .v-ev .v-d{flex:none;width:8px;height:8px;margin:9px 2px 0;border-radius:50%;background:var(--c-text-faint)}
.nmos .v-ev.major .v-d{width:12px;height:12px;margin:7px 0 0;box-sizing:border-box;border:2px solid var(--c-text-strong);background:transparent}
.nmos .v-ev .v-x{color:var(--c-text-soft);min-width:0} .nmos .v-ev.major .v-x{color:var(--c-text-strong)}
.nmos .v-ends{display:flex;justify-content:space-between;font-size:var(--t-caption,13px);color:var(--c-text-muted)}
.nmos .v-warn{color:var(--c-warn)}
.nmos .v-filter input{width:100%;margin:0 0 8px}
.nmos .v-foot{margin:28px 0 0;padding-top:10px;border-top:1px solid var(--c-line);font-size:var(--t-caption,13px);color:var(--c-text-muted)}
.nmos .v-foot a{color:var(--c-text-soft)}
.nmos .v-stack{position:relative;height:8px;margin:6px 0 2px;border-radius:4px;overflow:hidden;background:var(--c-raised)}
.nmos .v-seg{position:absolute;top:0;bottom:0}
.nmos .v-seg.setting{background:var(--c-text-ghost)} .nmos .v-seg.over{background:var(--c-warn)}
.nmos .v-seg.story{background:var(--c-link)} .nmos .v-seg.owner{background:var(--c-ok)}
.nmos .g-m{color:var(--c-text-muted)} .nmos .g-m.story{color:var(--c-link)}
.nmos .g-m.changed,.nmos .g-m.over{color:var(--c-warn)} .nmos .g-m.owner{color:var(--c-ok)}
.nmos .v-graph{margin:8px 0 4px}
.nmos .v-graph svg{display:block;margin:0 auto;max-width:100%;height:auto;max-height:90vh}
.nmos .v-graph.one .g-t{font-size:20px}
.nmos .g-e{stroke:var(--c-text-ghost);stroke-width:1.5;vector-effect:non-scaling-stroke} .nmos .g-e.story{stroke:var(--c-link)}
.nmos .g-e.changed{stroke:var(--c-warn)} .nmos .g-e.split{stroke:var(--c-text-muted);stroke-dasharray:5 4}
.nmos .g-n{fill:var(--c-text-faint)} .nmos .g-n.lead{fill:var(--c-text-strong)}
.nmos .g-n.group,.nmos .g-n.place{fill:var(--c-bg);stroke:var(--c-text-muted);stroke-width:2}
.nmos .g-t{fill:var(--c-text-soft);font-size:16px} .nmos .g-t.lead{fill:var(--c-text-strong);font-weight:600}
.nmos svg.g-panel{display:block;width:100%;height:min(62vh,480px);touch-action:none;user-select:none;-webkit-user-select:none;background:var(--c-sunken);border-radius:var(--r-block,12px)}
.nmos svg.g-panel .g-e.on{stroke-width:2.5}
.nmos svg.g-panel.sel .g-e:not(.on){opacity:.12} .nmos svg.g-panel.sel .g-node:not(.on){opacity:.3}
.nmos .v-graph-btns{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:6px 0 0}
@media (min-width:700px){.nmos .v-block:not(.v-wide):not(.v-big){flex-basis:240px}}
@media (max-width:699px){.nmos .v-graph.whole{display:none}}
"""

T: dict[str, tuple[str, str]] = {
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
         "r.textContent.toLowerCase().indexOf(q)<0?'none':'';});});});")


def full_page(title: str, body: str, lang: str = "ko") -> str:
    """A screen as a page of its own, for the browser: the panel's root class, so the same stylesheet applies."""
    root = ".nmos{" + tokens.css_vars() + ";background:var(--c-bg);color:var(--c-text);min-height:100vh;padding:20px 16px;" \
        "font-family:system-ui,-apple-system,\"Apple SD Gothic Neo\",\"Malgun Gothic\",\"Noto Sans KR\",sans-serif}"
    return (f"<!doctype html><html lang=\"{lang}\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            f"<title>{_v(title)}</title><style>body{{margin:0}}{root}{STYLE}</style></head>"
            f"<body><div class=\"nmos\">{body}</div><script>{PLACE}</script></body></html>")


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


def hub(data: dict[str, Any], lang: str, map_: bool = False) -> str:
    """The panel's first screen (PHASE-52 D1): the working line, then a block per category. Without a chat NMOS knows,
    only what does not need one. `map_`: the reader can open the memory map (PHASE-55), a block after memory's."""
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
        now = "".join(f'<span class="v-now">{_v(x)}</span>' for x in (m.get("now") or [])[:2])
        blocks.append(_block(t(lang, "memory"), t(lang, "memory_sub", c=m.get("cast", 0), o=m.get("open", 0),
                                                  g=m.get("changed", 0)), href=f"/views/c/{cid}/memory", cls="v-big",
                             extra=now))
        if map_:
            blocks.append(_block(t(lang, "map"), t(lang, "map_sub"), href=f"/views/c/{cid}/map"))
        if data.get("attention"):
            blocks.append(_block(t(lang, "attention"), str(data["attention"]), href=f"{detail}#s-attention",
                                 cls="v-attn"))
        blocks.append(_block(t(lang, "notes"), t(lang, "notes_sub"), act="notes"))
        blocks.append(_block(t(lang, "usage"), t(lang, "usage_sub", n=(data.get("usage") or {}).get("calls", 0)),
                             href=f"/views/c/{cid}/working#s-usage"))
    else:
        blocks.append(_block(title, sub, href="/views/chats", cls=f"v-wide {state}"))
    blocks.append(_block(t(lang, "settings"), t(lang, "settings_sub"), act="settings"))
    blocks.append(_block(t(lang, "backup"), t(lang, "backup_sub"), act="backup"))
    blocks.append(_block(t(lang, "chats"), t(lang, "chats_sub", n=data.get("chats", 0)), href="/views/chats"))
    cap = " · ".join(str(x) for x in ((conv or {}).get("name"), (conv or {}).get("character"),
                                     f"t{conv['turns']}" if conv and conv.get("turns") is not None else None) if x)
    return (f'<div class="v v-hub"><div class="v-head"><h1 class="v-h1">NMOS</h1>'
            f'<span class="v-cap">{_v(cap)}</span></div><div class="v-blocks">{"".join(blocks)}</div></div>')


NOW = ("located_in", "has_status")


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
    """A thread's kind, how long it is meant to last when known (PHASE-51), and since when."""
    kind = t(lang, th["kind"]) if th["kind"] in T else th["kind"]
    horizon = t(lang, f"hz.{th['horizon']}") if th.get("horizon") in ("scene", "arc", "lasting") else None
    return " · ".join(x for x in (kind, horizon, t(lang, "since", t=th.get("turn"))) if x)


def name_link(cid: str, entities: dict[str, str], name: str | None) -> str:
    """A character's name, leading to their sheet when NMOS knows them."""
    eid = entities.get(str(name or "").casefold())
    return f'<a class="v-name" href="/views/c/{cid}/person/{eid}">{_v(name)}</a>' if eid else _v(name)


def _named(f: dict[str, Any], side: str) -> str:
    e = f.get(f"{side}_entity") or {}
    return str(e.get("name") or f.get(side) or "")


def memory(d: dict[str, Any], lang: str, map_: bool = False) -> str:
    """A chat's memory as one document (PHASE-52 D2): now, open threads, people, so far, secrets, changed from the
    setting; at the foot, the way into everything else (with `map_`, the memory map, PHASE-55)."""
    conv, ents = d["conv"], d.get("entities") or {}
    cid = conv["id"]
    nm = lambda name: name_link(cid, ents, name)  # noqa: E731
    keys = ["s-now", "s-open", "s-people", "s-sofar", "s-secrets", "s-changed"]
    chips = '<div class="v-chips">' + "".join(f'<a href="#{k}">{_v(t(lang, k))}</a>' for k in keys) + "</div>"
    nothing = f'<p class="v-text">{_v(t(lang, "none_yet"))}</p>'
    now = [line(nm(x["name"]), " · ".join(_v(s) for s in x["said"])) for x in d.get("now") or []]
    threads = d.get("threads") or []
    opened = [line(f"{nm(th['by'])}{' → ' + nm(th['to']) if th.get('to') else ''}: {_v(th['text'])}",
                   _v(thread_meta(th, lang)),
                   _close(th)) for th in threads]
    stale = f'<p class="v-note">{_v(t(lang, "stale", n=d["stale"]))}</p>' if d.get("stale") else ""
    people = []
    for p in d.get("pairs") or []:
        names = sorted(p["names"].values())
        rel = [f.get("value") for f in p["relationship"]]
        head = " ↔ ".join(nm(n) for n in names) + (f" · {_v(', '.join(str(r) for r in rel if r))}" if rel else "")
        bits = []
        for k, pred in (("role", "role_toward"), ("feels", "feels_toward"), ("speech", "addresses")):
            for f in p[k]:
                value = f'"{f.get("value")}"' if pred == "addresses" else f.get("value")
                bits.append(f"{_named(f, 'subject')}→{_named(f, 'object')} {t(lang, pred)} {value}")
        if len(p["relationship"]) > 1 or any(not symmetric(f.get("value")) for f in p["relationship"]):
            bits = [f"{_named(f, 'subject')}→{_named(f, 'object')} {t(lang, 'relationship')} {f.get('value')}"
                    for f in p["relationship"]] + bits
        people.append(line(head, _v(" · ".join(bits))))
    story, scenes = d.get("story"), d.get("scenes") or []
    sofar = (f'<p class="v-text">{_v(story["text"])}</p><div class="v-meta">{_v(t(lang, "story"))} · '
             f't{story["first_turn"]}–{story["last_turn"]}</div>') if story else ""
    if scenes:
        sofar += (f'<details class="v-more"><summary>{_v(t(lang, "scenes", n=len(scenes)))}</summary>'
                  + "".join(line(_v(s["text"]), f"t{s['first_turn']}–{s['last_turn']}") for s in scenes) + "</details>")
    secrets = [line(_v(content(s)), _v(" · ".join(x for x in (
        t(lang, "by", who=", ".join(s.get("holders") or [])) if s.get("holders") else "",
        t(lang, "kept", who=", ".join(s.get("open") or [])), f"t{s.get('turn')}") if x)))
        for s in d.get("secrets") or [] if s.get("open")]
    changed = [line(f"{nm(_named(c['fact'], 'subject'))} {_v(t(lang, c['fact']['predicate']) if c['fact']['predicate'] in T else c['fact']['predicate'])}",
                    _v(t(lang, "was", old=c["old"], new=c["new"]) + f" · t{c['fact'].get('turn')}"))
               for c in d.get("changes") or []]
    body = (section("s-now", lang, more(now, lang, 6) or nothing)
            + section("s-open", lang, (more(opened, lang) or nothing) + stale, len(threads))
            + section("s-people", lang, more(people, lang) or nothing, len(people))
            + section("s-sofar", lang, sofar or nothing)
            + section("s-secrets", lang, more(secrets, lang) or nothing, len(secrets))
            + section("s-changed", lang, more(changed, lang) or nothing, len(changed)))
    detail = f"/inspector/c/{cid}"
    foot = (f'<div class="v-foot"><a href="{detail}#s-facts">{_v(t(lang, "facts", n=d.get("facts", 0)))}</a>'
            + (f' · <a href="{detail}#s-attention">{_v(t(lang, "attention"))} {d["attention"]}</a>' if d.get("attention") else "")
            + (f' · <a href="/views/c/{cid}/map">{_v(t(lang, "map"))}</a>' if map_ else "")
            + f' · <a href="{detail}">{_v(t(lang, "details"))}</a></div>')
    cap = " · ".join(str(x) for x in (conv.get("character"), f"t{conv['turns']}" if conv.get("turns") is not None else None) if x)
    return (f'<div class="v v-doc"><div class="v-head"><h1 class="v-h1">{_v(conv.get("name") or t(lang, "memory"))}</h1>'
            f'<span class="v-cap">{_v(cap)}</span></div>{chips}{body}{foot}</div>')



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
    return (f'<div class="v-ev{" major" if major else ""}"><span class="v-t">t{m[0]}</span><span class="v-d"></span>'
            f'<span class="v-x">{_v(text)}</span></div>')


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


def person(d: dict[str, Any], lang: str) -> str:
    """A person's sheet (PHASE-52 D3): now, relationships, promises and goals, what they know and do not, the timeline."""
    conv, e, ents = d["conv"], d["entity"], d.get("entities") or {}
    cid = conv["id"]
    nm = lambda name: name_link(cid, ents, name)  # noqa: E731
    nothing = f'<p class="v-text">{_v(t(lang, "none_yet"))}</p>'
    aka = [n for n in e.get("names") or [] if n != e.get("name")]
    now = f'<p class="v-text">{" · ".join(_v(x) for x in d.get("now") or [])}</p>' if d.get("now") else nothing
    rels = []
    for p in d.get("pairs") or []:
        other = [n for i, n in p["names"].items() if str(i) != str(e["id"])]
        rel = [str(f.get("value")) for f in p["relationship"] if f.get("value")]
        bits = []
        for k, pred in (("role", "role_toward"), ("feels", "feels_toward"), ("speech", "addresses")):
            for f in p[k]:
                value = f'"{f.get("value")}"' if pred == "addresses" else f.get("value")
                bits.append(f"{_named(f, 'subject')}→{_named(f, 'object')} {t(lang, pred)} {value}")
        rels.append(line(" · ".join([nm(o) for o in other] + [_v(r) for r in rel]), _v(" · ".join(bits))))
    threads = [line(f"{_v(th['text'])}" + (f" → {nm(th['to'])}" if th.get("to") and th.get("by") == e.get("name") else ""),
                    _v(thread_meta(th, lang)),
                    _close(th)) for th in d.get("threads") or []]
    knows = [line(_v(content(s)), _v(t(lang, "knows") + f" · t{s.get('turn')}")) for s in d.get("knows") or []]
    knows += [line(_v(content(s)), _v(t(lang, "unaware", who=", ".join(s.get("holders") or [])) + f" · t{s.get('turn')}"))
              for s in d.get("kept") or []]
    time = (_timeline(d, lang) + f'<p class="v-note">{_v(t(lang, "tl_hint"))}</p>') if d.get("marks") else nothing
    body = (section("s-now", lang, now) + section("s-rels", lang, more(rels, lang) or nothing, len(rels))
            + section("s-threads", lang, more(threads, lang) or nothing, len(threads))
            + section("s-knows", lang, more(knows, lang) or nothing, len(knows)) + section("s-time", lang, time))
    cap = t(lang, "aka", names=", ".join(aka)) if aka else ""
    if not e.get("persona"):  # PHASE-47 S6: the button, behind a tap like every repair here
        body += (f'<p class="v-note">{_v(t(lang, "is_not_char"))}</p>' if e.get("excluded")
                 else line(_v(t(lang, "not_char")), "", _act("entity_exclude", e["id"], e.get("name"))))
    return (f'<div class="v v-doc"><div class="v-head"><h1 class="v-h1">{_v(e.get("name"))}</h1>'
            f'<span class="v-cap">{_v(cap)}</span></div>{body}'
            f'<div class="v-foot"><a href="/views/c/{cid}/memory">{_v(t(lang, "back_memory"))}</a> · '
            f'<a href="/inspector/c/{cid}/e/{e["id"]}">{_v(t(lang, "details"))}</a></div></div>')



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
            items = [line(_v(plain(x.get("text") or "", lang)), _v(t(lang, "echoed")) if x.get("echoed") else "")
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
        failed += int(x.get("failed") or 0)
        main = f"{t(lang, 'w_' + key)} · " + (f"{x.get(done, 0)}/{x.get(due, 0)}" if done else t(lang, "w_made", n=x.get("produced", 0)))
        rows.append(line(_v(main), _v(t(lang, "w_counts", f=x.get("failed", 0), p=x.get("pending", 0)))))
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
        if f["predicate"] == "relationship" and symmetric(f.get("value")):
            bits.append(f"{word('relationship', lang)} {value}")
        else:
            bits.append(f"{_named(f, 'subject')}→{_named(f, 'object')} {word(f['predicate'], lang)} {value}")
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
        keys = ["s-src", "s-ties", "s-events", "s-depth"]
        chips = '<div class="v-chips">' + "".join(f'<a href="#{k}">{_v(t(lang, k))}</a>' for k in keys) + "</div>"
        head = t(lang, "map")
        body = (chips + section("s-src", lang, _sources(m["sources"], lang)) + ties
                + section("s-events", lang, _events(cid, m["events"], m["last"], ents, lang), len(m["events"]))
                + section("s-depth", lang, _depth(m["depth"], lang)))
        foot = (f'<div class="v-foot"><a href="/views/c/{cid}/memory">{_v(t(lang, "back_memory"))}</a> · '
                f'<a href="/inspector/c/{cid}">{_v(t(lang, "details"))}</a></div>')
    cap = " · ".join(str(x) for x in (conv.get("name"), f"t{conv['turns']}" if conv.get("turns") is not None else None)
                     if x)
    return (f'<div class="v v-doc v-map"><div class="v-head"><h1 class="v-h1">{_v(head)}</h1>'
            f'<span class="v-cap">{_v(cap)}</span></div>{body}{foot}</div>')
