"""The panel's screens (PHASE-52), rendered by the sidecar: the hub first, then memory, a person, working and the chats.

They are HTML fragments the panel shows through its sanitizer (`inspector.ts` `safeFragment`), so they use only what it
keeps: `div`, `p`, `h1`, `h2`, `span`, `b`, `br`, `a`, `details`, `summary`; `class`, `title`, Inspector and view
links, and `data-act` with a fixed set of values for what the plugin itself does (settings, backup, the author's note).
No table, no inline script or style. The browser shows the same fragments as full pages (`full_page`).

The stylesheet is one string the panel injects once (`/v1/views/style`): every rule starts with `.nmos`, the panel's
root, so it cannot reach the host's page.
"""

from __future__ import annotations

from typing import Any

from . import tokens
from .facts import symmetric
from .inspector import _close, _v
from .summaries import content

STYLE = """
.nmos .v{font-size:var(--t-body,16px);line-height:1.65;color:var(--c-text);max-width:980px}
.nmos .v a{color:inherit;text-decoration:none}
.nmos .v-head{display:flex;flex-wrap:wrap;align-items:baseline;justify-content:space-between;gap:4px 12px;margin:0 0 14px}
.nmos .v-h1{font-size:var(--t-h1,20px);font-weight:600;margin:0;color:var(--c-text-strong)}
.nmos .v-cap{font-size:var(--t-caption,13px);color:var(--c-text-muted)}
.nmos .v-blocks{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
.nmos .v-block{display:flex;flex-direction:column;gap:2px;background:var(--c-raised);border-radius:var(--r-block,12px);padding:14px 16px;min-height:84px;cursor:pointer;border:1px solid transparent}
.nmos .v-block:hover{border-color:var(--c-line-hover)}
.nmos .v-wide{grid-column:1/-1;min-height:0;border-left:3px solid var(--c-ok);border-radius:0 var(--r-block,12px) var(--r-block,12px) 0}
.nmos .v-wide.warn{border-left-color:var(--c-warn)} .nmos .v-wide.err{border-left-color:var(--c-err)}
.nmos .v-wide.off,.nmos .v-wide.idle{border-left-color:var(--c-text-ghost)}
.nmos .v-bt{font-size:var(--t-body,16px);font-weight:600;color:var(--c-text-strong)}
.nmos .v-bs{font-size:var(--t-secondary,14px);color:var(--c-text-soft)}
.nmos .v-attn .v-bt{color:var(--c-warn)}
.nmos .v-now{display:none;font-size:var(--t-secondary,14px);color:var(--c-text-soft);margin-top:6px}
.nmos .v-chips{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 6px}
.nmos .v-chips a{font-size:var(--t-caption,13px);padding:3px 10px;border-radius:var(--r-control,6px);background:var(--c-raised);color:var(--c-text-soft)}
.nmos .v-sec{margin:22px 0 0}
.nmos .v-h2{font-size:var(--t-h2,17px);font-weight:600;margin:0 0 6px;color:var(--c-text-strong)}
.nmos .v-h2.v-small{font-size:var(--t-secondary,14px);margin-top:12px}
.nmos .v-n{font-size:var(--t-caption,13px);font-weight:400;color:var(--c-text-muted);margin-left:6px}
.nmos .v-line{padding:8px 0;border-top:1px solid var(--c-line)}
.nmos .v-line .rp{display:none} .nmos .v-line.open .rp{display:block;margin-top:6px}
.nmos .v-meta{font-size:var(--t-caption,13px);color:var(--c-text-muted)}
.nmos .v a.v-name{color:var(--c-link)}
.nmos .v-text{color:var(--c-text-soft);margin:0}
.nmos .v-note{font-size:var(--t-caption,13px);color:var(--c-text-muted);margin:6px 0 0}
.nmos .v-more>summary{cursor:pointer;list-style:none;font-size:var(--t-secondary,14px);color:var(--c-text-muted);padding:6px 0}
.nmos .v-more>summary::-webkit-details-marker{display:none}
.nmos .v-tl{position:relative;height:56px;margin:8px 4px 0}
.nmos .v-tl .tl-row{position:relative;height:56px}
.nmos .v-tl .v-axis{position:absolute;left:0;right:0;top:20px;border-top:1px solid var(--c-line-strong)}
.nmos .v-mark{position:absolute;top:16px;width:9px;height:9px;margin-left:-4px;border-radius:50%;background:var(--c-text-soft);cursor:pointer}
.nmos .v-mark.major{top:10px;width:20px;height:20px;margin-left:-10px;background:transparent;border:2px solid var(--c-text-strong)}
.nmos .v-mark.n2{top:14px;width:13px;height:13px;margin-left:-6px} .nmos .v-mark.n4{top:12px;width:17px;height:17px;margin-left:-8px}
.nmos .v-mark.major.n2,.nmos .v-mark.major.n4{top:8px;width:24px;height:24px;margin-left:-12px}
.nmos .v-mark.sel{border-color:var(--c-accent);background:var(--c-accent)}
.nmos .v-ends{display:flex;justify-content:space-between;font-size:var(--t-caption,13px);color:var(--c-text-muted)}
.nmos .v-warn{color:var(--c-warn)}
.nmos .v-filter input{width:100%;margin:0 0 8px}
.nmos .v-foot{margin:28px 0 0;padding-top:10px;border-top:1px solid var(--c-line);font-size:var(--t-caption,13px);color:var(--c-text-muted)}
.nmos .v-foot a{color:var(--c-text-soft)}
@media (min-width:700px){.nmos .v-blocks{grid-template-columns:repeat(3,minmax(0,1fr))}.nmos .v-big{grid-row:span 2}.nmos .v-now{display:block}}
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
    "stale": ("30턴 넘게 언급 없는 열린 일 {n}개는 여기 넣지 않았어요. 자세히에서 확인하거나 닫을 수 있어요.",
              "{n} open threads not mentioned for over 30 turns are left out here; check or close them in details."),
    "since": ("t{t}부터", "since t{t}"),
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
    "tl_hint": ("점을 누르면 그 턴의 변화가 보여요. 큰 원은 큰 사건이나 관계 변화예요.",
                "Tap a mark for its changes. A ring is a major event or a change of relationship."),
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
}

ACTS = ("notes", "settings", "backup", "retry")  # what the plugin does itself; its sanitizer keeps only these values


def t(lang: str, key: str, **kw: Any) -> str:
    text = T[key][lang == "en"]
    return text.format(**kw) if kw else text


# The browser page places the timeline's marks itself; in the panel, `placeMarks` does (it runs no page script).
PLACE = ("document.querySelectorAll('[data-l]').forEach(function(m){var l=Number(m.getAttribute('data-l'));"
         "if(l>=0&&l<=100)m.style.left=l+'%';});"
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


def hub(data: dict[str, Any], lang: str) -> str:
    """The panel's first screen (PHASE-52 D1): the working line, then a block per category. Without a chat NMOS knows,
    only what does not need one."""
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


def now_said(facts: list[dict[str, Any]], name: str) -> list[str]:
    """Where a character is and how, as the story says now (canon left out)."""
    key = name.casefold()
    said = [f.get("object") or f.get("value") for f in facts if f["predicate"] in NOW and not f.get("canon")
            and f.get("polarity") != "negative"
            and key in {str(f.get("subject") or "").casefold(),
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


def name_link(cid: str, entities: dict[str, str], name: str | None) -> str:
    """A character's name, leading to their sheet when NMOS knows them."""
    eid = entities.get(str(name or "").casefold())
    return f'<a class="v-name" href="/views/c/{cid}/person/{eid}">{_v(name)}</a>' if eid else _v(name)


def _named(f: dict[str, Any], side: str) -> str:
    e = f.get(f"{side}_entity") or {}
    return str(e.get("name") or f.get(side) or "")


def memory(d: dict[str, Any], lang: str) -> str:
    """A chat's memory as one document (PHASE-52 D2): now, open threads, people, so far, secrets, changed from the
    setting; at the foot, the way into everything else."""
    conv, ents = d["conv"], d.get("entities") or {}
    cid = conv["id"]
    nm = lambda name: name_link(cid, ents, name)  # noqa: E731
    keys = ["s-now", "s-open", "s-people", "s-sofar", "s-secrets", "s-changed"]
    chips = '<div class="v-chips">' + "".join(f'<a href="#{k}">{_v(t(lang, k))}</a>' for k in keys) + "</div>"
    nothing = f'<p class="v-text">{_v(t(lang, "none_yet"))}</p>'
    now = [line(nm(x["name"]), " · ".join(_v(s) for s in x["said"])) for x in d.get("now") or []]
    threads = d.get("threads") or []
    opened = [line(f"{nm(th['by'])}{' → ' + nm(th['to']) if th.get('to') else ''}: {_v(th['text'])}",
                   _v(f"{t(lang, th['kind']) if th['kind'] in T else th['kind']} · {t(lang, 'since', t=th.get('turn'))}"),
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
            + f' · <a href="{detail}">{_v(t(lang, "details"))}</a></div>')
    cap = " · ".join(str(x) for x in (conv.get("character"), f"t{conv['turns']}" if conv.get("turns") is not None else None) if x)
    return (f'<div class="v v-doc"><div class="v-head"><h1 class="v-h1">{_v(conv.get("name") or t(lang, "memory"))}</h1>'
            f'<span class="v-cap">{_v(cap)}</span></div>{chips}{body}{foot}</div>')



def _marks(d: dict[str, Any]) -> str:
    """The person's changes as circles on one lane (PHASE-52 D4), placed by `data-l` as today's timeline is, with the
    texts the panel's mark card shows."""
    from .timeline import circles
    first, last = d.get("first", 0) or 0, d.get("last", 0) or 0
    span = max(last - first, 1)
    marks = []
    for b in circles(d.get("marks") or [], first, last):
        mid = (b["lo"] + b["hi"]) / 2
        left = round(min(max((mid - first) / span * 100, 0), 100), 3)
        when = (f"t{b['lo']}" if b["lo"] == b["hi"] else f"t{b['lo']}–{b['hi']}") + (f" · ×{b['count']}" if b["count"] > 1 else "")
        text = " / ".join(b["texts"])[:400]
        size = "" if b["count"] < 2 else " n2" if b["count"] < 4 else " n4"  # a merged mark is larger; its count in its card
        marks.append(f'<span class="v-mark{" major" if b["major"] else ""}{size}" data-l="{left:g}" data-k="{_v(when)}" '
                     f'data-v="{_v(text)}" data-s="{_v(when)}"></span>')
    return ('<div class="tl v-tl"><div class="tl-row"><span class="v-axis"></span>' + "".join(marks) + "</div></div>")


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
        other = [n for i, n in p["names"].items() if i != e["id"]]
        bits = [f.get("value") for f in p["relationship"]]
        bits += [f'{t(lang, pred)} "{f.get("value")}"' if pred == "addresses" else f"{t(lang, pred)} {f.get('value')}"
                 for k, pred in (("role", "role_toward"), ("feels", "feels_toward"), ("speech", "addresses"))
                 for f in p[k] if (f.get("subject_entity") or {}).get("id") == e["id"]]
        rels.append(line(" · ".join([nm(o) for o in other] + [_v(b) for b in bits if b])))
    threads = [line(f"{_v(th['text'])}" + (f" → {nm(th['to'])}" if th.get("to") and th.get("by") == e.get("name") else ""),
                    _v(f"{t(lang, th['kind']) if th['kind'] in T else th['kind']} · {t(lang, 'since', t=th.get('turn'))}"),
                    _close(th)) for th in d.get("threads") or []]
    knows = [line(_v(content(s)), _v(t(lang, "knows") + f" · t{s.get('turn')}")) for s in d.get("knows") or []]
    knows += [line(_v(content(s)), _v(t(lang, "unaware", who=", ".join(s.get("holders") or [])) + f" · t{s.get('turn')}"))
              for s in d.get("kept") or []]
    time = (_marks(d) + f'<div class="v-ends"><span>t{d.get("first", 0)}</span>'
            f'<span>{_v(t(lang, "now_turn", t=d.get("last", 0)))}</span></div>'
            f'<p class="v-note">{_v(t(lang, "tl_hint"))}</p>') if d.get("marks") else nothing
    body = (section("s-now", lang, now) + section("s-rels", lang, more(rels, lang) or nothing, len(rels))
            + section("s-threads", lang, more(threads, lang) or nothing, len(threads))
            + section("s-knows", lang, more(knows, lang) or nothing, len(knows)) + section("s-time", lang, time))
    cap = t(lang, "aka", names=", ".join(aka)) if aka else ""
    return (f'<div class="v v-doc"><div class="v-head"><h1 class="v-h1">{_v(e.get("name"))}</h1>'
            f'<span class="v-cap">{_v(cap)}</span></div>{body}'
            f'<div class="v-foot"><a href="/views/c/{cid}/memory">{_v(t(lang, "back_memory"))}</a> · '
            f'<a href="/inspector/c/{cid}/e/{e["id"]}">{_v(t(lang, "details"))}</a></div></div>')



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
            items = [line(_v(x.get("text") or ""), _v(t(lang, "echoed")) if x.get("echoed") else "")
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
