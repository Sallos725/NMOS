"""Read-only inspector: plain server-rendered HTML, every value escaped. Korean by default, English
with `?lang=en`. `embed=True` returns only the body, without the language switch, for the plugin panel
(which cannot open a browser tab, ARCHITECTURE H15)."""

from __future__ import annotations

from collections.abc import Iterable
from html import escape
from typing import Any
from urllib.parse import quote

STYLE = """
:root{color-scheme:light dark;--bg:#fbfbfa;--fg:#1d1d1f;--muted:#6b6b70;--line:#e3e3e0;--chip:#efefec;--accent:#3b5bdb}
@media (prefers-color-scheme:dark){:root{--bg:#18181a;--fg:#ececec;--muted:#9a9aa0;--line:#2c2c30;--chip:#26262a;--accent:#8ea2ff}}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,-apple-system,"Noto Sans KR",sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px}
h1{font-size:20px;margin:0 0 4px} h2{font-size:15px;margin:28px 0 8px}
a{color:var(--accent);text-decoration:none} a:hover{text-decoration:underline}
.muted{color:var(--muted)} .mono{font-family:ui-monospace,monospace;font-size:12px}
.top{display:flex;justify-content:space-between;align-items:baseline;gap:12px}
.lang{font-size:13px;white-space:nowrap}
.ref{display:block;font-family:ui-monospace,monospace;font-size:11px;color:var(--muted)}
table{width:100%;border-collapse:collapse} th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-weight:600;color:var(--muted);font-size:12px}
.chip{display:inline-block;padding:0 6px;border-radius:4px;background:var(--chip);font-size:12px}
.wrap{overflow-x:auto}
"""

LANGS = ("ko", "en")

T: dict[str, tuple[str, str]] = {  # key: (ko, en)
    "title": ("NMOS 인스펙터", "NMOS inspector"),
    "intro": ("원장(source ledger) 읽기 전용 화면입니다. 백그라운드 작업:", "Read-only view of the source ledger. Background jobs:"),
    "empty": ("없음", "empty"),
    "none": ("없음", "none"),
    "extractor": ("사실 추출 세대", "Extractor generation"),
    "projection": ("임베딩 공간", "Embedding projection"),
    "partial": ("일부", "partial"),
    "h.conversation": ("대화", "Conversation"),
    "h.messages": ("메시지", "Messages"),
    "h.facts_cov": ("사실 커버리지", "Facts coverage"),
    "h.vector_cov": ("벡터 커버리지", "Vector coverage"),
    "h.commits": ("커밋", "Commits"),
    "h.branched": ("분기 원본", "Branched from"),
    "h.last_retrieval": ("마지막 검색", "Last retrieval"),
    "no_conversations": ("아직 동기화된 대화가 없습니다. PocketRisu에서 메시지를 보내 보세요.",
                         "No conversation synced yet. Send a message in PocketRisu."),
    "back": ("← 대화 목록", "← conversations"),
    "conversation": ("대화", "conversation"),
    "head": ("헤드", "head"),
    "branched_from": ("분기 원본", "branched from"),
    "at": ("메시지", "at"),
    "state": ("현재 상태", "Current state"),
    "h.key": ("키", "Key"), "h.value": ("값", "Value"), "h.as_of": ("기준 턴", "As of turn"), "h.rule": ("규칙", "Rule"),
    "no_state": ("상태창 규칙으로 읽은 값이 없습니다.", "No parser state."),
    "coverage": ("의미 처리 현황", "Semantic coverage"),
    "no_generation": ("활성화된 사실 추출·임베딩이 없습니다.", "No extractor or embedding generation is active."),
    "h.projection": ("종류", "Projection"), "h.generation": ("세대", "Generation"),
    "h.coverage": ("커버리지", "Coverage"), "h.detail": ("상세", "Detail"),
    "facts_row": ("사실 (추출)", "Facts (extraction)"), "vectors_row": ("벡터 (임베딩)", "Vectors (embedding)"),
    "pending": ("대기", "pending"), "failed": ("실패", "failed"), "not_queued": ("대기열 밖", "not queued"),
    "older_only": ("이전 세대에서 읽음", "served by an older generation"),
    "older_gen": ("이전 세대", "older generation"), "truncated": ("대상 잘림", "target truncated"),
    "partially_embedded": ("일부만 임베딩", "partially embedded"),
    "facts": ("현재 사실", "Current facts"),
    "negated": ("부정", "negated"), "legacy": ("이전 형식", "legacy"), "disputed": ("충돌", "disputed"),
    "conflicts": ("충돌 (이야기가 앞뒤가 맞지 않음)", "Conflicts (the story contradicts itself)"),
    "h.fact": ("현재 사실", "Current fact"), "h.against": ("맞지 않는 단언", "Contradicted by"),
    "items": ("아이템 이력", "Item timelines"), "h.item": ("아이템", "Item"), "h.timeline": ("이력 (오래된 순)", "Timeline (oldest first)"),
    "w.possesses": ("{s} 보유", "held by {s}"), "w.located_in": ("{o}에 있음", "at {o}"),
    "w.destroyed": ("소멸: {v}", "destroyed: {v}"), "w.not": ("아님", "not"),
    "o.current": ("현재", "current"), "o.superseded": ("대체됨", "superseded"), "o.ended": ("끝남", "ended"),
    "o.conflicting": ("충돌", "conflicting"),
    "claims": ("인물의 주장", "Claims by characters"), "h.by": ("말한 인물", "Said by"),
    "other": ("실제가 아닌 단언 (가정·꿈·미상)", "Not actual (hypothetical, dreamed, unknown)"),
    "h.modality": ("양태", "Modality"),
    "entities": ("엔티티", "Entities"), "h.type": ("종류", "Type"), "h.names": ("이름", "Names"),
    "h.mentions": ("언급", "Mentions"), "h.alias_turns": ("별칭이 나온 턴", "Alias stated in turn"),
    "ambiguous": ("모호한 이름 (연결 안 함)", "Ambiguous names (not linked)"), "h.candidates": ("후보", "Candidates"),
    "h.subject": ("주어", "Subject"), "h.predicate": ("술어", "Predicate"), "h.object": ("대상 / 값", "Object / value"),
    "h.knowledge": ("아는 범위", "Knowledge"), "h.turn": ("턴", "Turn"), "h.versions": ("버전", "Versions"),
    "h.position": ("#", "#"),
    "known_by": ("아는 인물", "known by"), "hidden_from": ("모르는 인물", "hidden from"),
    "k.public": ("공개", "public"), "k.limited": ("일부만 앎", "limited"), "k.unknown": ("미상", "unknown"),
    "retrievals": ("최근 검색", "Recent retrievals"),
    "h.when": ("시각", "When"), "h.query": ("질의", "Query"), "h.fresh": ("최신 여부", "Fresh"),
    "h.cand": ("후보", "Cand."), "h.sel": ("선택", "Sel."), "h.in_ctx": ("이미 문맥", "In-ctx"),
    "h.tokens": ("토큰", "Tokens"),
    "h.reason": ("사유", "Reason"), "h.changes": ("변경", "Changes"), "h.kinds": ("종류", "Kinds"),
    "members": ("현재 메시지 (최신순)", "Head membership (newest first)"),
    "h.role": ("역할", "Role"), "h.lifecycle": ("상태", "Lifecycle"), "h.disabled": ("비활성", "Disabled"),
    "h.processed": ("처리", "Processed"), "h.text": ("내용", "Text"),
    "not_normalized": ("정규화 안 됨", "not normalized"),
    "raw": ("원문", "raw"), "clean": ("정리", "clean"), "emb": ("임베딩", "emb"), "ext": ("추출", "ext"),
    "full": ("전체", "full"),
    "job.queued": ("대기", "queued"), "job.running": ("실행 중", "running"), "job.done": ("완료", "done"),
    "job.dead": ("실패", "dead"), "job.obsolete": ("폐기", "obsolete"),
}


def lang_of(value: str | None) -> str:
    return value if value in LANGS else "ko"


def query(token: str | None, lang: str) -> str:
    """Query string kept on every inspector link: auth token (if any) and the chosen language."""
    parts = ([f"token={quote(token)}"] if token else []) + ([] if lang == "ko" else [f"lang={lang}"])
    return ("?" + "&".join(parts)) if parts else ""


def _t(lang: str, key: str) -> str:
    return T[key][0 if lang == "ko" else 1]


def page(title: str, body: str, lang: str = "ko") -> str:
    return (f"<!doctype html><html lang=\"{lang}\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" "
            f"content=\"width=device-width,initial-scale=1\"><title>{escape(title)}</title><style>{STYLE}</style>"
            f"</head><body><main>{body}</main></body></html>")


def _v(value: Any) -> str:
    return escape("" if value is None else str(value))


def table(headers: list[str], rows: Iterable[list[str]]) -> str:
    head = "".join(f"<th>{escape(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return f"<div class=\"wrap\"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"


def label(conv: dict[str, Any]) -> str:
    """'<bot> · <chat>' as the host last named them; the host chat id when no name was reported."""
    names = [n for n in (conv.get("host_character_name"), conv.get("host_chat_name")) if n]
    return " · ".join(names) if names else str(conv["host_chat_ref"])


def _lang_switch(path: str, token: str | None, lang: str) -> str:
    links = []
    for code, name in (("ko", "한국어"), ("en", "English")):
        links.append(f"<b>{name}</b>" if code == lang else f"<a href=\"{path}{query(token, code)}\">{name}</a>")
    return "<span class=\"lang\">" + " | ".join(links) + "</span>"


def _generation(gen: dict[str, Any] | None, lang: str) -> str:
    if gen is None:
        return f"<span class=\"muted\">{_t(lang, 'none')}</span>"
    return (f"<span class=\"mono\" title=\"{_v(gen['key'])}\">{_v(gen['key'][:20])}</span> "
            f"{_v(gen['model'])} @ {_v(gen['endpoint'])}")


def _percent(stats: dict[str, Any] | None, done_key: str, lang: str) -> str:
    """Coverage of the active generation; partial coverage is never shown as complete (#8)."""
    if not stats or any(key not in stats for key in (done_key, "eligible", "percent", "complete")):
        return "<span class=\"muted\">—</span>"
    text = f"{stats[done_key]}/{stats['eligible']} ({stats['percent']}%)"
    return text if stats["complete"] else f"<span class=\"chip\">{_t(lang, 'partial')}</span> {text}"


def index(conversations: list[dict[str, Any]], token: str | None, jobs: dict[str, int] | None = None,
          gens: dict[str, dict[str, Any] | None] | None = None, extraction: dict | None = None,
          embeddings: dict | None = None, lang: str = "ko", embed: bool = False) -> str:
    extraction, embeddings, gens = extraction or {}, embeddings or {}, gens or {}
    q = query(token, lang)
    rows = [[f"<a href=\"/inspector/c/{c['id']}{q}\">{_v(label(c))}</a>"
             + (f"<span class=\"ref\">{_v(c['host_chat_ref'])}</span>" if label(c) != c["host_chat_ref"] else ""),
             _v(c["messages"]), _percent(extraction.get(c["id"]), "compiled", lang),
             _percent(embeddings.get(c["id"]), "embedded", lang), _v(c["commits"]),
             _v(c["branched_from_host_chat_ref"] or ""), _v(str(c["last_retrieval"] or "")[:19])]
            for c in conversations]
    queue = " · ".join(f"{_t(lang, f'job.{k}') if f'job.{k}' in T else escape(k)} {v}"
                       for k, v in sorted((jobs or {}).items())) or _t(lang, "empty")
    listing = (table([_t(lang, k) for k in ("h.conversation", "h.messages", "h.facts_cov", "h.vector_cov",
                                            "h.commits", "h.branched", "h.last_retrieval")], rows)
               if rows else f"<p class=\"muted\">{_t(lang, 'no_conversations')}</p>")
    switch = "" if embed else _lang_switch("/inspector", token, lang)
    body = (f"<div class=\"top\"><h1>{_t(lang, 'title')}</h1>{switch}</div>"
            f"<p class=\"muted\">{_t(lang, 'intro')} {queue}</p>"
            f"<p>{_t(lang, 'extractor')}: {_generation(gens.get('extraction'), lang)}<br>"
            f"{_t(lang, 'projection')}: {_generation(gens.get('embeddings'), lang)}</p>" + listing)
    return body if embed else page(_t(lang, "title"), body, lang)


def _knowledge(f: dict[str, Any], lang: str) -> str:
    scope = f.get("knowledge") or "unknown"
    detail = []
    if f.get("known_by"):
        detail.append(f"{_t(lang, 'known_by')}: " + ", ".join(f["known_by"]))
    if f.get("hidden_from"):
        detail.append(f"{_t(lang, 'hidden_from')}: " + ", ".join(f["hidden_from"]))
    chip = _t(lang, f"k.{scope}") if f"k.{scope}" in T else scope
    return f"<span class=\"chip\" title=\"{_v(scope)}\">{_v(chip)}</span> " + _v("; ".join(detail))


def _coverage_section(cov: dict[str, Any], lang: str) -> str:
    ex, emb = cov.get("extraction") or {}, cov.get("embeddings") or {}
    t = lambda k: _t(lang, k)
    rows = []
    if ex.get("generation"):
        rows.append([t("facts_row"), _generation(ex["generation"], lang), _percent(ex, "compiled", lang),
                     _v(f"{t('pending')} {ex.get('pending', 0)} · {t('failed')} {ex.get('failed', 0)} · "
                        f"{t('not_queued')} {ex.get('not_queued', 0)} · {t('older_only')} {ex.get('historical_only', 0)}"
                        f" · {t('truncated')} {ex.get('target_truncated', 0)}")])
    if emb.get("generation"):
        rows.append([t("vectors_row"), _generation(emb["generation"], lang), _percent(emb, "embedded", lang),
                     _v(f"{t('pending')} {emb.get('pending', 0)} · {t('failed')} {emb.get('failed', 0)} · "
                        f"{t('partially_embedded')} {emb.get('partial', 0)}")])
    if not rows:
        return f"<h2>{t('coverage')}</h2><p class=\"muted\">{t('no_generation')}</p>"
    return f"<h2>{t('coverage')}</h2>" + table([t("h.projection"), t("h.generation"), t("h.coverage"), t("h.detail")],
                                                rows)


def _processed(m: dict[str, Any], lang: str) -> str:
    """Was the whole revision semantically processed? Normalized chars embedded / seen by extraction."""
    clean = m.get("clean_chars")
    if clean is None:
        return f"<span class=\"muted\">{_t(lang, 'not_normalized')}</span>"
    parts = [f"{_t(lang, 'raw')} {m['length']:,} → {_t(lang, 'clean')} {clean:,}"]
    for key_label, key in (("emb", "embedded_chars"), ("ext", "extracted_chars")):
        if m.get(key) is not None:
            done = m[key] >= clean
            parts.append(f"{_t(lang, key_label)} {_t(lang, 'full') if done else f'{m[key]:,}/{clean:,}'}")
    partial = any(m.get(k) is not None and m[k] < clean for k in ("embedded_chars", "extracted_chars"))
    return (f"<span class=\"chip\">{_t(lang, 'partial')}</span> " if partial else "") + _v(" · ".join(parts))


def fact_line_text(a: dict[str, Any]) -> str:
    text = f"{a['subject']} {a['predicate'].replace('_', ' ')}" + (f" {a['object']}" if a.get("object") else "")
    return f"{text}: {a['value']}" if a.get("value") else text


def _step(h: dict[str, Any], lang: str) -> str:
    """One whereabouts history entry: turn, what it said, and what became of it (PHASE-6)."""
    said = _t(lang, f"w.{h['predicate']}").format(s=h["subject"], o=h.get("object") or "", v=h.get("value") or "")
    if h.get("polarity") == "negative":
        said = f"{_t(lang, 'w.not')} {said}" if lang == "en" else f"{said} {_t(lang, 'w.not')}"
    turn = h["turn"] if h.get("turn") is not None else h["position"]
    outcome = h.get("outcome", "superseded")
    return (f"<span class=\"muted\">{_v(turn)}</span> {_v(said)} "
            f"<span class=\"chip\" title=\"{_v(outcome)}\">{_v(_t(lang, f'o.{outcome}'))}</span>")


def detail(conv: dict[str, Any], state: list[dict[str, Any]], members: list[dict[str, Any]],
           commits: list[dict[str, Any]], traces: list[dict[str, Any]], facts: list[dict[str, Any]],
           token: str | None, coverage: dict[str, Any] | None = None, lang: str = "ko", embed: bool = False,
           claims: list[dict[str, Any]] | None = None, other: list[dict[str, Any]] | None = None,
           entities: list[dict[str, Any]] | None = None, ambiguous: list[dict[str, Any]] | None = None,
           conflicts: list[dict[str, Any]] | None = None, items: list[dict[str, Any]] | None = None) -> str:
    t = lambda k: _t(lang, k)
    q = query(token, lang)
    name, path = label(conv), f"/inspector/c/{conv['id']}"
    parts = [(f"<div class=\"top\"><p><a href=\"/inspector{q}\">{t('back')}</a></p>"
              f"{'' if embed else _lang_switch(path, token, lang)}</div>"),
             f"<h1>{_v(name)}</h1>",
             f"<p class=\"muted\"><span class=\"mono\">{_v(conv['host_chat_ref'])}</span><br>"
             f"{t('conversation')} {_v(conv['id'])} · {t('head')} {_v(conv['head_commit_id'])}"
             + (f" · {t('branched_from')} {_v(conv['branched_from_host_chat_ref'])} {t('at')} "
                f"{_v(conv['branched_from_message_ref'])}" if conv.get("branched_from_host_chat_ref") else "") + "</p>"]
    parts.append(f"<h2>{t('state')}</h2>" + (table([t("h.key"), t("h.value"), t("h.as_of"), t("h.rule")],
                 [[_v(s["key"]), _v(s["value"]), _v(s["position"]), _v(s["rule_id"])] for s in state])
                 if state else f"<p class=\"muted\">{t('no_state')}</p>"))
    parts.append(_coverage_section(coverage or {}, lang))
    if facts:
        # A fact whose turn the active generation has not compiled yet comes from an older one (ADR 0014).
        active = (((coverage or {}).get("extraction") or {}).get("generation") or {}).get("key")
        older = f" <span class=\"chip\">{t('older_gen')}</span>"
        parts.append(f"<h2>{t('facts')}</h2>" + table(
            [t(k) for k in ("h.subject", "h.predicate", "h.object", "h.knowledge", "h.turn", "h.versions")],
            [[_v(f["subject"]), f"<span class=\"chip\">{_v(f['predicate'])}</span>",
              _v(f.get("object") or f.get("value")), _knowledge(f, lang),
              _v(f["turn"] if f.get("turn") is not None else f["position"])
              + (older if active and f.get("generation") not in (None, active) else "")
              + (f" <span class=\"chip\">{t('negated')}</span>" if f.get("polarity") == "negative" else "")
              + (f" <span class=\"chip\">{t('disputed')}</span>" if f.get("disputed_by") else "")
              + (f" <span class=\"chip\">{t('legacy')}</span>" if f.get("source") is None else ""),
              _v(f.get("versions", 1))]
             for f in facts]))

    def turn_of(a: dict[str, Any]) -> str:
        return _v(a["turn"] if a.get("turn") is not None else a["position"])

    if conflicts:
        parts.append(f"<h2>{t('conflicts')}</h2>" + table(
            [t(k) for k in ("h.fact", "h.turn", "h.against", "h.turn")],
            [[_v(c["text"]), turn_of(c), _v(fact_line_text(c["against"])), turn_of(c["against"])]
             for c in conflicts[:100]]))
    if items:
        parts.append(f"<h2>{t('items')}</h2>" + table(
            [t("h.item"), t("h.timeline")],
            [[_v(i["item"]), " → ".join(_step(h, lang) for h in i["history"])] for i in items[:100]]))
    if entities:
        parts.append(f"<h2>{t('entities')}</h2>" + table(
            [t(k) for k in ("h.type", "h.names", "h.mentions", "h.alias_turns")],
            [[_v(e["type"]), _v(" · ".join(e["names"])), _v(e["mentions"]),
              _v(", ".join(str(a["turn"]) for a in e["aliases"]))] for e in entities[:200]]))
    if ambiguous:
        parts.append(f"<h2>{t('ambiguous')}</h2>" + table(
            [t(k) for k in ("h.type", "h.names", "h.candidates")],
            [[_v(a["type"]), _v(a["name"]), _v(" · ".join(a["candidates"]))] for a in ambiguous]))
    if claims:
        parts.append(f"<h2>{t('claims')}</h2>" + table(
            [t(k) for k in ("h.by", "h.subject", "h.predicate", "h.object", "h.turn")],
            [[_v(c.get("asserted_by")), _v(c["subject"]), f"<span class=\"chip\">{_v(c['predicate'])}</span>",
              _v(c.get("object") or c.get("value")), turn_of(c)] for c in claims[:100]]))
    if other:
        parts.append(f"<h2>{t('other')}</h2>" + table(
            [t(k) for k in ("h.modality", "h.subject", "h.predicate", "h.object", "h.turn")],
            [[_v(a["modality"]), _v(a["subject"]), f"<span class=\"chip\">{_v(a['predicate'])}</span>",
              _v(a.get("object") or a.get("value")), turn_of(a)] for a in other[:100]]))
    parts.append(f"<h2>{t('retrievals')}</h2>" + table(
        [t(k) for k in ("h.when", "h.query", "h.fresh", "h.cand", "h.sel", "h.in_ctx", "h.tokens")] + ["ms"],
        [[_v(str(r["created_at"])[:19]), _v(r["query"]), _v(r["freshness"]), _v(r["candidates"]), _v(r["selected"]),
          _v(r["excluded"]), _v(r["token_estimate"]), _v((r["latency_ms"] or {}).get("sidecar_total"))] for r in traces]))
    parts.append(f"<h2>{t('h.commits')}</h2>" + table(["#", t("h.reason"), t("h.changes"), t("h.kinds"), t("h.when")],
                 [[_v(c["seq"]), f"<span class=\"chip\">{_v(c['reason'])}</span>", _v(c["changes"]), _v(c["kinds"]),
                   _v(str(c["created_at"])[:19])] for c in commits]))
    parts.append(f"<h2>{t('members')}</h2>" + table(
        [t(k) for k in ("h.position", "h.turn", "h.role", "h.lifecycle", "h.disabled", "h.processed", "h.text")],
        [[_v(m["position"]), _v(m.get("turn")), _v(m["role"]), f"<span class=\"chip\">{_v(m['lifecycle'])}</span>",
          _v(m["disabled"] or ""), _processed(m, lang), _v(m["preview"]) + ("…" if m["length"] > 240 else "")]
         for m in members]))
    return "".join(parts) if embed else page(f"NMOS · {name}", "".join(parts), lang)
