"""PHASE-60 S6 (ADR 0085 items 4, 5): the packet-v20 lines of what a chat's carry link carries.

`continue`: carried facts and open threads are offered as the target's own, marked source="carried" in place of a turn,
their ledger entries naming the link and the source assertion; they never change the target's scene cast, <Cast>,
gone pins, return-gap marks or settled lines; the earlier chat's story so far opens <Story>. `regression`: what the named
characters remember of the previous timeline, only inside a <Regression> group, private, under the memory modes.
Stub extractor only; the worlds of `test_phase60_carry_fold`; synthetic
names only."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

import psycopg

from conftest import make_client
from nmos_sidecar import carry, retrieval
from nmos_sidecar.packet import (CARRIED_MARK, CARRIED_NOTE, PRIVATE_NOTE, REGRESSION_MARK, REGRESSION_NOTE, STORY_SHARE,
                                 Compiled, Excerpt, Line, compile_lines)
from nmos_sidecar.retrieval import REGRESSION_MAX, Gathered, RecallOptions
from test_phase60_carry_fold import CANON_ON, PROMISE, _connect, _head, _key, _world

BUDGET = 3000


def _link(conn: psycopg.Connection, tgt: UUID, src: UUID, mode: str = "continue",
          names: list[str] | None = None) -> carry.Carried:
    carry.link(conn, tgt, src, mode, names or [], carry.Keys(extractor=_key(conn)))
    found = carry.in_force(conn, tgt)
    assert found is not None
    return carry.target_rows(found)


def _packet(conn: psycopg.Connection, tgt: UUID, query: str, carried: carry.Carried | None,
            policy: str = "packet-v20", **opts: Any) -> tuple[Compiled, Gathered]:
    options = RecallOptions(policy=policy, extractor_key=_key(conn), **opts)
    g = retrieval.gather(conn, _head(conn, tgt), query, "", set(), options, carried=carried)
    return retrieval.compile_gathered(g, BUDGET, policy), g


def _section(text: str, tag: str) -> str:
    found = re.search(rf"  <{tag}>\n.*?\n  </{tag}>", text, re.DOTALL)
    return found.group(0) if found else ""


def _carried_entries(ledger: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [e for e in ledger if (e.get("ref") or {}).get("carried")]


# --- continue: the lines ------------------------------------------------------------------------------------------

def test_continue_facts_and_threads_are_marked_carried_with_their_provenance(migrated: str) -> None:
    with make_client(migrated, **CANON_ON) as c:
        src, _, tgt = _world(c, migrated)
        with _connect(migrated) as conn:
            carried = _link(conn, tgt, src)
            out, _ = _packet(conn, tgt, "세라는 카이토와 어떤 사이야?", carried)
            plain, _ = _packet(conn, tgt, "세라는 카이토와 어떤 사이야?", None)
    text = out.text
    assert '<Fact kind="relationship" source="carried">세라 relationship 카이토: 오랜 동료</Fact>' in text
    assert f'<Thread kind="promise" by="세라" to="카이토" source="carried">{PROMISE}</Thread>' in text
    assert 'turn="-1"' not in text
    assert CARRIED_NOTE in text and CARRIED_MARK not in plain.text and CARRIED_NOTE not in plain.text
    # The target's story says where 세라 is now: the carried lighthouse is history, not the place.
    assert "세라 located in 항구" in text and "세라 located in 등대" not in text
    # Each carried line's ledger entry names the link and the source assertion it was read from (ADR 0027).
    entries = _carried_entries(out.ledger)
    assert {e["kind"] for e in entries} == {"fact", "thread"}
    by_text = {e["text"]: e for e in entries}
    rel = next(e for t, e in by_text.items() if "오랜 동료" in t)
    assert rel["placed"] and rel["ref"]["carried"] == carried.link and rel["ref"]["assertion"] < 0
    for e in entries:
        assert isinstance(e["ref"]["source_assertion"], int) and e["ref"]["source_assertion"] > 0
        assert e["ref"]["carried"] == carried.link


def test_a_version_a_standing_fact_replaced_is_named_as_the_earlier_chats() -> None:
    """A standing fact that replaced a carried version names it as an earlier chat's, never as turn -1."""
    from nmos_sidecar.facts import _entry, fact_line
    base = {"predicate": "relationship", "subject": "세라", "subject_type": "character", "object": "카이토",
            "object_type": "character", "polarity": "positive"}
    old = {**base, "position": carry.CARRY_BASE, "turn": -1, "value": "오랜 동료", "carried": "L"}
    new = {**base, "position": 5, "turn": 2, "value": "옛 동료"}
    history = [_entry(old, {}), _entry(new, {id(new): "current"})]
    assert history[0]["carried"] == "L" and "carried" not in history[1]
    line = fact_line({**new, "history": history}, before=True)
    assert line == ('    <Fact kind="relationship" turn="2">세라 relationship 카이토: 옛 동료; before, in an earlier chat: '
                    '세라 relationship 카이토: 오랜 동료</Fact>')


# --- continue: what a link never changes --------------------------------------------------------------------------

PERSONA_SPELLINGS = ("{{user}}", "유찬")  # the target's persona, displayed by the first spelling its resolution has


def _scene_parts(out: Compiled, g: Gathered) -> dict[str, Any]:
    return {"cast": _section(out.text, "Cast"), "scene": sorted(g.cast),
            "names": sorted(n for n in g.cast.values() if n not in PERSONA_SPELLINGS), "gone": [x.xml for x in g.gone],
            "marks": dict(g.cast_marks), "settled": [x.xml for x in g.settled],
            "gone_marked": out.text.count('gone="true"'), "back_after": out.text.count("back_after="),
            "status_threads": out.text.count('<Thread status="')}


def _without_aliases(link: dict[str, Any]) -> carry.Carried:
    """The link's rows less its aliases: a carried alias joins the target's names by design (ADR 0085 item 3), which
    regroups the target's own lines; what is compared here is what the carried rows themselves do."""
    return carry.target_rows({**link, "snapshot": {**link["snapshot"], "aliases": []}})


def test_a_continue_link_changes_no_scene_cast_gone_pin_return_mark_or_settled_line(migrated: str) -> None:
    query = "세라는 지금 어디 있어?"
    with make_client(migrated, **CANON_ON) as c:
        src, _, tgt = _world(c, migrated, target_turns=4)  # turn 3 keeps the carried promise
        with _connect(migrated) as conn:
            before = _scene_parts(*_packet(conn, tgt, query, None))
            _link(conn, tgt, src)
            carried = _without_aliases(carry.in_force(conn, tgt))
            out, g = _packet(conn, tgt, query, carried)
            view = retrieval.memory_view(conn, _head(conn, tgt), _key(conn), carried=carried)
    # present: a carried death (유나: a gone pin needs no mention) and a carried promise the target's story kept
    assert [(t["status"], t.get("carried")) for t in view["threads"] if t.get("carried")] == [("kept", carried.link)]
    assert any(f.get("carried") and f["value"] == "사망" for f in view["facts"])
    assert _scene_parts(out, g) == before
    assert before["names"] == ["세라"] and "<Character name=\"세라\">" in before["cast"]


def test_a_carried_status_of_a_character_the_message_names_is_a_fact_never_a_cast_line(migrated: str) -> None:
    with make_client(migrated, **CANON_ON) as c:
        src, _, tgt = _world(c, migrated)
        with _connect(migrated) as conn:
            carried = _link(conn, tgt, src)
            out, g = _packet(conn, tgt, "유나는 지금 어디 있어?", carried)
    assert "유나" in g.cast.values()  # a name the message says counts, whatever the rows are
    assert '<Fact kind="has_status" source="carried">유나 has status: 사망</Fact>' in _section(out.text, "Facts")
    assert "사망" not in _section(out.text, "Cast") and 'gone="true"' not in out.text


# --- continue: the story so far -----------------------------------------------------------------------------------

EARLIER = "세라는 <등대>에서 카이토와 열쇠를 찾았다 & 약속했다."


def _with_story(link: dict[str, Any], text: str = EARLIER) -> carry.Carried:
    story = {"text": text, "first_turn": 0, "last_turn": 4,
             "from": {"conversation": str(link["source_conversation_id"]), "summary": "s-earlier", "generation": "g"}}
    return carry.target_rows({**link, "snapshot": {**link["snapshot"], "story": story}})


def test_the_earlier_chats_story_so_far_is_a_summary_first_in_story(migrated: str) -> None:
    with make_client(migrated, **CANON_ON) as c:
        src, _, tgt = _world(c, migrated)
        with _connect(migrated) as conn:
            _link(conn, tgt, src)
            carried = _with_story(carry.in_force(conn, tgt))
            out, g = _packet(conn, tgt, "오늘은 날씨가 맑네.", carried, summarize_key="summarize-test")
            narrated, _ = _packet(conn, tgt, "오늘은 날씨가 맑네.", carried, summarize_key="summarize-test",
                                  narrator="세라")
            older, _ = _packet(conn, tgt, "오늘은 날씨가 맑네.", carried, "packet-v19", summarize_key="summarize-test")
            off, _ = _packet(conn, tgt, "오늘은 날씨가 맑네.", carried)  # no summaries configured: no <Story>
    line = '    <Summary scope="earlier chat">세라는 &lt;등대&gt;에서 카이토와 열쇠를 찾았다 &amp; 약속했다.</Summary>'
    assert '  <Story>\n' + line + '\n' in out.text
    entry = next(e for e in out.ledger if e["kind"] == "summary")
    assert entry["ref"] == {"carried": carried.link, "summary": "s-earlier"} and entry["placed"]
    assert entry["turn"] is None and entry["text"] == f"earlier chat: {EARLIER}"
    assert [x.content for x in g.story] == [EARLIER]
    for text in (narrated.text, older.text, off.text):
        assert 'scope="earlier chat"' not in text


def test_the_earlier_chats_story_is_emitted_first_and_left_out_first() -> None:
    own = Line("summary", '    <Summary kind="story" turns="0–7">이 채팅의 지금까지.</Summary>', {"summary": "own"}, 7,
               "story 0–7: 이 채팅의 지금까지.", "이 채팅의 지금까지.")
    earlier = Line("summary", '    <Summary scope="earlier chat">앞선 채팅의 이야기.</Summary>',
                   {"carried": "L", "summary": "s"}, None, "earlier chat: 앞선 채팅의 이야기.", "앞선 채팅의 이야기.")
    out = compile_lines([], 2000, story=[own, earlier], policy="packet-v20")
    assert out.text.index('scope="earlier chat"') < out.text.index('kind="story"')
    # a share that holds one of them keeps the chat's own story so far
    long_own = Line("summary", own.xml.replace("이 채팅의 지금까지.", "가" * 120), own.ref, 7, own.text, "가" * 120)
    budget = next(b for b in range(200, 4000)  # the least budget whose story share holds the chat's own
                  if compile_lines([], b, story=[long_own, earlier], policy="packet-v20").ledger[0]["placed"])
    tight = compile_lines([], budget, story=[long_own, earlier], policy="packet-v20")
    kinds = [(e["ref"].get("carried"), e["placed"], e["why"]) for e in tight.ledger]
    assert kinds == [(None, True, "placed"), ("L", False, "story_cap")], (kinds, STORY_SHARE)


def test_an_earlier_chats_story_that_repeats_a_secret_kept_here_is_left_out() -> None:
    secrets = [{"id": 1, "text": "세라 knows: 붉은 벽돌 아래 지하 창고 열쇠가 숨겨져 있다", "holders": ["세라"],
                "open": ["카이토"]}]
    view = {"carried": {"link": "L", "story": {"text": "붉은 벽돌 아래 지하 창고 열쇠가 숨겨져 있다.",
                                               "from": {"summary": "s"}}}}
    hidden: list[dict[str, Any]] = []
    assert retrieval.carried_story(view, secrets, frozenset(), hidden) is None
    assert hidden == [{"kind": "summary", "ref": {"carried": "L", "summary": "s"}, "turn": None, "text": "",
                       "tok": 0, "placed": False, "why": "secret_gate", "label": "hidden"}]
    assert retrieval.carried_story(view, [], frozenset()) is not None
    assert retrieval.carried_story({"carried": {"link": "L", "story": None}}, [], frozenset()) is None


# --- regression: memory of a previous timeline, apart -------------------------------------------------------------

ASK = "세라는 카이토를 기억해?"
GROUP = re.compile(r"  <Regression remembered_by=\"(?P<names>[^\"]*)\">\n(?P<body>.*?)\n  </Regression>", re.DOTALL)


def _group(text: str) -> tuple[str, str] | None:
    found = GROUP.search(text)
    return (found["names"], found["body"]) if found else None


def _outside(text: str) -> str:
    return GROUP.sub("", text)


def test_regression_lines_are_only_inside_their_group_for_the_named(migrated: str) -> None:
    with make_client(migrated, **CANON_ON) as c:
        src, _, tgt = _world(c, migrated)
        with _connect(migrated) as conn:
            carried = _link(conn, tgt, src, "regression", ["세라"])
            out, g = _packet(conn, tgt, ASK, carried)
            plain, _ = _packet(conn, tgt, ASK, None)
    group = _group(out.text)
    assert group is not None and group[0] == "세라"
    lines = group[1].split("\n")
    assert 1 <= len(lines) <= REGRESSION_MAX
    for line in lines:
        assert line.startswith(("    <Fact ", "    <Thread ")) and ' timeline="previous"' in line
        assert ' known_by="세라"' in line and " turn=" not in line and 'source="carried"' not in line
    assert '    <Fact kind="relationship" timeline="previous" known_by="세라">세라 relationship 카이토: 오랜 동료</Fact>' in lines
    assert any(x.startswith(f'    <Thread kind="promise" by="세라" to="카이토" timeline="previous" known_by="세라">{PROMISE}')
               for x in lines)
    assert REGRESSION_NOTE in out.text and REGRESSION_MARK not in plain.text and REGRESSION_NOTE not in plain.text
    assert PRIVATE_NOTE not in out.text  # private only as limited knowledge: no line went to <Private>
    # Rows that involve no one named are never carried: the source's 유나 and its persona's tiredness.
    assert "사망" not in out.text and "지침" not in out.text
    # Nothing carried anywhere else: not facts, cast, threads, gone pins, settled lines or return marks.
    outside = _outside(out.text)
    assert 'timeline="previous"' not in outside and "오랜 동료" not in outside and PROMISE not in outside
    assert 'source="carried"' not in out.text
    assert not g.gone and not g.cast_marks and not [x for x in g.settled if x.ref.get("carried")]
    assert not [x for x in g.lead + g.facts + g.threads + [y for _, ys in g.cast_lines for y in ys] if x.ref.get("carried")]
    # Each line's ledger entry: in its section, private, with the link, the source assertion and who remembers it.
    entries = [e for e in out.ledger if e.get("section") == "regression"]
    assert len(entries) == len(g.regression) and all(e["placed"] for e in entries)
    for e in entries:
        assert e["ref"]["carried"] == carried.link and e["ref"]["source_assertion"] > 0 and e["ref"]["assertion"] < 0
        assert e["marks"]["remembered_by"] == ["세라"] and e["turn"] is None and e["label"] == "required"


def _many(src: UUID, n: int = 8) -> carry.Carried:
    values = ("피곤함", "배고픔", "졸림", "슬픔", "기쁨", "분노", "두려움", "놀람")[:n]
    facts = [{"predicate": "has_status", "subject": "세라", "subject_type": "character", "value": v,
              "object": None, "object_type": None, "polarity": "positive", "modality": "actual", "source": "narration",
              "turn": i, "position": 2 * i, "knowledge": "limited", "known_by": ["세라"], "hidden_from": None,
              "from": {"conversation": str(src), "assertion": 100 + i, "revision": None, "generation": "g", "repair": None}}
             for i, v in enumerate(values)]
    return carry.target_rows({"id": UUID("00000000-0000-7000-8000-000000000001"), "source_conversation_id": src,
                              "mode": "regression", "entity_names": ["세라"],
                              "snapshot": {"mode": "regression", "names": ["세라"], "facts": facts[::-1], "threads": []}})


def test_at_most_six_regression_lines_the_newest_first_on_a_tie(migrated: str) -> None:
    with make_client(migrated, **CANON_ON) as c:
        src, _, tgt = _world(c, migrated)
        with _connect(migrated) as conn:
            carried = _many(src)
            assert len({r["id"] for r in carried.regression}) == 8 and all(r["id"] < 0 for r in carried.regression)
            out, g = _packet(conn, tgt, "세라는 그때를 기억해?", carried)
    assert REGRESSION_MAX == 6 and len(g.regression) == 6
    assert [x.ref["source_assertion"] for x in g.regression] == [107, 106, 105, 104, 103, 102]
    assert _group(out.text)[1].count("<Fact ") == 6


def test_no_regression_line_for_a_message_about_no_one_who_remembers(migrated: str) -> None:
    with make_client(migrated, **CANON_ON) as c:
        src, _, tgt = _world(c, migrated)
        with _connect(migrated) as conn:
            carried = _link(conn, tgt, src, "regression", ["세라"])
            out, g = _packet(conn, tgt, "오늘은 날씨가 맑네.", carried)
    assert g.regression == [] and "<Regression" not in out.text and REGRESSION_NOTE not in out.text


def test_strict_mode_withholds_regression_lines_as_secrets(migrated: str) -> None:
    with make_client(migrated, **CANON_ON) as c:
        src, _, tgt = _world(c, migrated)
        with _connect(migrated) as conn:
            carried = _link(conn, tgt, src, "regression", ["세라"])
            out, g = _packet(conn, tgt, ASK, carried, strict=True)
    group = _group(out.text)
    assert group is not None and group[0] == "세라"
    assert group[1].startswith("    <Secret holders=\"세라\"") and "<Fact " not in group[1] and "<Thread " not in group[1]
    assert "오랜 동료" not in out.text and PROMISE not in out.text and 'timeline="previous"' not in out.text
    assert g.withheld >= 3


def test_a_narrator_who_does_not_remember_never_sees_regression_lines(migrated: str) -> None:
    with make_client(migrated, **CANON_ON) as c:
        src, _, tgt = _world(c, migrated)
        with _connect(migrated) as conn:
            carried = _link(conn, tgt, src, "regression", ["세라"])
            kaito, _ = _packet(conn, tgt, ASK, carried, narrator="카이토")
            sera, _ = _packet(conn, tgt, ASK, carried, narrator="세라")
    assert "<Regression" not in kaito.text and "오랜 동료" not in kaito.text and PROMISE not in kaito.text
    group = _group(sera.text)
    assert group is not None and "오랜 동료" in group[1] and PROMISE in group[1]


def _line(text: str, remembered: list[str], ref: int) -> Line:
    xml = f'    <Fact kind="has_status" timeline="previous" known_by="{", ".join(remembered)}">{text}</Fact>'
    return Line("fact", xml, {"assertion": -ref, "carried": "L", "source_assertion": ref}, None, text, text,
                {"remembered_by": remembered}, True)


def test_the_regression_group_follows_private_lines_and_precedes_excerpts() -> None:
    private = Line("fact", '    <Fact kind="knows" turn="3" known_by="하나">하나 knows: 비밀</Fact>', {"assertion": 1}, 3,
                   "하나 knows: 비밀", "비밀", {}, True)
    excerpt = Excerpt(turn=2, speaker="하나", text="하나가 문을 열고 들어와 조용히 인사했다.", score=1.0, revision_id="r1")
    regression = [_line("하나 has status: 슬픔", ["하나"], 7), _line("세라 has status: 기쁨", ["세라"], 8)]
    out = compile_lines([excerpt], 3000, facts=[private], policy="packet-v20", regression=regression,
                        regression_names=("세라", "하나"))
    text = out.text
    assert text.index("</Private>") < text.index('<Regression remembered_by="세라, 하나">') < text.index("<Excerpt ")
    assert REGRESSION_NOTE in text
    entries = [e for e in out.ledger if e.get("section") == "regression"]
    assert [e["ref"]["source_assertion"] for e in entries] == [7, 8] and all(e["placed"] for e in entries)
    # only the placed lines' rememberers name the group
    one = compile_lines([], 3000, policy="packet-v20", regression=regression[:1], regression_names=("세라", "하나"))
    assert '<Regression remembered_by="하나">' in one.text
    # nothing placed, no group and no Note sentence
    none = compile_lines([], 3000, policy="packet-v20", regression=[], regression_names=("세라",))
    assert "<Regression" not in none.text and REGRESSION_NOTE not in none.text
    # a regression line alone is a packet
    assert one.text and "</Regression>" in one.text
    # every other policy ignores them
    for policy in ("packet-v19", "packet-v14", "packet-v8"):
        with_lines = compile_lines([excerpt], 3000, facts=[private], policy=policy, regression=regression,
                                   regression_names=("세라", "하나"))
        assert with_lines.text == compile_lines([excerpt], 3000, facts=[private], policy=policy).text
        assert with_lines.ledger == compile_lines([excerpt], 3000, facts=[private], policy=policy).ledger


def test_an_owner_memory_exclusion_leaves_its_regression_lines_and_rememberer_out(migrated: str) -> None:
    """Review F1 (PHASE-47 S2): with 카이토 left out of the target's memory, the group loses the standing he is one
    end of and no longer names him; removing the exclusion brings them back; a request recorded under it replays as
    it was answered; packet-v19 shows no regression line either way."""
    from test_phase60_carry_recall import _ask, _client, _replay

    def lines(text: str) -> tuple[str, list[str]]:
        group = _group(text)
        assert group is not None
        return group[0], group[1].split("\n")

    with _client(migrated, "packet-v20") as c:
        src, tgt_sim, tgt = _world(c, migrated, 4)  # the target's turn 3 names 카이토
        with _connect(migrated) as conn:
            _link(conn, tgt, src, "regression", ["세라", "카이토"])
        before, _ = _ask(c, tgt_sim)
        names, kept = lines(before)
        assert names == "세라, 카이토" and any("오랜 동료" in x and 'known_by="세라, 카이토"' in x for x in kept)
        res = c.post(f"/v1/conversations/{tgt}/repairs",
                     json={"kind": "entity_exclude", "item": "카이토", "scope": "memory"})
        assert res.status_code == 200, res.text
        rid = res.json()["repair"]["id"]
        excluded, trace = _ask(c, tgt_sim)
        names, kept = lines(excluded)
        assert names == "세라" and kept and all(' known_by="세라"' in x for x in kept)
        assert "오랜 동료" not in excluded  # a standing 카이토 is one end of
    with _client(migrated, "packet-v19") as c:
        older, _ = _ask(c, tgt_sim)
    assert "<Regression" not in older and 'timeline="previous"' not in older
    with _client(migrated, "packet-v20") as c:
        assert c.post(f"/v1/conversations/{tgt}/repairs/{rid}/remove").status_code == 200
        again, _ = _ask(c, tgt_sim)
    assert _group(again) == _group(before)
    replayed = _replay(migrated, trace)  # the exclusion as of the request, removed since
    assert replayed["text"] == excluded and replayed["reproduced"] is True
    with _client(migrated, "packet-v19") as c:
        assert "<Regression" not in _ask(c, tgt_sim)[0]


# --- packet-v19 never reads a link (A3) ---------------------------------------------------------------------------

def test_v19_packets_are_byte_identical_with_a_link_in_force_fresh_and_replayed(migrated: str) -> None:
    from test_phase60_carry_recall import _ask, _client, _replay
    with _client(migrated, "packet-v19") as c:
        src, tgt_sim, tgt = _world(c, migrated)
        before, first = _ask(c, tgt_sim)
        for mode, names in (("continue", []), ("regression", ["세라"])):
            with _connect(migrated) as conn:
                _link(conn, tgt, src, mode, names)
            text, trace = _ask(c, tgt_sim)
            assert text == before and "carry" not in trace["recall_options"]
            again = _replay(migrated, trace)
            assert again["text"] == before and again["reproduced"] is True
            assert _replay(migrated, first)["text"] == before
    with _client(migrated, "packet-v20") as c:  # the same request under packet-v20 reads the regression link
        text, _ = _ask(c, tgt_sim)
    assert "<Regression" in text and "<Regression" not in before
