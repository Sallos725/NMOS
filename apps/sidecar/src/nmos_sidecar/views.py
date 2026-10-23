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
from .inspector import _v

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
}

ACTS = ("notes", "settings", "backup")  # what the plugin does itself; its sanitizer keeps only these values


def t(lang: str, key: str, **kw: Any) -> str:
    text = T[key][lang == "en"]
    return text.format(**kw) if kw else text


def full_page(title: str, body: str, lang: str = "ko") -> str:
    """A screen as a page of its own, for the browser: the panel's root class, so the same stylesheet applies."""
    root = ".nmos{" + tokens.css_vars() + ";background:var(--c-bg);color:var(--c-text);min-height:100vh;padding:20px 16px;" \
        "font-family:system-ui,-apple-system,\"Apple SD Gothic Neo\",\"Malgun Gothic\",\"Noto Sans KR\",sans-serif}"
    return (f"<!doctype html><html lang=\"{lang}\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
            f"<title>{_v(title)}</title><style>body{{margin:0}}{root}{STYLE}</style></head>"
            f"<body><div class=\"nmos\">{body}</div></body></html>")


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
        blocks.append(_block(title, sub, href=detail, cls=f"v-wide {state}"))
        m = data.get("memory") or {}
        now = "".join(f'<span class="v-now">{_v(x)}</span>' for x in (m.get("now") or [])[:2])
        blocks.append(_block(t(lang, "memory"), t(lang, "memory_sub", c=m.get("cast", 0), o=m.get("open", 0),
                                                  g=m.get("changed", 0)), href=detail, cls="v-big", extra=now))
        if data.get("attention"):
            blocks.append(_block(t(lang, "attention"), str(data["attention"]), href=f"{detail}#s-attention",
                                 cls="v-attn"))
        blocks.append(_block(t(lang, "notes"), t(lang, "notes_sub"), act="notes"))
        blocks.append(_block(t(lang, "usage"), t(lang, "usage_sub", n=(data.get("usage") or {}).get("calls", 0)),
                             href=f"{detail}#s-usage"))
    else:
        blocks.append(_block(title, sub, href="/inspector", cls=f"v-wide {state}"))
    blocks.append(_block(t(lang, "settings"), t(lang, "settings_sub"), act="settings"))
    blocks.append(_block(t(lang, "backup"), t(lang, "backup_sub"), act="backup"))
    blocks.append(_block(t(lang, "chats"), t(lang, "chats_sub", n=data.get("chats", 0)), href="/inspector"))
    cap = " · ".join(str(x) for x in ((conv or {}).get("name"), (conv or {}).get("character"),
                                     f"t{conv['turns']}" if conv and conv.get("turns") is not None else None) if x)
    return (f'<div class="v v-hub"><div class="v-head"><h1 class="v-h1">NMOS</h1>'
            f'<span class="v-cap">{_v(cap)}</span></div><div class="v-blocks">{"".join(blocks)}</div></div>')


NOW = ("located_in", "has_status")


def now_lines(facts: list[dict[str, Any]], cast: list[str]) -> list[str]:
    """Where each character of the scene is and how (the newest request's cast, in its order): "Hana · the lighthouse ·
    tired". Characters with neither are left out."""
    out = []
    for name in cast:
        key = name.casefold()
        said = [f.get("object") or f.get("value") for f in facts if f["predicate"] in NOW and not f.get("canon")
                and f.get("polarity") != "negative"
                and key in {str(f.get("subject") or "").casefold(),
                            str((f.get("subject_entity") or {}).get("name") or "").casefold()}]
        said = [s for s in said if s]
        if said:
            out.append(" · ".join([name, *dict.fromkeys(said)]))
    return out
