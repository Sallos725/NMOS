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
from .predicates import REGISTRY
from .repairs import default_outcome, outcomes
from .facts import STANDING, earlier, first, participant_entities, symmetric
from . import scene
from .retrieval import CAST_GOALS, cast_facts
from .summaries import LAG, WINDOW

STYLE = """
:root{color-scheme:light dark;--bg:#fbfbfa;--fg:#1d1d1f;--muted:#6b6b70;--line:#e3e3e0;--chip:#efefec;--accent:#3b5bdb}
@media (prefers-color-scheme:dark){:root{--bg:#18181a;--fg:#ececec;--muted:#9a9aa0;--line:#2c2c30;--chip:#26262a;--accent:#8ea2ff}}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,-apple-system,"Noto Sans KR",sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px}
h1{font-size:20px;margin:0 0 4px} h2{font-size:15px;margin:28px 0 8px}
a{color:var(--accent);text-decoration:none} a:hover{text-decoration:underline}
.muted{color:var(--muted)} .mono{font-family:ui-monospace,monospace;font-size:12px}
pre.mono{white-space:pre-wrap;background:var(--chip);padding:8px 10px;border-radius:6px;margin:4px 0 0}
.top{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:baseline;gap:12px}
.refresh{margin:0} .refresh button{font:inherit;color:var(--fg);background:var(--chip);border:1px solid var(--line);border-radius:6px;padding:4px 10px;cursor:pointer}
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
    "conflicts": ("충돌 (이야기끼리, 원전과, 고정한 사실과)", "Conflicts (within the story, with canon, with a lock)"),
    "h.fact": ("현재 사실", "Current fact"), "h.against": ("맞지 않는 단언", "Contradicted by"),
    "threads": ("스레드 (약속·목표·질문·위협·빚)", "Threads (promises, goals, questions, threats, debts)"),
    "h.to": ("상대", "To"), "h.promise": ("내용", "What"), "h.kind": ("종류", "Kind"),
    "h.status": ("상태", "Status"), "h.closed": ("닫은 단언", "Closed by"), "h.restated": ("다시 말한 턴", "Restated in turn"),
    "unmatched": ("어느 스레드에도 맞지 않은 종료", "Ends matching no open thread"),
    "salience": ("중요도", "salience"),
    "items": ("아이템 이력", "Item timelines"), "h.item": ("아이템", "Item"), "h.timeline": ("이력 (오래된 순)", "Timeline (oldest first)"),
    "w.possesses": ("{s} 보유", "held by {s}"), "w.located_in": ("{o}에 있음", "at {o}"),
    "w.destroyed": ("소멸: {v}", "destroyed: {v}"), "w.not": ("아님", "not"),
    "o.current": ("현재", "current"), "o.superseded": ("대체됨", "superseded"), "o.ended": ("끝남", "ended"),
    "o.conflicting": ("충돌", "conflicting"),
    "claims": ("인물의 주장", "Claims by characters"), "h.by": ("말한 인물", "Said by"),
    "because": ("원인", "because"), "cause_event": ("그 사건", "that event"),
    "pairs": ("관계 (인물 쌍마다)", "Relationships"), "toc.pairs": ("관계", "Relationships"),
    "h.pair": ("두 인물", "Pair"), "h.relationship": ("관계", "Relationship"),
    "h.role": ("역할", "Role"), "h.feelings": ("감정", "Feelings"),
    "h.speech": ("말투·호칭", "Speech"), "before": ("이전", "before"), "first": ("처음", "first"),
    "summaries": ("요약 (장면·지금까지의 이야기)", "Summaries (scenes, story so far)"), "toc.summaries": ("요약", "Summaries"),
    "story": ("지금까지의 이야기", "Story so far"), "h.turns": ("턴", "Turns"), "h.summary": ("요약", "Summary"),
    "sm.current": ("있음", "current"), "sm.waiting": ("대기", "waiting"), "sm.held": ("보류: 비밀을 담음", "held back: repeats a secret"),
    "sm.unlisted": ("보류: 뒤에 드러난 비밀, 다시 작성", "held back: a secret stated after it, written again"),
    "sm.near": ("{names} 앞에서는 쓰지 않음", "not used while {names} is in the scene"),
    "sm.queued": ("작성 대기", "queued"), "sm.running": ("작성 중", "writing"), "sm.dead": ("실패", "failed"),
    "sm.changed": ("장면이 바뀜: 다시 작성", "scene changed: written again"),
    "sm.secret": ("비밀", "secret"), "sm.generation": ("요약 세대", "Summary generation"),
    "sm.off": ("장면 요약이 꺼져 있습니다. 저장된 요약만 보여 주며, 어떤 패킷도 쓰지 않습니다.",
               "Scene summaries are off: the stored ones are shown, and no packet uses them."),
    "sm.narrator": ("화자 모드: 이 채팅의 패킷에는 <Story>가 들어가지 않습니다.", "Narrator mode: this chat's packets have no <Story>."),
    "sm.story_wait": ("모든 장면에 요약이 생기면 작성합니다 ({n}/{m}).", "Written once every scene has a summary ({n} of {m})."),
    "sm.behind": ("최신 장면은 아직 반영 안 됨", "the newest scenes are not in it yet"),
    "sm.story_covers": ("장면 {n}/{m}개", "scenes 1–{n} of {m}"), "sm.none": ("아직 요약할 장면이 없습니다 ({w}턴마다 한 장면, 뒤로 {l}턴이 더 지나면 요약).",
                                                      "No scene to summarize yet (one scene per {w} turns, summarized {l} turns later)."),
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
    # the first page's status (PHASE-23 Q8): what the tray's and the menu bar's "dashboard" opens
    "version": ("버전", "Version"),
    "refresh": ("새로고침", "Refresh"),
    "errors": ("최근 오류", "Recent errors"),
    "errors.none": ("실패했거나 다시 시도 중인 백그라운드 작업이 없습니다.", "No background job has failed or is retrying."),
    "h.job": ("작업", "Job"), "h.status": ("상태", "Status"), "h.attempts": ("시도", "Attempts"),
    "h.when": ("시각", "When"), "h.error": ("오류", "Error"),
    "ids": ("식별자", "Identifiers"),
    # contents: short names of the detail sections
    "toc.state": ("상태", "State"), "toc.coverage": ("처리 현황", "Coverage"), "toc.conflicts": ("충돌", "Conflicts"),
    "toc.threads": ("스레드", "Threads"), "toc.unmatched": ("맞지 않은 종료", "Unmatched"),
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
    "lk.summary": ("요약", "summary"), "lk.cast": ("인물 상태", "cast"),
    "pk.placed": ("들어감", "placed"), "pk.budget": ("예산 부족", "no budget"), "pk.state_cap": ("상태 상한", "state cap"),
    "pk.repeats": ("사실과 중복", "repeats a fact"), "pk.restates": ("앞 줄과 같은 내용", "says an earlier line again"),
    "fits_at": ("예산 {n}이면 모두", "all at {n}"),
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
    "now": ("지금 상태 (<Cast>)", "Current state (<Cast>)"), "toc.now": ("지금 상태", "Current state"),
    "cs.located_in": ("있는 곳", "Place"), "cs.has_status": ("상태", "Condition"),
    "cs.feels_toward": ("페르소나에 대한 감정", "Feeling toward the persona"), "cs.possesses": ("지닌 것", "Carries"),
    "cs.goal": ("열린 목표", "Open goal"), "h.aspect": ("항목", "Aspect"),
    "cs.note": ("이 인물이 장면에 있을 때 패킷의 <Cast>가 말하는 내용입니다. 목표는 메시지가 이 인물을 부를 때만 {n}개까지 "
                "들어가고, 장면의 일부만 아는 줄은 <Private>에 남습니다.",
                "What the packet's <Cast> says of this character when they are in the scene. Open goals go in, up to {n}, "
                "only when the message names them, and a line only some of the scene know stays in <Private>."),
    "cs.empty": ("<Cast>에 넣을 현재 상태가 없습니다.", "No current state for <Cast>."),
    "profile": ("프로필", "Profile"), "held": ("지금 가진 것", "Holding now"),
    "about": ("이 인물에 대한 사실", "Facts about this character"),
    "takes_part": ("참여한 일 (주어나 대상이 아닌 사실)", "Takes part in (facts where they are neither subject nor object)"),
    "knows": ("아는 것", "What this character knows"), "hidden": ("모르는 것", "Kept from this character"),
    "knows_note": ("아는 범위는 추출 모델이 붙인 표시라 틀릴 수 있습니다.",
                   "Knowledge scopes are labels from the extraction model and may be wrong."),
    "who_claims": ("주장 (이 인물이 했거나 이 인물에 대한)", "Claims (by or about this character)"),
    "who_other": ("실제가 아닌 단언", "Not actual"),
    # the plugin build (ADR 0037)
    "plugin.none": ("플러그인: 이 사이드카가 시작된 뒤 아직 동기화한 플러그인이 없습니다. 다음 생성 뒤에 확인됩니다 (맞는 빌드 {want}).",
                    "Plugin: none has synced since this sidecar started; the next generation shows it (matching build {want})."),
    "plugin.ok": ("플러그인: 사이드카와 같은 빌드 {build} ({when})", "Plugin: the sidecar's build {build} ({when})"),
    "plugin.old": ("⚠ 플러그인이 이 사이드카와 다른 빌드입니다: 사용 중 {build} ({when}), 맞는 빌드 {want}. 플러그인 파일을 교체하고 PocketRisu를 새로 고침하세요.",
                   "⚠ The plugin is not this sidecar's build: in use {build} ({when}), matching build {want}. Replace the plugin file and reload PocketRisu."),
    "plugin.get": ("맞는 파일: {link}", "Matching file: {link}"),
    "plugin.other": ("⚠ 다른 탭이나 기기에서 예전 플러그인({builds})이 동기화했습니다 ({when}). 그 화면을 새로 고침하세요.",
                     "⚠ An older plugin ({builds}) synced from another tab or device ({when}). Reload that screen."),
    "plugin.no_build": ("빌드 정보 없음(예전 플러그인)", "no build id (an older plugin)"),
    # secrets (PHASE-10 step 6, ADR 0033)
    "toc.secrets": ("비밀", "Secrets"), "toc.unrevealed": ("맞는 비밀 없는 발견", "Unmatched reveals"),
    "toc.found_out": ("알게 된 비밀", "Found out"),
    "secrets": ("비밀 (누구에게 숨기는지, 누가 언제 알게 됐는지)", "Secrets (kept from whom, who found out and when)"),
    "unrevealed": ("알게 됐다는 보고 중 맞는 비밀이 없는 것", "Reveals that matched no open secret"),
    "found_out": ("이 인물이 알게 된 비밀", "Secrets this character found out"),
    "h.secret": ("비밀", "Secret"), "h.holders": ("아는 인물", "Known by"), "h.kept_from": ("숨기는 상대", "Kept from"),
    "h.who": ("인물", "Who"), "h.listed": ("보고된 비밀", "Reported secret"), "h.evidence": ("근거", "Evidence"),
    "h.found": ("알게 된 턴", "Found out in turn"),
    "sec.open": ("아직 모름", "does not know yet"), "sec.ended": ("{turn}턴에 알게 됨", "found out in turn {turn}"),
    "or.closed": ("오너가 닫음", "closed by the owner"), "or.marked": ("오너 표시", "marked by the owner"),
    "or.corrected": ("오너가 고침", "corrected by the owner"),
    "rs.via": ("{names}을(를) 거쳐 아직 한 인물", "still one entity through {names}"),
    "attention": ("확인 필요", "Needs attention"), "toc.attention": ("확인 필요", "Needs attention"),
    "h.issue": ("무엇", "What"),
    "at.stale": ("{n}턴 넘게 다시 나오지 않은 열린 스레드", "open for more than {n} turns without a restatement"),
    "at.unmatched": ("짝이 맞는 열린 스레드가 없는 종료", "an end matching no open thread"),
    # PHASE-22 Q6: a narrated fact a re-extraction of the turn left out, which memory no longer holds anywhere
    "at.dropped": ("다시 추출하면서 사라진 사실 (복원하면 그 턴의 사실로 다시 기억)",
                   "dropped by a re-extraction (restore it to remember it at its turn again)"),
    "at.disputed": ("이야기가 엇갈린 사실", "a fact the story contradicts"),
    # PHASE-28 Q7: a role ending applied after its confirmation, or held by it (the model can be wrong both times)
    "at.role_auto": ("자동으로 끝난 역할 (철회하면 다시 현재 역할)",
                     "a role ended automatically (retract it to keep the role)"),
    "at.role_held": ("확인되지 않아 보류된 역할 종료: {why} (복원하면 그 턴에 끝남)",
                     "a role ending held, not confirmed: {why} (restore it to end the role at its turn)"),
    # PHASE-29 Q5: an alias a confirmation held joins nothing; listed so a wrong hold (one person's two names apart) is seen
    "at.alias_held": ("확인되지 않아 보류된 별명: {why} (연결하면 한 사람으로 읽음)",
                      "an alias held, not confirmed: {why} (link it to read them as one person)"),
    "at.repair": ("지금 맞는 항목이 없는 수리", "a repair that matches nothing now"),
    "at.split": ("아직 한 인물인 이름 분리", "a split whose names are still one entity"),
    "at.ambiguous": ("모호한 이름 (연결 안 함)", "an ambiguous name (not linked)"),
    "at.none": ("확인할 것이 없습니다.", "Nothing needs a look."),
    "at.note": ("NMOS가 이미 찾아낸 것 가운데 오너가 고칠 수 있는 것입니다. NMOS 화면의 인스펙터 탭에서 줄마다 고칠 수 있습니다.",
                "What NMOS already found that the owner can fix: the panel's Inspector tab fixes each line."),
    "repairs": ("수리 (오너가 고친 것)", "Repairs (what the owner fixed)"), "toc.repairs": ("수리", "Repairs"),
    "canon": ("원전 (카드·로어북·페르소나·작가 노트)", "Canon (card, lorebooks, persona, author's note)"),
    "toc.canon": ("원전", "Canon"), "h.source": ("원전", "Source"), "h.what": ("무엇", "What"),
    "h.chars": ("글자 수", "Chars"), "h.since": ("효력 시작", "In force since"),
    "h.held": ("프롬프트에 든 요청", "In prompts"), "cn.card": ("카드", "card"), "cn.note": ("작가 노트", "author's note"),
    "cn.about": (
        "호스트가 이 채팅에 보여 주는 원전입니다. 카드를 고치면 새 판이 생기고 옛 판은 이력으로 남습니다. 호스트가 이미 보내는 원전은 "
        "NMOS가 다시 보내지 않습니다.",
        "The canon the host shows this chat. A card edit makes a new version and keeps the old one. NMOS does not send "
        "again what the host already sends."),
    "cn.persona": ("페르소나", "persona"), "cn.lore": ("로어북", "lorebook"), "cn.keys": ("키 {n}개", "{n} keys"),
    "cn.held": ("{n}회, 마지막", "{n}×, last"), "cn.never": ("아직 없음", "not yet"),
    "cn.missing": ("텍스트가 아직 오지 않음", "text not received yet"),
    "h.read": ("사실 읽기", "Facts read"), "cn.read": ("읽음 (호출 {n}회)", "read ({n} calls)"),
    "cn.reading": ("읽는 중", "reading"), "cn.failed": ("실패", "failed"),
    "cn.unread": ("아직 안 읽음 (프롬프트에 든 적 없음)", "not read (no prompt held it yet)"),
    "cn.none": ("읽지 않음", "not read"),
    "cn.facts": ("원전에서 읽은 사실 {n}개가 기억에 들어 있습니다. 이야기가 새로 말하면 그 턴부터 이야기를 따릅니다. 호스트가 이미 "
                 "보낸 원전의 사실은 패킷에 다시 넣지 않습니다.",
                 "{n} facts read from the canon are in memory. The story supersedes them from the turn it says something "
                 "new. Facts of canon the host already sent are not sent again."),
    "canon_row": ("원전 사실", "Canon facts"),
    "us.title": ("모델 사용량", "Model usage"), "toc.usage": ("사용량", "Usage"),
    "us.intro": ("이 채팅의 기억에 NMOS가 부른 모델 호출과, 제공자가 보고한 토큰이에요. 추정하지 않아요. 다시 만들면서 버린 결과의 "
                 "호출도 셉니다. NMOS가 지금 가진 결과 기준이라, 임베딩 모델을 바꾸면 정리된 이전 임베딩의 호출은 빠져요.",
                 "The model calls NMOS made for this chat's memory, and the tokens the provider reported; nothing is "
                 "estimated. Calls whose results were discarded by a rebuild count too. It counts the results NMOS "
                 "still holds: after the embedding model changes, the earlier embeddings are cleaned up and their calls "
                 "no longer count."),
    "us.none": ("아직 기록된 모델 호출이 없어요.", "No model calls recorded yet."),
    "us.kind.extract": ("사실 추출", "Fact extraction"), "us.kind.canon": ("원전 읽기", "Canon reads"),
    "us.kind.summarize": ("요약", "Summaries"), "us.kind.embed": ("임베딩", "Embeddings"),
    "us.kind.reveal": ("비밀 확인", "Reveal checks"),
    "us.total": ("합계", "Total"), "us.active": ("사용 중", "active"),
    "us.h.calls": ("호출", "Calls"), "us.h.input": ("입력 토큰", "Input tokens"),
    "us.h.output": ("출력 토큰", "Output tokens"), "us.h.cached": ("캐시 입력", "Cached input"),
    "us.h.reported": ("보고된 호출", "Calls reported"),
    "us.not_reported": ("보고 없음", "not reported"),
    "us.partial": ("일부", "partly"),
    "us.no_generation": ("세대 없음 (이전 버전)", "no generation (older version)"),
    "us.not_recorded": ("기록 이전 결과 {n}개", "{n} results from before recording"),
    "canon_detail": ("모델 호출 {calls} · 대기 {pending} · 실패 {failed} · 안 읽은 글자 {unread}",
                     "model calls {calls} · pending {pending} · failed {failed} · characters not read {unread}"),
    "cf.disputed": ("이야기끼리", "story vs story"), "cf.canon": ("원전과 이야기", "canon vs story"),
    "cf.locked": ("고정한 사실과 이야기", "locked vs story"),
    "at.canon": ("원전과 다른 이야기 (고정하면 원전 유지, 철회하면 이야기 유지)",
                 "the story differs from canon (lock keeps canon's, retract keeps the story's)"),
    "at.canon_says": ("원전", "canon"), "at.story_says": ("이야기", "story"),
    "or.locked": ("오너가 고정", "locked by the owner"),
    "held_off": ("이야기 {n}건 보류", "{n} story statements held off"),
    "rk.fact_lock": ("사실 고정", "lock a fact"),
    "rk.thread_close": ("스레드 닫기", "close a thread"), "rk.thread_reopen": ("스레드 다시 열기", "reopen a thread"),
    "rk.secret_found_out": ("비밀을 알게 됨", "secret found out"), "rk.secret_keep": ("비밀 유지", "secret still kept"),
    "rk.fact_restore": ("사실 복원", "restore a fact"), "rk.fact_retract": ("사실 철회", "retract a fact"), "rk.fact_correct": ("사실 정정", "correct a fact"),
    "rk.name_split": ("이름 분리", "split two names"),
    "rs.applied": ("적용됨", "applied"), "rs.unmatched": ("지금 맞는 항목 없음", "matches nothing now"),
    "rs.removed": ("되돌림", "taken back"),
    "h.repair": ("수리", "Repair"), "h.target": ("대상", "Target"), "h.value": ("내용", "Value"), "h.made": ("만든 때", "Made"),
    "or.note": ("오너가 고친 것은 재구축과 새 추출 세대에도 남습니다. 대상의 턴이 편집되거나 새 세대가 내용을 너무 다르게 적으면 "
                "'지금 맞는 항목 없음'이 됩니다.",
                "What the owner fixed survives rebuilds and new extractor generations. When the target's turn is edited, or a "
                "new generation words it too differently, the repair matches nothing."),
    "sec.note": ("추출 모델이 붙인 표시라 틀릴 수 있습니다. 같은 비밀이 여러 턴에 다시 기록되면 줄도 여러 개입니다. 알게 된 턴을 "
                 "지우거나 고치면 비밀이 다시 열립니다.",
                 "Marks from the extraction model may be wrong. A secret extracted again in later turns has a line for "
                 "each. Deleting or editing the turn that revealed it opens it again."),
    "unrevealed_note": ("추출 모델이 누군가 비밀을 알게 됐다고 보고했지만, 그 인물에게 숨긴 열린 비밀 중 맞는 것이 없었습니다. "
                        "아무 비밀도 끝내지 않았습니다.",
                        "The extraction model reported someone finding out a secret, but no open secret kept from them "
                        "matched. Nothing was ended."),
    "scene": ("장면 인물: {cast} · 기억 모드: {mode}", "Scene: {cast} · memory mode: {mode}"),
    "mode.default": ("기본", "default"), "mode.strict": ("엄격", "strict"), "mode.narrator": ("1인칭 화자 {n}", "narrator {n}"),
    "mode.withheld": ("모드로 빠지거나 바뀐 줄 {n}", "{n} withheld by the mode"),
    "lk.secret": ("비밀", "secret"),
    # stored values, shown translated (the raw value stays in the tooltip)
    "p.located_in": ("위치", "located in"), "p.has_status": ("상태", "status"), "p.identity": ("정체", "identity"),
    "p.has_trait": ("특징", "trait"), "p.relationship": ("관계", "relationship"),
    "p.role_toward": ("역할", "role toward"), "p.feels_toward": ("감정", "feels toward"),
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
    "t.achieved": ("이룸", "achieved"), "t.abandoned": ("그만둠", "abandoned"), "t.failed": ("실패", "failed"),
    "t.answered": ("답이 나옴", "answered"), "t.averted": ("피함", "averted"), "t.paid": ("갚음", "paid"),
    "k.promise": ("약속", "promise"), "k.goal": ("목표", "goal"), "k.question": ("질문", "question"),
    "k.threat": ("위협", "threat"), "k.debt": ("빚", "debt"),
    "p.question": ("질문", "question"), "p.threat": ("위협", "threat"), "p.owes": ("빚", "owes"),
    "p.resolved": ("스레드 종료", "resolved"),
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


def _facts_kept(timings: dict[str, Any], lang: str = "en") -> str | None:
    """Fact lines that fit the budget out of those offered (ADR 0026); traces before it only offered. When
    memory was left out, the budget that would hold it all (ADR 0036)."""
    if "facts" not in timings:
        return None
    kept = f"{timings['kept_facts']}/{timings['facts']}" if "kept_facts" in timings else f"?/{timings['facts']}"
    return kept + (f" ({_t(lang, 'fits_at').format(n=timings['fits_at'])})" if timings.get("fits_at") else "")


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


def _errors(errors: list[dict[str, Any]], lang: str) -> str:
    """Background jobs that failed for good or are retrying, newest first, with their last error (cut, escaped)."""
    head = f"<h2>{_t(lang, 'errors')}</h2>"
    if not errors:
        return head + f"<p class=\"muted\">{_t(lang, 'errors.none')}</p>"
    rows = [[_v(e["kind"]), _t(lang, f"job.{e['status']}") if f"job.{e['status']}" in T else _v(e["status"]),
             _v(e["attempts"]), timestamp(e["updated_at"]), _v(e["error"])] for e in errors]
    return head + table([_t(lang, k) for k in ("h.job", "h.status", "h.attempts", "h.when", "h.error")], rows)


def index(conversations: list[dict[str, Any]], token: str | None, jobs: dict[str, int] | None = None,
          gens: dict[str, dict[str, Any] | None] | None = None, extraction: dict | None = None,
          embeddings: dict | None = None, lang: str = "ko", embed: bool = False,
          plugin: dict[str, Any] | None = None, version: str | None = None,
          errors: list[dict[str, Any]] | None = None) -> str:
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
    refresh = "" if embed else (
        '<form class="refresh" method="get" action="/inspector">'
        + (f'<input type="hidden" name="token" value="{_v(token)}">' if token else "")
        + f'<input type="hidden" name="lang" value="{_v(lang)}">'
        + f'<button type="submit">{_t(lang, "refresh")}</button></form>')
    ver = f"<span class=\"muted\">{_t(lang, 'version')} {_v(version)}</span>" if version else ""
    body = (f"<div class=\"top\"><h1>{_t(lang, 'title')}</h1>{ver}{refresh}{switch}</div>"
            f"<p class=\"muted\">{_t(lang, 'intro')} {queue}</p>"
            f"<p>{_t(lang, 'extractor')}: {_generation(gens.get('extraction'), lang)}<br>"
            f"{_t(lang, 'projection')}: {_generation(gens.get('embeddings'), lang)}"
            + (f"<br>{_t(lang, 'sm.generation')}: {_generation(gens['summaries'], lang)}" if gens.get("summaries") else "")
            + "</p>"
            + _plugin_status(plugin or {}, q, lang, embed) + listing
            + (_errors(errors, lang) if errors is not None else ""))
    return body if embed else page(_t(lang, "title"), body, lang)


def _plugin_status(plugin: dict[str, Any], q: str, lang: str, embed: bool) -> str:
    """Whether the plugin that synced last is this sidecar's build (ADR 0037); other builds seen lately (a
    tab or device not reloaded since the plugin was replaced) are named too."""
    want, seen = plugin.get("expected"), plugin.get("seen") or []
    if not want:
        return ""
    t = lambda k: _t(lang, k)
    path = "/v1/plugin/nmos-pocketrisu.js"
    get = (f"<span class=\"mono\">{path}</span>" if embed else f"<a href=\"{path}{q}\" download>{path}</a>")
    if not seen:
        return f"<p class=\"muted\">{t('plugin.none').format(want=want)}</p>"
    name = lambda s: s["build"] or t("plugin.no_build")
    at = lambda s: timestamp(datetime.fromisoformat(s["at"]))
    latest, others = seen[0], [s for s in seen[1:] if not s["matches"]]
    if latest["matches"]:
        out = f"<p>{t('plugin.ok').format(build=want, when=at(latest))}</p>"
    else:
        out = (f"<p class=\"warn\">{t('plugin.old').format(build=_v(name(latest)), want=want, when=at(latest))}"
               f" {t('plugin.get').format(link=get)}</p>")
    if latest["matches"] and others:
        builds = ", ".join(_v(name(s)) for s in others)
        out += f"<p class=\"warn\">{t('plugin.other').format(builds=builds, when=at(others[0]))}</p>"
    return out


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
    cn = cov.get("canon") or {}
    if cn.get("generation"):
        done = f"{cn.get('read', 0)}/{cn.get('wanted', 0)}"
        rows.append([t("canon_row"), _generation(cn["generation"], lang), _v(done),
                     _v(t("canon_detail").format(calls=cn.get("calls", 0), pending=cn.get("pending", 0),
                                                 failed=cn.get("failed", 0), unread=f"{cn.get('unread_chars', 0):,}"))])
    if emb.get("generation"):
        rows.append([t("vectors_row"), _generation(emb["generation"], lang), _percent(emb, "embedded", lang),
                     _v(f"{t('pending')} {emb.get('pending', 0)} · {t('failed')} {emb.get('failed', 0)} · "
                        f"{t('partially_embedded')} {emb.get('partial', 0)}")])
    if not rows:
        return f"<p class=\"muted\">{t('no_generation')}</p>"
    return table([t("h.projection"), t("h.generation"), t("h.coverage"), t("h.detail")], rows)


def _usage_section(usage: dict[str, Any], lang: str) -> str:
    """What the chat's model calls used, per generation (ADR 0051): only counts the provider reported."""
    t = lambda k: _t(lang, k)

    def cells(u: dict[str, Any]) -> list[str]:
        def tokens(k: str) -> str:  # a count no call reported is "—", never a reported 0
            n = u[f"{k}_reported"]
            if not n:
                return "—"
            return f"{u[k]:,}" + (f" <span class=\"muted\">({t('us.partial')})</span>" if n < u["calls"] else "")
        share = f"{u['reported']:,}/{u['calls']:,}" if u["calls"] else "—"
        if u["calls"] and not u["reported"]:
            share = f"<span class=\"chip\">{t('us.not_reported')}</span> {share}"
        if u["not_recorded"]:
            share += f" <span class=\"muted\">· {t('us.not_recorded').format(n=f'{u['not_recorded']:,}')}</span>"
        return [f"{u['calls']:,}", *(tokens(k) for k in ("input", "output", "cached")), share]

    rows = []
    for g in usage.get("generations") or []:
        kind = f"us.kind.{g['kind']}"
        name = _v(t(kind) if kind in T else g["kind"])
        if g["active"]:
            name += f" <span class=\"chip\">{t('us.active')}</span>"
        gen = (f"<span class=\"mono\" title=\"{_v(g['key'])}\">{_v(g['key'][:20])}</span> {_v(g['model'] or '')}"
               if g["key"] else f"<span class=\"muted\">{t('us.no_generation')}</span>")
        rows.append([name, gen, *cells(g)])
    head = f"<p class=\"muted\">{t('us.intro')}</p>"
    if not rows:
        return head + f"<p class=\"muted\">{t('us.none')}</p>"
    rows.append([f"<strong>{t('us.total')}</strong>", "", *cells(usage["total"])])
    return head + table([t("h.kind"), t("h.generation"), t("us.h.calls"), t("us.h.input"), t("us.h.output"),
                         t("us.h.cached"), t("us.h.reported")], rows)


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
    if a.get("canon"):  # before turn 0 (ADR 0047): the canon text it came from
        return f"<span class=\"chip\" title=\"{_v(a['canon'])}\">canon</span>"
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


def _cause(f: dict[str, Any], lang: str) -> str:
    """The cause the story states (extract-v13), and the event it names when one clearly does (ADR 0040)."""
    if not f.get("because"):
        return ""
    out = f"<br><span class=\"muted\">{_t(lang, 'because')}: {_v(f['because'])}"
    if e := f.get("cause_event"):
        when = e["turn"] if e.get("turn") is not None else e["position"]
        out += f" · {_t(lang, 'cause_event')} {_v(when)}: {_v(e['text'])}"
    return out + "</span>"


def pairs(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """How two characters stand, one entry per pair (PHASE-11 step 7, ADR 0038): the current relationship (one
    history for both directions), and each direction's current role (ADR 0059), feeling and speech level. Newest pair
    first."""
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for f in facts:
        if f["predicate"] not in STANDING or not f.get("object"):
            continue
        ends = []
        for role in ("subject", "object"):
            e = f.get(f"{role}_entity") or {}
            ends.append((e.get("id") or norm(f[role]), e.get("name") or f[role]))
        key = tuple(sorted(i for i, _ in ends))
        p = out.setdefault(key, {"ids": key, "names": {}, "relationship": [], "role": [], "feels": [], "speech": [],
                                    "position": -1})
        p["names"].update(dict(ends))
        p["position"] = max(p["position"], f["position"])
        p[{"relationship": "relationship", "role_toward": "role", "feels_toward": "feels",
           "addresses": "speech"}[f["predicate"]]].append(f)
    return sorted(out.values(), key=lambda p: p["position"], reverse=True)


def _pairs_table(entries: list[dict[str, Any]], lang: str) -> str:
    def said(f: dict[str, Any], directed: bool) -> str:
        who = f"{f['subject']} → {f['object']}: " if directed else ""
        text = _v(who + (f.get("value") or "")) + f" <span class=\"muted\">{_turn(f)}</span>"
        if f.get("polarity") == "negative":
            text += f" <span class=\"chip\">{_t(lang, 'negated')}</span>"
        if f.get("because"):
            text += f" <span class=\"muted\">· {_t(lang, 'because')}: {_v(f['because'])}</span>"
        for key, was in (("before", earlier(f)), ("first", first(f))):
            if was:
                text += f" <span class=\"muted\">· {_t(lang, key)}: {_v(was.get('value'))} ({_turn(was)})</span>"
        return text

    return table([_t(lang, k) for k in ("h.pair", "h.relationship", "h.role", "h.feelings", "h.speech")],
                 [[_v(" ↔ ".join(sorted(p["names"].values()))),
                   # a directed value ("엄마") says who is whose only with its direction; a symmetric one needs it
                   # only when both directions are current
                   "<br>".join(said(f, len(p["relationship"]) > 1 or not symmetric(f.get("value")))
                               for f in p["relationship"]),
                   "<br>".join(said(f, True) for f in p["role"]),
                   "<br>".join(said(f, True) for f in p["feels"]),
                   "<br>".join(said(f, True) for f in p["speech"])] for p in entries[:100]])


def _job_state(job: dict[str, Any], notes: list[str], lang: str) -> str:
    """A summary job still to finish, as a chip; a failed one adds its error to `notes`."""
    if job["status"] == "dead" and job.get("last_error"):
        notes.append(str(job["last_error"])[:200])
    return chip(lang, "sm", job["status"])


def _summary_state(x: dict[str, Any], lang: str) -> str:
    """Why a summary is or is not used (PHASE-12 step 6): held for a secret, not used in front of someone, or, without
    one, its job's state; with the secrets and the error that explain it."""
    notes = [f"{_t(lang, 'sm.secret')}: {s['text']}" for s in x["leaks"] + x["unlisted"]]
    job = x.get("job")  # the newest job of its window, or of the story that would replace it
    pending = " " + _job_state(job, notes, lang) if job and job["status"] != "done" else ""
    if x["summary"] is not None:
        out = (chip(lang, "sm", "held") if x["leaks"] else chip(lang, "sm", "unlisted") if x["unlisted"]
               else chip(lang, "sm", "current")) + pending
        if x["near"]:
            names = ", ".join(sorted({n for s in x["near"] for n in s.get("open") or []}))
            out += f" <span class=\"chip\">{_v(_t(lang, 'sm.near').format(names=names))}</span>"
    else:
        out = ((chip(lang, "sm", "changed") if x.get("changed") else "") + pending).strip() or chip(lang, "sm", "waiting")
    return out + "".join(f"<br><span class=\"muted\">{_v(n[:160])}</span>" for n in notes)


def _summaries_section(view: dict[str, Any], lang: str, gen: dict[str, Any] | None = None, on: bool = True,
                       narrator: str | None = None) -> str:
    """The story so far and each due scene with its summary and state (PHASE-12, ADR 0042), newest scene first."""
    t = lambda k: _t(lang, k)
    head = f"<p class=\"muted\">{t('sm.generation')}: {_generation(gen, lang)}</p>"
    head += "" if on else f"<p class=\"warn\">{_v(t('sm.off'))}</p>"
    head += f"<p class=\"muted\">{_v(t('sm.narrator'))}</p>" if narrator else ""
    if not view["scenes"]:
        return head + f"<p class=\"muted\">{t('sm.none').format(w=WINDOW, l=LAG)}</p>"
    out = head
    if story := view.get("story"):
        covers = t("sm.story_covers").format(n=len(story["members"]), m=view["due"])
        state = _summary_state({"summary": story, "job": view.get("story_job"), **view["story_why"]}, lang)
        behind = "" if view["story_current"] else f" <span class=\"muted\">{_v(t('sm.behind'))}</span>"
        out += f"<p><b>{t('story')}</b> <span class=\"muted\">({covers})</span> {state}{behind}<br>{_v(story['text'])}</p>"
    else:
        job, notes = view.get("story_job"), []
        state = f" {_job_state(job, notes, lang)}" if job and job["status"] != "done" else ""
        state += "".join(f"<br><span class=\"muted\">{_v(n[:160])}</span>" for n in notes)
        out += (f"<p><b>{t('story')}</b> <span class=\"muted\">"
                f"{_v(t('sm.story_wait').format(n=view['done'], m=view['due']))}</span>{state}</p>")
    return out + table([t(k) for k in ("h.turns", "h.status", "h.summary")],
                       [[_v(f"{x['window'].first_turn}–{x['window'].last_turn}"), _summary_state(x, lang),
                         _v((x["summary"] or {}).get("text") or "")] for x in reversed(view["scenes"])][:200])


def _facts_table(facts: list[dict[str, Any]], active: str | None, lang: str) -> str:
    t = lambda k: _t(lang, k)
    # A fact whose turn the active generation has not compiled yet comes from an older one (ADR 0014).
    older = f" <span class=\"chip\">{t('older_gen')}</span>"
    return table(
        [t(k) for k in ("h.subject", "h.predicate", "h.object", "h.with", "h.knowledge", "h.turn", "h.versions")],
        [[_v(f["subject"]), chip(lang, "p", f["predicate"]), _v(f.get("object") or f.get("value")) + _cause(f, lang)
          + ("" if f.get("owner") else _act("fact_retract", f["id"]) + "".join(_act("fact_correct", f["id"], x) for x in _corrections(f)))
          + (_act("fact_lock", f["id"]) if (f.get("canon") or f.get("owner")) and not f.get("locked") else ""),
          _with(f, lang),
          _knowledge(f, lang),
          _turn(f)
          # a canon fact carries its canon generation, whose reads the Canon section covers (ADR 0047)
          + (older if active and f.get("generation") not in (None, active) and not f.get("owner")
             and not f.get("canon") else "")
          + (f" {chip(lang, 'or', 'corrected')}" if f.get("owner") else "")
          + (f" {chip(lang, 'or', 'locked')}" + _act("undo", f["locked"]) if f.get("locked") else "")
          + (f" <span class=\"chip\">{_v(t('held_off').format(n=f['held_off']))}</span>" if f.get("held_off") else "")
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
    """Threads with their status and what closed them (PHASE-7, ADR 0019; PHASE-11, ADR 0039), newest first."""
    def closed(t: dict[str, Any]) -> str:
        c = t.get("closed_by")
        if c and c.get("owner"):
            return f"<span title=\"{_v(c.get('evidence') or '')}\">{_turn(c)} · {chip(lang, 'or', 'closed')}</span>"
        return f"{_turn(c)} · {_v(fact_line_text(c))}" if c else ""

    counts: dict[str, int] = {}
    for th in threads:
        if th["status"] == "open":
            counts[th.get("kind", "promise")] = counts.get(th.get("kind", "promise"), 0) + 1
    summary = (f"<p class=\"muted\">{_t(lang, 't.open')}: "
               + " · ".join(f"{_t(lang, f'k.{k}')} {n}" for k, n in sorted(counts.items(), key=lambda kv: -kv[1]))
               + "</p>") if counts else ""
    return summary + table([_t(lang, k) for k in ("h.kind", "h.by", "h.to", "h.promise", "h.turn", "h.status", "h.closed",
                                                  "h.restated")],
                 [[chip(lang, "k", t.get("kind", "promise")), _v(t["by"]), _v(t.get("to") or ""), _v(t.get("text")),
                   _turn(t), chip(lang, "t", t["status"])
                   + (_close(t) if t["status"] == "open"
                      else _act("thread_reopen", t["id"]) if not (t.get("closed_by") or {}).get("owner") else ""),
                   closed(t), _v(", ".join(str(r["turn"] if r.get("turn") is not None else r["position"])
                                          for r in t.get("restated") or []))]
                  for t in threads[:100]])


def _unmatched_table(unmatched: list[dict[str, Any]], lang: str) -> str:
    return table([_t(lang, k) for k in ("h.subject", "h.predicate", "h.object", "h.turn")],
                 [[_v(u["subject"]), chip(lang, "p", u["predicate"])
                   + (f" <span class=\"chip\">{_t(lang, 'negated')}</span>" if u.get("polarity") == "negative" else ""),
                   _v(u.get("value")), _turn(u)] for u in unmatched[:100]])


def _secret_status(s: dict[str, Any], lang: str) -> str:
    """Per character it is kept from: still kept, or found out (turn; the evidence in the tooltip)."""
    out = []
    for name in s["kept_from"]:
        ended = s["ended"].get(name)
        if ended is None:
            out.append(f"{_v(name)}: <span class=\"warn\">{_v(_t(lang, 'sec.open'))}</span>"
                       + _act("secret_found_out", s["id"], name))
        else:
            turn = ended["turn"] if ended.get("turn") is not None else ended.get("position")
            owner = f" {chip(lang, 'or', 'marked')}" if ended.get("owner") else _act("secret_keep", s["id"], name)
            out.append(f"<span title=\"{_v(ended.get('evidence') or '')}\">{_v(name)}: "
                       f"{_v(_t(lang, 'sec.ended').format(turn=turn))}</span>{owner}")
    return "<br>".join(out)


STALE_TURNS = 30  # an open thread not restated for this long is suggested for closing (PHASE-13 Q6)


def _act(kind: str, item: Any, extra: str | None = None) -> str:
    """Where the panel puts a repair button (ADR 0044); nothing shows in a browser tab (H15)."""
    value = f"{kind}:{item}" + (f":{_enc(extra)}" if extra else "")
    return f"<span class=\"rp\" data-repair=\"{_v(value)}\"></span>"


def _undo(rep: dict[str, Any]) -> str:
    """An undo; a name split's is marked so the panel previews it like a join (PHASE-20 Q2)."""
    return _act("undo", rep["id"], "name_split" if rep.get("kind") == "name_split" else None)


def _close(th: dict[str, Any]) -> str:
    """A close button with the outcomes of the thread's kind, its default first (ADR 0044 item 3)."""
    first = default_outcome(th["kind"])
    return _act("thread_close", th["id"], ",".join([first] + [o for o in outcomes(th["kind"]) if o != first]))


def _who_to(t: dict[str, Any]) -> str:
    """A thread's maker, and its counterpart when it has one (a promise, a debt)."""
    return f"{t.get('by')} → {t['to']}" if t.get("to") else f"{t.get('by')}"


def _enc(text: str) -> str:
    """Percent-encode a mark's extra (a name can be any text); the panel decodes it as data only."""
    return "".join(c if c.isascii() and (c.isalnum() or c in "._~-,") else "".join(f"%{b:02X}" for b in c.encode())
                   for c in text)


def _corrections(f: dict[str, Any]) -> list[str]:
    """The fields a correction of this fact can set, as the API checks them (ADR 0044 item 8): its object when its
    predicate has one, its value when it needs or has one (a relationship: both)."""
    pred = REGISTRY.get(f["predicate"])
    has_object = pred.object_types is not None if pred is not None else bool(f.get("object"))
    has_value = (pred.needs_value if pred is not None else False) or bool(f.get("value"))
    return (["object"] if has_object else []) + (["value"] if has_value else [])


def _attention(view: dict[str, Any], repairs: list[dict[str, Any]], last_turn: int | None, lang: str) -> list[list[str]]:
    """What needs a look (PHASE-13 Q6), each with its repair where one fits: from what NMOS already detects."""
    rows: list[list[str]] = []
    if last_turn is not None:
        for th in view.get("threads", []):
            seen = [th.get("turn")] + [r.get("turn") for r in th.get("restated") or []]
            latest = max((x for x in seen if x is not None), default=None)
            if th["status"] == "open" and latest is not None and latest < last_turn - STALE_TURNS:
                rows.append([_v(_t(lang, "at.stale").format(n=STALE_TURNS)),
                             _v(_who_to(th) + f": {th.get('text') or ''}"), _v(latest),
                             _close(th)])
    for u in view.get("unmatched", []):
        rows.append([_v(_t(lang, "at.unmatched")), _v(fact_line_text(u)), _turn(u), ""])
    for f in view.get("dropped", []):  # PHASE-22 Q6
        rows.append([_v(_t(lang, "at.dropped")), _v(fact_line_text(f)), _v(f.get("turn")), _act("fact_restore", f["id"])])
    ends = view.get("endings") or {}  # PHASE-28 Q7: role endings, applied or held, each with the owner's one action
    for f in ends.get("automatic", []):
        rows.append([_v(_t(lang, "at.role_auto")), _v(fact_line_text(f)) + _quote(f.get("quote")), _v(f.get("turn")),
                     _act("fact_retract", f["id"])])
    for f in ends.get("held", []):
        why = ((f.get("reason") or "").split(": ", 1) + [""])[1]
        rows.append([_v(_t(lang, "at.role_held").format(why=why)), _v(fact_line_text(f)) + _quote(f.get("evidence")),
                     _v(f.get("turn")), _act("fact_restore", f["id"])])
    for f in ends.get("aliases_held", []):
        why = ((f.get("reason") or "").split(": ", 1) + [""])[1]
        rows.append([_v(_t(lang, "at.alias_held").format(why=why)), _v(f"{f.get('subject')} = {f.get('value')}")
                     + _quote(f.get("evidence")), _v(f.get("turn")),
                     _act("alias_join", f["id"], f"{f.get('subject')}|{f.get('value')}")])
    owned = {f["id"]: f["repair"] for f in view.get("facts", []) if f.get("owner")}  # the owner's corrections
    for c in view.get("conflicts", []):
        if c.get("kind") == "canon":  # keep canon's (a lock) or the story's (canon's statement retracted), or leave it
            rows.append([_v(_t(lang, "at.canon")),
                         _v(f"{_t(lang, 'at.canon_says')}: {fact_line_text(c['against'])} · "
                            f"{_t(lang, 'at.story_says')}: {c['text']}"), _v(c.get("turn")),
                         _act("fact_lock", c["against"]["id"]) + _act("fact_retract", c["against"]["id"])])
            continue
        if c.get("kind") == "locked":  # the owner chose: the Conflicts section lists it
            continue
        act = _act("undo", owned[c["fact"]]) if c["fact"] in owned else _act("fact_retract", c["fact"])
        rows.append([_v(_t(lang, "at.disputed")), _v(c["text"]), _v(c.get("turn")), act])
    for rep in repairs:
        if rep.get("removed_at"):
            continue
        if rep.get("via"):
            rows.append([_v(_t(lang, "at.split")), _repair_target(rep), "", _undo(rep)])
        elif not rep.get("applied"):
            rows.append([_v(_t(lang, "at.repair")), _repair_target(rep), "", _undo(rep)])
    for a in view.get("ambiguous", []):
        rows.append([_v(_t(lang, "at.ambiguous")), _v(f"{a['name']}: " + ", ".join(a.get("candidates") or [])), "", ""])
    return rows


def _quote(text: str | None) -> str:
    return f"<br><span class=\"muted\">“{_v(text)}”</span>" if text else ""


def _repair_target(rep: dict[str, Any]) -> str:
    t = rep["target"] or {}
    if rep["kind"] == "name_split":
        return _v(f"{t.get('name')} ≠ {t.get('other')}")
    if rep["kind"].startswith("thread_"):
        text = _who_to(t) + f": {t.get('text')}"
    else:
        text = t.get("text") or ""
    return f"<span class=\"muted\">{_v(t.get('turn'))}</span> {_v(text)}"


def _repair_value(rep: dict[str, Any], lang: str) -> str:
    v = rep.get("value") or {}
    parts = []
    if v.get("outcome"):
        parts.append(chip(lang, "t", v["outcome"]))
    for k in ("object", "value"):
        if v.get(k):
            parts.append(f"→ {_v(v[k])}")
    if v.get("character"):
        parts.append(_v(v["character"]))
    if v.get("turn") is not None:
        parts.append(f"<span class=\"muted\">{_v(_t(lang, 'h.turn'))} {_v(v['turn'])}</span>")
    if rep.get("note"):
        parts.append(f"<span class=\"muted\">{_v(rep['note'])}</span>")
    return " ".join(parts)


def _repairs_table(repairs: list[dict[str, Any]], lang: str) -> str:
    """The owner's repairs of the chat (ADR 0044), newest first: in force (applied, or matching nothing now) or taken
    back."""
    def state(rep: dict[str, Any]) -> str:
        if rep.get("removed_at"):
            return chip(lang, "rs", "removed")
        undo = _undo(rep)
        if rep.get("via"):
            return f"<span class=\"warn\">{_v(_t(lang, 'rs.via').format(names=', '.join(rep['via'])))}</span>" + undo
        return (chip(lang, "rs", "applied") if rep.get("applied")
                else f"<span class=\"warn\">{_v(_t(lang, 'rs.unmatched'))}</span>") + undo

    return (table([_t(lang, k) for k in ("h.repair", "h.target", "h.value", "h.made", "h.status")],
                  [[chip(lang, "rk", rep["kind"]), _repair_target(rep), _repair_value(rep, lang), timestamp(rep["created_at"]),
                    state(rep)] for rep in repairs[:200]])
            + f"<p class=\"muted\">{_v(_t(lang, 'or.note'))}</p>")


def _canon_table(rows: list[dict[str, Any]], history: dict[str, dict[str, Any]], held: dict[str, dict[str, Any]],
                 lang: str, read: dict[str, dict[str, Any]] | None = None) -> str:
    """The chat's canon in force (ADR 0045): what each text is, how long, since when and in how many versions,
    whether a request's prompt held it (the host sends what it activates; NMOS does not repeat it, D3), and what the
    canon generation read of it (ADR 0047: a lorebook entry only once a prompt held it)."""
    def facts(key: str) -> str:
        if read is None:
            return ""
        x = read.get(key)
        if x is None:
            return f"<span class=\"muted\">{_v(_t(lang, 'cn.unread' if key.startswith('lore:') else 'cn.none'))}</span>"
        if x["job"] in ("queued", "running"):
            return _v(_t(lang, "cn.reading"))
        if x["job"] == "dead":
            return f"<span class=\"warn\">{_v(_t(lang, 'cn.failed'))}</span>"
        return _v(_t(lang, "cn.read").format(n=x["calls"])) if x["calls"] else ""

    def what(r: dict[str, Any]) -> str:
        m = r["metadata"] or {}
        bits = [m.get("scope"), m.get("mode"), "always" if m.get("always_active") else None,
                _t(lang, "cn.keys").format(n=len(m["keys"])) if m.get("keys") else None]
        return _v(" · ".join(b for b in bits if b))

    def seen(key: str) -> str:
        h = held.get(key)
        return (_v(_t(lang, "cn.held").format(n=h["requests"])) + " " + timestamp(h["last_at"])) if h \
            else f"<span class=\"muted\">{_v(_t(lang, 'cn.never'))}</span>"

    def text(r: dict[str, Any]) -> str:
        c = r.get("content")
        return _v(c[:120] + ("…" if len(c) > 120 else "")) if c is not None \
            else f"<span class=\"warn\">{_v(_t(lang, 'cn.missing'))}</span>"

    return (table([_t(lang, k) for k in ("h.source", "h.key", "h.what", "h.chars", "h.versions", "h.since", "h.held",
                                         "h.read", "h.text")],
                  [[chip(lang, "cn", r["key"].split(":")[0]), _v(r["key"]), what(r),
                    _v(len(r["content"]) if r.get("content") is not None else "—"),
                    _v((history.get(r["key"]) or {}).get("versions", 1)),
                    timestamp((history.get(r["key"]) or {}).get("since")), seen(r["key"]), facts(r["key"]), text(r)]
                   for r in rows[:500]])
            + f"<p class=\"muted\">{_v(_t(lang, 'cn.about'))}</p>")


def _secrets_table(secrets: list[dict[str, Any]], lang: str) -> str:
    """A chat's secrets, newest first (PHASE-10 step 6, ADR 0033): holders, whom it is kept from, the turn that
    made it, and per character whether and when they found out."""
    return (table([_t(lang, k) for k in ("h.secret", "h.holders", "h.kept_from", "h.turn", "h.status")],
                  [[_v(s["text"]), _v(", ".join(s["holders"])), _v(", ".join(s["kept_from"])), _turn(s),
                    _secret_status(s, lang)] for s in secrets[:100]])
            + f"<p class=\"muted\">{_v(_t(lang, 'sec.note'))}</p>")


def _unrevealed_table(unrevealed: list[dict[str, Any]], lang: str) -> str:
    return (table([_t(lang, k) for k in ("h.who", "h.listed", "h.turn", "h.evidence")],
                  [[_v(u["subject"]), _v(u.get("value")), _turn(u), _v(u.get("evidence") or "")]
                   for u in unrevealed[:100]])
            + f"<p class=\"muted\">{_v(_t(lang, 'unrevealed_note'))}</p>")


def _conflicts_table(conflicts: list[dict[str, Any]], lang: str) -> str:
    """The story against itself (disputed), against canon (canon, ADR 0047), and against the owner's lock (locked:
    the locked fact stays current, the statement is held off)."""
    return table([_t(lang, k) for k in ("h.kind", "h.fact", "h.turn", "h.against", "h.turn")],
                 [[chip(lang, "cf", c.get("kind") or "disputed"), _v(c["text"]), _turn(c),
                   _v(fact_line_text(c["against"])), _turn(c["against"])]
                  for c in conflicts[:100]])


def _claims_table(claims: list[dict[str, Any]], lang: str) -> str:
    return table([_t(lang, k) for k in ("h.by", "h.subject", "h.predicate", "h.object", "h.turn")],
                 [[_v(c.get("asserted_by")), _v(c["subject"]), chip(lang, "p", c["predicate"]),
                   _v(c.get("object") or c.get("value")) + _cause(c, lang), _turn(c)] for c in claims[:100]])


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
           packet: dict[str, Any] | None = None, secrets: list[dict[str, Any]] | None = None,
           unrevealed: list[dict[str, Any]] | None = None, standing: list[dict[str, Any]] | None = None,
           summaries: dict[str, Any] | None = None, repairs: list[dict[str, Any]] | None = None,
           last_turn: int | None = None, canon_rows: list[dict[str, Any]] | None = None,
           canon_history: dict[str, dict[str, Any]] | None = None,
           canon_held: dict[str, dict[str, Any]] | None = None, canon_read: dict[str, dict[str, Any]] | None = None,
           canon_facts: int = 0, dropped: list[dict[str, Any]] | None = None,
           endings: dict[str, list[dict[str, Any]]] | None = None) -> str:
    t = lambda k: _t(lang, k)
    q = query(token, lang)
    name, path = label(conv), f"/inspector/c/{conv['id']}"
    head = (f"<div class=\"top\"><p><a href=\"/inspector{q}\">{t('back')}</a></p>"
            f"{'' if embed else _lang_switch(path, token, lang)}</div>"
            f"<h1>{_v(name)}</h1>" + _meta(conv, lang) + _who(conv["id"], entities or [], None, q, lang))
    active = (((coverage or {}).get("extraction") or {}).get("generation") or {}).get("key")
    # What needs a look comes first; logs of the machinery start folded.
    queue = _attention({"threads": threads or [], "unmatched": unmatched or [], "conflicts": conflicts or [],
                        "ambiguous": ambiguous or [], "dropped": dropped or [], "endings": endings or {}},
                       repairs or [], last_turn, lang)
    parts: list[Section] = [
        ("attention", t("attention"), len(queue),
         table([t(k) for k in ("h.issue", "h.text", "h.turn", "h.repair")], queue) + f"<p class=\"muted\">{t('at.note')}</p>"
         if queue else f"<p class=\"muted\">{t('at.none')}</p>", bool(queue)),
        ("state", t("state"), None, table([t("h.key"), t("h.value"), t("h.as_of"), t("h.rule")],
                                          [[_v(s["key"]), _v(s["value"]), _v(s["turn"]), _v(s["rule_id"])]
                                           for s in state])
         if state else f"<p class=\"muted\">{t('no_state')}</p>{_no_state_example(lang)}", True),
        ("coverage", t("coverage"), None, _coverage_section(coverage or {}, lang), True)]
    if (coverage or {}).get("usage") is not None:
        parts.append(("usage", t("us.title"), None, _usage_section(coverage["usage"], lang), False))
    if conflicts:
        parts.append(("conflicts", t("conflicts"), len(conflicts), _conflicts_table(conflicts, lang), True))
    if threads:
        parts.append(("threads", t("threads"), len(threads), _threads_table(threads, lang), True))
    if unmatched:
        parts.append(("unmatched", t("unmatched"), len(unmatched), _unmatched_table(unmatched, lang), True))
    if secrets:
        parts.append(("secrets", t("secrets"), len(secrets), _secrets_table(secrets, lang), True))
    if unrevealed:
        parts.append(("unrevealed", t("unrevealed"), len(unrevealed), _unrevealed_table(unrevealed, lang), True))
    if both := pairs(facts if standing is None else standing):  # every pair, not only those in the capped facts
        parts.append(("pairs", t("pairs"), len(both), _pairs_table(both, lang), True))
    if summaries is not None:
        parts.append(("summaries", t("summaries"), summaries["done"], _summaries_section(summaries, lang, summaries.get("generation"), summaries.get("on", True),
                                                        conv.get("memory_narrator")), False))
    if repairs:
        live = sum(1 for rep in repairs if not rep.get("removed_at"))
        parts.append(("repairs", t("repairs"), live, _repairs_table(repairs, lang), True))
    if canon_rows:
        parts.append(("canon", t("canon"), len(canon_rows),
                      _canon_table(canon_rows, canon_history or {}, canon_held or {}, lang, canon_read)
                      + (f"<p class=\"muted\">{_v(t('cn.facts').format(n=canon_facts))}</p>" if canon_read is not None
                         else ""), False))
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
              _v(", ".join("canon" if a.get("canon") else str(a["turn"]) for a in e["aliases"])), _owner_links(e)] for e in entities[:200]]), True))
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
          _v(r["selected"]), _v(r["excluded"]), _v(_facts_kept(r["latency_ms"] or {}, lang)), _placed(r, lang),
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
        kind = chip(lang, "lk", e["kind"]) + (f" {chip(lang, 'lk', 'cast')}" if e.get("section") == "cast" else "")
        rows.append([kind, _v(e.get("turn")), _v(e.get("text")), outcome, _v(e.get("tok")), echo])
    timings, options = trace.get("latency_ms") or {}, trace.get("recall_options") or {}
    scene = ""
    if "scene_cast" in timings:  # recorded since packet-v3 (ADR 0034) and the memory mode (ADR 0035)
        mode = [t("mode.strict")] if options.get("strict") else []
        mode += [t("mode.narrator").format(n=options["narrator"])] if options.get("narrator") else []
        if timings.get("memory_mode_withheld"):
            mode.append(t("mode.withheld").format(n=timings["memory_mode_withheld"]))
        scene = (f"<p class=\"muted\">{_v(t('scene').format(cast=', '.join(timings['scene_cast']) or '—',
                                                          mode=' · '.join(mode) or t('mode.default')))}</p>")
    return (f"<p class=\"muted\">{intro}</p>" + scene
            + table([t(k) for k in ("h.kind", "h.turn", "h.text", "h.outcome", "h.tokens", "h.echo")], rows)
            + f"<p class=\"muted\">{_v(t('packet_echo'))}</p>")


def _owner_links(entity: dict[str, Any]) -> str:
    """The owner's links that joined this entity's names (ADR 0025), as "name = same as"."""
    return _v(", ".join(f"{link['name']} = {link['same_as']}" for link in entity.get("links") or []))


def _cast_state(view: dict[str, Any], entity_id: str, r: Any, lang: str) -> str:
    """A character's state block (PHASE-12 step 6): the lines <Cast> gives them, by the same rule (ADR 0043), and
    their open goals, newest first."""
    persona = scene.key(r, scene.PERSONA)
    own = [f for f in view["facts"] if scene.key(r, f["subject"]) == entity_id]
    rows = [[chip(lang, "cs", f["predicate"]), _v(fact_line_text(f)), _turn(f), _knowledge(f, lang)]
            for f in cast_facts(own, lambda f: scene.key(r, f["object"]) == persona)]
    goals = sorted((th for th in view.get("threads", []) if th.get("kind") == "goal" and th["status"] == "open"
                    and scene.key(r, th["by"]) == entity_id), key=lambda th: th["position"], reverse=True)
    rows += [[chip(lang, "cs", "goal"), _v(th.get("text")), _turn(th), ""] for th in goals[:20]]
    if not rows:
        return f"<p class=\"muted\">{_v(_t(lang, 'cs.empty'))}</p>"
    return (table([_t(lang, k) for k in ("h.aspect", "h.fact", "h.turn", "h.knowledge")], rows)
            + f"<p class=\"muted\">{_v(_t(lang, 'cs.note').format(n=CAST_GOALS))}</p>")


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
    found = [s for s in view.get("secrets", []) if among(list(s["ended"]))]
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
    if (r := view.get("resolution")) is not None and entity["type"] == "character" \
            and entity_id != scene.key(r, scene.PERSONA):
        parts.append(("now", _v(t("now")), None, _cast_state(view, entity_id, r, lang), True))
    if conflicts:
        parts.append(("conflicts", t("conflicts"), len(conflicts), _conflicts_table(conflicts, lang), True))
    if threads:
        parts.append(("threads", t("threads"), len(threads), _threads_table(threads, lang), True))
    if mine_pairs := [p for p in pairs(facts) if entity_id in p["ids"]]:
        parts.append(("pairs", t("pairs"), len(mine_pairs), _pairs_table(mine_pairs, lang), True))
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
    if found:
        def when(s: dict[str, Any]) -> dict[str, Any]:
            return next(e for n, e in s["ended"].items() if norm(n) in names)
        parts.append(("found_out", t("found_out"), len(found), table(
            [t(k) for k in ("h.secret", "h.holders", "h.turn", "h.found", "h.evidence")],
            [[_v(s["text"]), _v(", ".join(s["holders"])), _turn(s), _turn(when(s)), _v(when(s).get("evidence") or "")]
             for s in found[:100]]), True))
    if claims:
        parts.append(("claims", t("who_claims"), len(claims), _claims_table(claims, lang), True))
    if other:
        parts.append(("other", t("who_other"), len(other), _other_table(other, lang), False))
    body = head + sections(lang, parts)
    if len(parts) == 1:
        body += f"<p class=\"muted\">{t('who.empty')}</p>"
    return body if embed else page(f"NMOS · {title}", body, lang)
