"""Read-only inspector: plain server-rendered HTML, every value escaped. Korean by default, English
with `?lang=en`. `embed=True` returns only the body, without the language switch, for the plugin panel
(which cannot open a browser tab, ARCHITECTURE H15)."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
from html import escape
from typing import Any
from urllib.parse import quote

from .entities import norm
from .facts import participant_entities

STYLE = """
:root{color-scheme:light dark;--bg:#fbfbfa;--fg:#1d1d1f;--muted:#6b6b70;--line:#e3e3e0;--chip:#efefec;--accent:#3b5bdb}
@media (prefers-color-scheme:dark){:root{--bg:#18181a;--fg:#ececec;--muted:#9a9aa0;--line:#2c2c30;--chip:#26262a;--accent:#8ea2ff}}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,-apple-system,"Noto Sans KR",sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px}
h1{font-size:20px;margin:0 0 4px} h2{font-size:15px;margin:28px 0 8px}
a{color:var(--accent);text-decoration:none} a:hover{text-decoration:underline}
.muted{color:var(--muted)} .mono{font-family:ui-monospace,monospace;font-size:12px}
pre.mono{white-space:pre-wrap;background:var(--chip);padding:8px 10px;border-radius:6px;margin:4px 0 0}
.top{display:flex;justify-content:space-between;align-items:baseline;gap:12px}
.lang{font-size:13px;white-space:nowrap}
.ref{display:block;font-family:ui-monospace,monospace;font-size:11px;color:var(--muted)}
table{width:100%;border-collapse:collapse} th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-weight:600;color:var(--muted);font-size:12px}
.chip{display:inline-block;padding:0 6px;border-radius:4px;background:var(--chip);font-size:12px}
.wrap{overflow-x:auto}
.warn{color:#e8590c} .n{color:var(--muted);font-weight:400;font-size:12px}
.toc,.who{font-size:13px;line-height:1.9;margin:8px 0}
details>summary{cursor:pointer;list-style:none} details>summary::-webkit-details-marker{display:none}
details>summary h2{display:inline-block} details>summary h2::before{content:"\\25B8  ";color:var(--muted)}
details[open]>summary h2::before{content:"\\25BE  "}
details.meta{margin:4px 0 0;font-size:12px} details.meta p{margin:4px 0}
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
    "no_state_hint": ("예: 봇 응답이 아래처럼 쓰여 있으면 규칙이 값을 읽습니다 (규칙 예시는 config/parsers.example.json 참고).",
                      "Example: rules read values when the bot's reply looks like this (see config/parsers.example.json for matching rules)."),
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
    "threads": ("약속", "Promises"), "h.to": ("받는 인물", "To"), "h.promise": ("약속", "Promise"),
    "h.status": ("상태", "Status"), "h.closed": ("닫은 단언", "Closed by"), "h.restated": ("다시 말한 턴", "Restated in turn"),
    "unmatched": ("어느 약속에도 맞지 않은 이행·파기", "Kept or broken, matching no open promise"),
    "salience": ("중요도", "salience"),
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
    "h.owner_links": ("소유자가 합친 이름", "Joined by the owner"),
    "ambiguous": ("모호한 이름 (연결 안 함)", "Ambiguous names (not linked)"), "h.candidates": ("후보", "Candidates"),
    "h.subject": ("주어", "Subject"), "h.predicate": ("술어", "Predicate"), "h.object": ("대상 / 값", "Object / value"),
    "h.knowledge": ("아는 범위", "Knowledge"), "h.turn": ("턴", "Turn"), "h.versions": ("버전", "Versions"),
    "h.with": ("함께한 인물", "With"),
    "h.position": ("#", "#"),
    "known_by": ("아는 인물", "known by"), "hidden_from": ("모르는 인물", "hidden from"),
    "k.public": ("공개", "public"), "k.limited": ("일부만 앎", "limited"), "k.unknown": ("미상", "unknown"),
    "retrievals": ("최근 검색", "Recent retrievals"),
    "h.when": ("시각", "When"), "h.query": ("질의", "Query"), "h.fresh": ("최신 여부", "Fresh"),
    "h.cand": ("후보", "Cand."), "h.sel": ("선택", "Sel."), "h.in_ctx": ("이미 문맥", "In-ctx"),
    "h.tokens": ("토큰", "Tokens"), "h.facts_kept": ("사실 (넣음/후보)", "Facts (kept/offered)"),
    "h.reason": ("사유", "Reason"), "h.changes": ("변경", "Changes"), "h.kinds": ("종류", "Kinds"),
    "members": ("현재 메시지 (최신순)", "Head membership (newest first)"),
    "h.role": ("역할", "Role"), "h.lifecycle": ("상태", "Lifecycle"), "h.disabled": ("비활성", "Disabled"),
    "h.processed": ("처리", "Processed"), "h.text": ("내용", "Text"),
    "not_normalized": ("정규화 안 됨", "not normalized"),
    "raw": ("원문", "raw"), "clean": ("정리", "clean"), "emb": ("임베딩", "emb"), "ext": ("추출", "ext"),
    "full": ("전체", "full"),
    "job.queued": ("대기", "queued"), "job.running": ("실행 중", "running"), "job.done": ("완료", "done"),
    "job.dead": ("실패", "dead"), "job.obsolete": ("폐기", "obsolete"),
    "ids": ("식별자", "Identifiers"),
    # contents: short names of the detail sections
    "toc.state": ("상태", "State"), "toc.coverage": ("처리 현황", "Coverage"), "toc.conflicts": ("충돌", "Conflicts"),
    "toc.threads": ("약속", "Promises"), "toc.unmatched": ("맞지 않은 이행·파기", "Unmatched"),
    "toc.facts": ("사실", "Facts"), "toc.items": ("아이템", "Items"), "toc.entities": ("엔티티", "Entities"),
    "toc.ambiguous": ("모호한 이름", "Ambiguous"), "toc.claims": ("주장", "Claims"), "toc.other": ("실제 아님", "Not actual"),
    "toc.retrievals": ("검색", "Retrievals"), "toc.commits": ("커밋", "Commits"), "toc.members": ("메시지", "Messages"),
    "toc.profile": ("프로필", "Profile"), "toc.held": ("소지품", "Belongings"), "toc.about": ("사실", "Facts"),
    "toc.takes_part": ("참여", "Takes part in"), "toc.packet": ("패킷", "Packet"),
    # Phase 9 (ADR 0027): the packet ledger of the latest request
    "packet": ("마지막 패킷: 들어간 줄과 빠진 이유", "Last packet: what went in, and why the rest did not"),
    "packet_intro": ("{when} 요청 · 정책 {policy} · {tokens}/{budget} 토큰 · 다음 응답: {reply}",
                     "Request at {when} · policy {policy} · {tokens}/{budget} tokens · next reply: {reply}"),
    "packet_echo": ("응답 반영 = 이 줄의 내용이 다음 응답에 다시 나온 정도(표면 비교, 사용 여부의 근사).",
                    "Echo = how much of the line's content reappears in the next reply (a surface measure of use)."),
    "h.kind": ("종류", "Kind"), "h.outcome": ("결과", "Outcome"), "h.echo": ("응답 반영", "Echo"),
    "h.placed": ("배치", "Placed"),
    "lk.state": ("상태", "state"), "lk.thread": ("약속", "thread"), "lk.fact": ("사실", "fact"),
    "lk.claim": ("주장", "claim"), "lk.excerpt": ("원문", "excerpt"),
    "pk.placed": ("들어감", "placed"), "pk.budget": ("예산 부족", "no budget"), "pk.state_cap": ("상태 상한", "state cap"),
    "pk.repeats": ("사실과 중복", "repeats a fact"),
    "pk.short": ("한 문장으로 줄임", "shortened to one sentence"), "pk.cut": ("잘라서 넣음", "cut to fit"),
    "rp.ok": ("있음", "present"), "rp.pending": ("아직 없음", "not yet"), "rp.changed": ("이후 앞부분이 바뀜", "story changed since"),
    "rp.not_a_reply": ("응답 아님", "not a reply"), "rp.not_recorded": ("원장 이전 기록", "recorded before the ledger"),
    "leak": ("숨긴 사실이 응답에 나옴", "a hidden fact reappears"),
    "toc.knows": ("아는 것", "Knows"), "toc.hidden": ("모르는 것", "Does not know"),
    # character view
    "who": ("캐릭터", "Character"), "who.all": ("전체", "All"),
    "who.gone": ("이 인물을 찾을 수 없습니다. 기억을 다시 만들었거나 이름이 다른 인물과 합쳐졌을 수 있습니다.",
                 "This character cannot be found. Memory may have been rebuilt, or the name merged with another."),
    "who.empty": ("이 인물에 대해 추출된 내용이 아직 없습니다.", "Nothing has been extracted about this character yet."),
    "profile": ("프로필", "Profile"), "held": ("지금 가진 것", "Holding now"),
    "about": ("이 인물에 대한 사실", "Facts about this character"),
    "takes_part": ("참여한 일 (주어나 대상이 아닌 사실)", "Takes part in (facts where they are neither subject nor object)"),
    "knows": ("아는 것", "What this character knows"), "hidden": ("모르는 것", "Kept from this character"),
    "knows_note": ("아는 범위는 추출 모델이 붙인 표시라 틀릴 수 있습니다.",
                   "Knowledge scopes are labels from the extraction model and may be wrong."),
    "who_claims": ("주장 (이 인물이 했거나 이 인물에 대한)", "Claims (by or about this character)"),
    "who_other": ("실제가 아닌 단언", "Not actual"),
    # stored values, shown translated (the raw value stays in the tooltip)
    "p.located_in": ("위치", "located in"), "p.has_status": ("상태", "status"), "p.identity": ("정체", "identity"),
    "p.has_trait": ("특징", "trait"), "p.relationship": ("관계", "relationship"), "p.feels_toward": ("감정", "feels toward"),
    "p.addresses": ("말투·호칭", "addresses"),
    "p.possesses": ("소지", "possesses"), "p.member_of": ("소속", "member of"), "p.knows": ("앎", "knows"),
    "p.goal": ("목표", "goal"), "p.promised": ("약속", "promised"), "p.event": ("사건", "event"),
    "p.world_fact": ("세계 설정", "world fact"), "p.also_called": ("별칭", "also called"),
    "p.destroyed": ("소멸", "destroyed"),
    "l.provisional": ("임시", "provisional"), "l.accepted": ("확정", "accepted"), "l.retracted": ("철회", "retracted"),
    "l.superseded": ("대체됨", "superseded"),
    "r.import": ("가져오기", "import"), "r.branch": ("분기", "branch"), "r.edit": ("수정", "edit"),
    "r.delete": ("삭제", "delete"), "r.swipe": ("스와이프", "swipe"), "r.reroll": ("다시 생성", "reroll"),
    "r.disable": ("비활성화", "disable"), "r.reconciliation": ("동기화", "reconciliation"), "r.manual": ("수동", "manual"),
    "f.fresh": ("최신", "fresh"), "f.stale": ("오래됨", "stale"), "f.unknown_conversation": ("모르는 대화", "unknown chat"),
    "m.hypothetical": ("가정", "hypothetical"), "m.dreamed": ("꿈", "dreamed"), "m.unknown": ("미상", "unknown"),
    "m.actual": ("실제", "actual"),
    "t.open": ("열림", "open"), "t.kept": ("지킴", "kept"), "t.broken": ("깨짐", "broken"),
    "s.major": ("중요", "major"), "s.minor": ("사소", "minor"), "p.fulfilled": ("약속 이행", "fulfilled"),
    "e.character": ("인물", "character"), "e.item": ("아이템", "item"), "e.place": ("장소", "place"),
    "e.group": ("집단", "group"), "e.concept": ("개념", "concept"),
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


def _facts_kept(timings: dict[str, Any]) -> str | None:
    """Fact lines that fit the budget out of those offered (ADR 0026); traces before it only offered."""
    if "facts" not in timings:
        return None
    return f"{timings['kept_facts']}/{timings['facts']}" if "kept_facts" in timings else f"?/{timings['facts']}"


def table(headers: list[str], rows: Iterable[list[str]]) -> str:
    head = "".join(f"<th>{escape(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return f"<div class=\"wrap\"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"


# Matches the "status-block" and "hp" rules in config/parsers.example.json.
NO_STATE_EXAMPLE = "```status\nHP: 80/100\nMP: 30/30\nLocation: Cafe\n```"


def _no_state_example(lang: str) -> str:
    return f"<p class=\"muted\">{_t(lang, 'no_state_hint')}</p><pre class=\"mono\">{_v(NO_STATE_EXAMPLE)}</pre>"


def chip(lang: str, prefix: str, value: Any) -> str:
    """A stored value as a translated chip; the raw value stays in the tooltip."""
    key = f"{prefix}.{value}"
    return f"<span class=\"chip\" title=\"{_v(value)}\">{_v(_t(lang, key) if key in T else value)}</span>"


def timestamp(value: Any) -> str:
    """A time in UTC. The exact instant stays in the tooltip: the plugin panel shows it in local time."""
    if not isinstance(value, datetime):
        return _v(str(value or "")[:19])
    utc = value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return f"<span class=\"ts\" title=\"{utc.isoformat(timespec='seconds')}\">{utc:%Y-%m-%d %H:%M} UTC</span>"


# (id, title, count or None, body, open by default)
Section = tuple[str, str, int | None, str, bool]


def sections(lang: str, parts: list[Section]) -> str:
    """Contents with counts, then each section as a fold that the contents links to."""
    def n(count: int | None) -> str:
        return "" if count is None else f" <span class=\"n\">{count}</span>"
    warn = " class=\"warn\""  # a conflict is the one thing that asks for attention
    toc = " · ".join(f"<a href=\"#s-{sid}\"{warn if sid == 'conflicts' and count else ''}>"
                     f"{_t(lang, f'toc.{sid}')}{n(count)}</a>" for sid, _, count, _, _ in parts)
    return f"<p class=\"toc\">{toc}</p>" + "".join(
        f"<details id=\"s-{sid}\"{' open' if is_open else ''}><summary><h2>{title}{n(count)}</h2></summary>{body}</details>"
        for sid, title, count, body, is_open in parts)


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
             _v(c["branched_from_host_chat_ref"] or ""), timestamp(c["last_retrieval"])]
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
        return f"<p class=\"muted\">{t('no_generation')}</p>"
    return table([t("h.projection"), t("h.generation"), t("h.coverage"), t("h.detail")], rows)


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


def _turn(a: dict[str, Any]) -> str:
    return _v(a["turn"] if a.get("turn") is not None else a["position"])


def with_participants(view: dict[str, Any]) -> dict[str, Any]:
    """Resolve the participants of the view's facts and claims for display (PHASE-8). Done here, not in
    every fact read: recall needs only their names."""
    r = view.get("resolution")
    if r is not None:
        for f in (*view["facts"], *view["claims"]):
            if f.get("participants"):
                f["participant_entities"] = participant_entities(f, r)
    return view


def _with(f: dict[str, Any], lang: str) -> str:
    """A fact's participants (PHASE-8): the entity's name, or the stored name when it does not resolve;
    groups carry a chip. Empty for facts without participants (older generations included)."""
    out = []
    for p in f.get("participant_entities") or []:  # set by with_participants() for the Inspector
        e = p.get("entity") or {}
        name = _v(e.get("name") or p["name"])
        if e.get("status") in ("ambiguous", "unresolved"):
            name = f"<span class=\"muted\" title=\"{_v(e['status'])}\">{name}</span>"
        out.append(name + (" " + chip(lang, "e", "group") if p["type"] == "group" else ""))
    return ", ".join(out)


def _facts_table(facts: list[dict[str, Any]], active: str | None, lang: str) -> str:
    t = lambda k: _t(lang, k)
    # A fact whose turn the active generation has not compiled yet comes from an older one (ADR 0014).
    older = f" <span class=\"chip\">{t('older_gen')}</span>"
    return table(
        [t(k) for k in ("h.subject", "h.predicate", "h.object", "h.with", "h.knowledge", "h.turn", "h.versions")],
        [[_v(f["subject"]), chip(lang, "p", f["predicate"]), _v(f.get("object") or f.get("value")), _with(f, lang),
          _knowledge(f, lang),
          _turn(f)
          + (older if active and f.get("generation") not in (None, active) else "")
          + (f" <span class=\"chip\">{t('negated')}</span>" if f.get("polarity") == "negative" else "")
          + (f" <span class=\"chip\">{t('disputed')}</span>" if f.get("disputed_by") else "")
          + (f" <span class=\"chip\">{t('legacy')}</span>" if f.get("source") is None else "")
          + _salience(f, lang),
          _v(f.get("versions", 1))]
         for f in facts])


def _salience(f: dict[str, Any], lang: str) -> str:
    """Events show their salience (ADR 0020); an unlabeled one (older generation) shows "—"."""
    if f.get("predicate") != "event":
        return ""
    if not f.get("salience"):
        return f" <span class=\"muted\" title=\"{_t(lang, 'salience')}\">—</span>"
    return " " + chip(lang, "s", f["salience"])


def _threads_table(threads: list[dict[str, Any]], lang: str) -> str:
    """Promises with their status and what closed them (PHASE-7, ADR 0019), newest first."""
    def closed(t: dict[str, Any]) -> str:
        c = t.get("closed_by")
        return f"{_turn(c)} · {_v(fact_line_text(c))}" if c else ""

    return table([_t(lang, k) for k in ("h.by", "h.to", "h.promise", "h.turn", "h.status", "h.closed", "h.restated")],
                 [[_v(t["by"]), _v(t.get("to") or ""), _v(t.get("text")), _turn(t), chip(lang, "t", t["status"]),
                   closed(t), _v(", ".join(str(r["turn"] if r.get("turn") is not None else r["position"])
                                          for r in t.get("restated") or []))]
                  for t in threads[:100]])


def _unmatched_table(unmatched: list[dict[str, Any]], lang: str) -> str:
    return table([_t(lang, k) for k in ("h.subject", "h.predicate", "h.object", "h.turn")],
                 [[_v(u["subject"]), chip(lang, "p", u["predicate"])
                   + (f" <span class=\"chip\">{_t(lang, 'negated')}</span>" if u.get("polarity") == "negative" else ""),
                   _v(u.get("value")), _turn(u)] for u in unmatched[:100]])


def _conflicts_table(conflicts: list[dict[str, Any]], lang: str) -> str:
    return table([_t(lang, k) for k in ("h.fact", "h.turn", "h.against", "h.turn")],
                 [[_v(c["text"]), _turn(c), _v(fact_line_text(c["against"])), _turn(c["against"])]
                  for c in conflicts[:100]])


def _claims_table(claims: list[dict[str, Any]], lang: str) -> str:
    return table([_t(lang, k) for k in ("h.by", "h.subject", "h.predicate", "h.object", "h.turn")],
                 [[_v(c.get("asserted_by")), _v(c["subject"]), chip(lang, "p", c["predicate"]),
                   _v(c.get("object") or c.get("value")), _turn(c)] for c in claims[:100]])


def _other_table(other: list[dict[str, Any]], lang: str) -> str:
    return table([_t(lang, k) for k in ("h.modality", "h.subject", "h.predicate", "h.object", "h.turn")],
                 [[chip(lang, "m", a["modality"]), _v(a["subject"]), chip(lang, "p", a["predicate"]),
                   _v(a.get("object") or a.get("value")), _turn(a)] for a in other[:100]])


def _who(conv_id: Any, entities: list[dict[str, Any]], current: str | None, q: str, lang: str) -> str:
    """Character picker: links here (the panel turns them into a drop-down), the shown one in bold."""
    chars = [e for e in entities if e["type"] == "character"][:50]
    chars += [e for e in entities if e["id"] == current and e not in chars]
    if not chars:
        return ""
    base, everyone = f"/inspector/c/{conv_id}", _t(lang, "who.all")
    links = [f"<b>{everyone}</b>" if current is None else f"<a href=\"{base}{q}\">{everyone}</a>"]
    links += [f"<b>{_v(e['name'])}</b>" if e["id"] == current else f"<a href=\"{base}/e/{e['id']}{q}\">{_v(e['name'])}</a>"
              for e in chars]
    return f"<p class=\"who\"><span class=\"muted\">{_t(lang, 'who')}</span> " + " · ".join(links) + "</p>"


def _meta(conv: dict[str, Any], lang: str) -> str:
    """Internal identifiers, folded away; where a branch came from stays in view."""
    t = lambda k: _t(lang, k)
    branched = (f"<p class=\"muted\">{t('branched_from')} {_v(conv['branched_from_host_chat_ref'])} {t('at')} "
                f"{_v(conv['branched_from_message_ref'])}</p>" if conv.get("branched_from_host_chat_ref") else "")
    return (branched + f"<details class=\"meta\"><summary class=\"muted\">{t('ids')}</summary>"
            f"<p class=\"muted mono\">{_v(conv['host_chat_ref'])}<br>{t('conversation')} {_v(conv['id'])} · "
            f"{t('head')} {_v(conv['head_commit_id'])}</p></details>")


def detail(conv: dict[str, Any], state: list[dict[str, Any]], members: list[dict[str, Any]],
           commits: list[dict[str, Any]], traces: list[dict[str, Any]], facts: list[dict[str, Any]],
           token: str | None, coverage: dict[str, Any] | None = None, lang: str = "ko", embed: bool = False,
           claims: list[dict[str, Any]] | None = None, other: list[dict[str, Any]] | None = None,
           entities: list[dict[str, Any]] | None = None, ambiguous: list[dict[str, Any]] | None = None,
           conflicts: list[dict[str, Any]] | None = None, items: list[dict[str, Any]] | None = None,
           threads: list[dict[str, Any]] | None = None, unmatched: list[dict[str, Any]] | None = None,
           packet: dict[str, Any] | None = None) -> str:
    t = lambda k: _t(lang, k)
    q = query(token, lang)
    name, path = label(conv), f"/inspector/c/{conv['id']}"
    head = (f"<div class=\"top\"><p><a href=\"/inspector{q}\">{t('back')}</a></p>"
            f"{'' if embed else _lang_switch(path, token, lang)}</div>"
            f"<h1>{_v(name)}</h1>" + _meta(conv, lang) + _who(conv["id"], entities or [], None, q, lang))
    active = (((coverage or {}).get("extraction") or {}).get("generation") or {}).get("key")
    # What needs a look comes first; logs of the machinery start folded.
    parts: list[Section] = [
        ("state", t("state"), None, table([t("h.key"), t("h.value"), t("h.as_of"), t("h.rule")],
                                          [[_v(s["key"]), _v(s["value"]), _v(s["position"]), _v(s["rule_id"])]
                                           for s in state])
         if state else f"<p class=\"muted\">{t('no_state')}</p>{_no_state_example(lang)}", True),
        ("coverage", t("coverage"), None, _coverage_section(coverage or {}, lang), True)]
    if conflicts:
        parts.append(("conflicts", t("conflicts"), len(conflicts), _conflicts_table(conflicts, lang), True))
    if threads:
        parts.append(("threads", t("threads"), len(threads), _threads_table(threads, lang), True))
    if unmatched:
        parts.append(("unmatched", t("unmatched"), len(unmatched), _unmatched_table(unmatched, lang), True))
    if facts:
        parts.append(("facts", t("facts"), len(facts), _facts_table(facts, active, lang), True))
    if items:
        parts.append(("items", t("items"), len(items), table(
            [t("h.item"), t("h.timeline")],
            [[_v(i["item"]), " → ".join(_step(h, lang) for h in i["history"])] for i in items[:100]]), True))
    if entities:
        parts.append(("entities", t("entities"), len(entities), table(
            [t(k) for k in ("h.type", "h.names", "h.mentions", "h.alias_turns", "h.owner_links")],
            [[chip(lang, "e", e["type"]), _v(" · ".join(e["names"])), _v(e["mentions"]),
              _v(", ".join(str(a["turn"]) for a in e["aliases"])), _owner_links(e)] for e in entities[:200]]), True))
    if ambiguous:
        parts.append(("ambiguous", t("ambiguous"), len(ambiguous), table(
            [t(k) for k in ("h.type", "h.names", "h.candidates")],
            [[chip(lang, "e", a["type"]), _v(a["name"]), _v(" · ".join(a["candidates"]))] for a in ambiguous]), True))
    if claims:
        parts.append(("claims", t("claims"), len(claims), _claims_table(claims, lang), True))
    if other:
        parts.append(("other", t("other"), len(other), _other_table(other, lang), False))
    if packet and packet.get("lines"):
        parts.append(("packet", t("packet"), sum(e["placed"] for e in packet["lines"]),
                      _packet_section(packet, traces[0] if traces else {}, lang), True))
    parts.append(("retrievals", t("retrievals"), len(traces), table(
        [t(k) for k in ("h.when", "h.query", "h.fresh", "h.cand", "h.sel", "h.in_ctx", "h.facts_kept", "h.placed",
                        "h.tokens")] + ["ms"],
        [[timestamp(r["created_at"]), _v(r["query"]), chip(lang, "f", r["freshness"]), _v(r["candidates"]),
          _v(r["selected"]), _v(r["excluded"]), _v(_facts_kept(r["latency_ms"] or {})), _placed(r, lang),
          _v(r["token_estimate"]),
          _v((r["latency_ms"] or {}).get("sidecar_total"))] for r in traces]), False))
    parts.append(("commits", t("h.commits"), len(commits), table(
        ["#", t("h.reason"), t("h.changes"), t("h.kinds"), t("h.when")],
        [[_v(c["seq"]), chip(lang, "r", c["reason"]), _v(c["changes"]), _v(c["kinds"]), timestamp(c["created_at"])]
         for c in commits]), False))
    parts.append(("members", t("members"), len(members), table(
        [t(k) for k in ("h.position", "h.turn", "h.role", "h.lifecycle", "h.disabled", "h.processed", "h.text")],
        [[_v(m["position"]), _v(m.get("turn")), _v(m["role"]), chip(lang, "l", m["lifecycle"]),
          _v(m["disabled"] or ""), _processed(m, lang), _v(m["preview"]) + ("…" if m["length"] > 240 else "")]
         for m in members]), False))
    body = head + sections(lang, parts)
    return body if embed else page(f"NMOS · {name}", body, lang)


def _placed(trace: dict[str, Any], lang: str) -> str:
    """What a request's packet held by kind (ADR 0027), e.g. "사실 6 · 원문 1"; empty before the ledger."""
    placed = (trace.get("latency_ms") or {}).get("placed") or {}
    return _v(" · ".join(f"{_t(lang, f'lk.{k}')} {n}" for k, n in placed.items() if n))


def _packet_section(packet: dict[str, Any], trace: dict[str, Any], lang: str) -> str:
    """The latest request's ledger: every offered line with its outcome, cost and echo (ADR 0027)."""
    t = lambda k: _t(lang, k)
    summary = packet["summary"]
    intro = t("packet_intro").format(when=timestamp(trace.get("created_at")), policy=_v(packet.get("policy")),
                                     tokens=_v(packet.get("tokens")), budget=_v(packet.get("budget_tokens")),
                                     reply=_v(t(f"rp.{summary['reply']}")))
    rows = []
    for e in packet["lines"]:
        outcome = chip(lang, "pk", e["why"])
        if e.get("form"):
            outcome += " " + chip(lang, "pk", e["form"])
        echo = "" if "echo" not in e else f"{round(e['echo'] * 100)}%"
        if e.get("possible_leak"):
            echo += f" <span class=\"warn\">{_v(t('leak'))}</span>"
        rows.append([chip(lang, "lk", e["kind"]), _v(e.get("turn")), _v(e.get("text")), outcome, _v(e.get("tok")), echo])
    return (f"<p class=\"muted\">{intro}</p>"
            + table([t(k) for k in ("h.kind", "h.turn", "h.text", "h.outcome", "h.tokens", "h.echo")], rows)
            + f"<p class=\"muted\">{_v(t('packet_echo'))}</p>")


def _owner_links(entity: dict[str, Any]) -> str:
    """The owner's links that joined this entity's names (ADR 0025), as "name = same as"."""
    return _v(", ".join(f"{link['name']} = {link['same_as']}" for link in entity.get("links") or []))


def character(conv: dict[str, Any], entity_id: str, view: dict[str, list[dict[str, Any]]], token: str | None,
              active: str | None = None, lang: str = "ko", embed: bool = False) -> str:
    """One character's side of the conversation: what is true of them, what they hold, know and claim.

    Read-only regrouping of the same memory view as the detail page; it changes nothing the packet uses.
    """
    t = lambda k: _t(lang, k)
    q = query(token, lang)
    conv_path = f"/inspector/c/{conv['id']}"
    entity = next((e for e in view["entities"] if e["id"] == entity_id), None)
    title = entity["name"] if entity else t("who")
    head = (f"<div class=\"top\"><p><a href=\"{conv_path}{q}\">← {_v(label(conv))}</a></p>"
            f"{'' if embed else _lang_switch(f'{conv_path}/e/{entity_id}', token, lang)}</div>"
            f"<h1>{_v(title)}</h1>" + _who(conv["id"], view["entities"], entity_id, q, lang))
    if entity is None:
        body = head + f"<p class=\"muted\">{t('who.gone')}</p>"
        return body if embed else page(f"NMOS · {title}", body, lang)

    names = {norm(n) for n in entity["names"]}

    def me(ref: dict[str, Any] | None) -> bool:
        return (ref or {}).get("id") == entity_id

    def involves(a: dict[str, Any]) -> bool:
        return me(a.get("subject_entity")) or me(a.get("object_entity"))

    def among(people: list[str] | None) -> bool:
        return any(norm(p) in names for p in people or [])

    facts = view["facts"]
    mine = [f for f in facts if involves(f)]
    held = [f for f in mine if f["predicate"] == "possesses" and f.get("polarity") == "positive"
            and me(f.get("subject_entity"))]
    knows = [f for f in facts if among(f.get("known_by"))
             or (f["predicate"] == "knows" and f.get("polarity") == "positive" and me(f.get("subject_entity")))]
    about = [f for f in mine if f not in held and f not in knows]  # each fact under one heading
    takes_part = [f for f in facts if not involves(f) and f not in knows
                  and any(me(p.get("entity")) for p in f.get("participant_entities") or [])]
    hidden = [f for f in facts if among(f.get("hidden_from"))]
    claims = [c for c in view["claims"] if norm(c.get("asserted_by")) in names or involves(c)]
    other = [a for a in view["other"] if involves(a)]
    ids = {f["id"] for f in mine}
    conflicts = [c for c in view["conflicts"] if c["fact"] in ids]
    threads = [th for th in view.get("threads", []) if norm(th["by"]) in names or norm(th.get("to")) in names]

    def knowledge(rows: list[dict[str, Any]]) -> str:
        return table([t("h.fact"), t("h.knowledge"), t("h.turn")],
                     [[_v(fact_line_text(f)), _knowledge(f, lang), _turn(f)] for f in rows]) \
            + f"<p class=\"muted\">{t('knows_note')}</p>"

    parts: list[Section] = [("profile", t("profile"), None, table(
        [t("h.type"), t("h.names"), t("h.mentions"), t("h.alias_turns"), t("h.owner_links")],
        [[chip(lang, "e", entity["type"]), _v(" · ".join(entity["names"])), _v(entity["mentions"]),
          _v(", ".join(str(a["turn"]) for a in entity["aliases"])), _owner_links(entity)]]), True)]
    if conflicts:
        parts.append(("conflicts", t("conflicts"), len(conflicts), _conflicts_table(conflicts, lang), True))
    if threads:
        parts.append(("threads", t("threads"), len(threads), _threads_table(threads, lang), True))
    if held:
        parts.append(("held", t("held"), len(held), table(
            [t("h.item"), t("h.turn"), t("h.timeline")],
            [[_v(f["object"]), _turn(f), " → ".join(_step(h, lang) for h in f.get("history") or [])] for f in held]),
            True))
    if about:
        parts.append(("about", t("about"), len(about), _facts_table(about, active, lang), True))
    if takes_part:
        parts.append(("takes_part", t("takes_part"), len(takes_part), _facts_table(takes_part, active, lang), True))
    if knows:
        parts.append(("knows", t("knows"), len(knows), knowledge(knows), True))
    if hidden:
        parts.append(("hidden", t("hidden"), len(hidden), knowledge(hidden), True))
    if claims:
        parts.append(("claims", t("who_claims"), len(claims), _claims_table(claims, lang), True))
    if other:
        parts.append(("other", t("who_other"), len(other), _other_table(other, lang), False))
    body = head + sections(lang, parts)
    if len(parts) == 1:
        body += f"<p class=\"muted\">{t('who.empty')}</p>"
    return body if embed else page(f"NMOS · {title}", body, lang)
