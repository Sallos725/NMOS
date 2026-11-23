"""PHASE-60 S3 (ADR 0082 items 2, 3, 7): a character who is gone stays gone under packet-v20.

The word rule itself is `gone.py` (tests/test_phase60_gone_words.py); these tests cover which rows are chosen, where
their lines go, the budget share, the Note, the memory modes and the echo rule. Synthetic names only.
"""

from __future__ import annotations

import re
import uuid
from uuid import UUID

import psycopg
import pytest
from psycopg.rows import dict_row

from conftest import make_client
from memeval import stub_extractor
from nmos_sidecar import audit, packet, retrieval, scene
from nmos_sidecar.entities import resolve
from nmos_sidecar.facts import _versions, fact_entry, fact_line
from nmos_sidecar.packet import GONE_MARK, GONE_NOTE, Line, compile_lines
from nmos_sidecar.retrieval import GONE_MAX, Gathered, RecallOptions, cast_groups, gone_rows, pin_gone
from simchat import SimChat
from test_generations import LLM
from test_hints import step
from test_semantics import row
from test_sidecar_integration import recall, sync
from test_extraction import drain

C = {"subject_type": "character"}
V20 = RecallOptions(policy="packet-v20")


def marked(text: str) -> int:
    """Lines carrying the mark (the Note's own sentence spells it too)."""
    return text.count(GONE_MARK) - text.count(GONE_NOTE)


def status(pos: int, who: str, value: str, **kw) -> dict:
    return row(pos, who, "has_status", None, value, **C, **kw)


def place(pos: int, who: str, where: str, **kw) -> dict:
    return row(pos, who, "located_in", where, None, **{"subject_type": "character", "object_type": "place", **kw})


def seen(pos: int, who: str, **kw) -> dict:
    """An ordinary narrated row about `who` (puts them in the scene at its turn)."""
    return row(pos, who, "event", None, f"walks in {pos}", **C, **kw)


def view_of(facts, claims=(), other=(), excluded=None) -> dict:
    return {"facts": list(facts), "claims": list(claims), "other": list(other), "excluded": excluded or {},
            "threads": []}


def chosen(facts, now: int | None = 20, claims=(), other=(), persona=(), excluded=None) -> list[str]:
    view = view_of(facts, claims, other)
    r = resolve(uuid.uuid4(), view["facts"] + view["claims"] + view["other"], persona=persona)
    if excluded:
        view["excluded"] = {str(r.key("character", n)): {"scope": "cast"} for n in excluded}
    return [f["subject"] for f in gone_rows(view, r, now)]


# --- selection (pure) ---------------------------------------------------------------------------------------------


def test_a_dead_character_is_chosen_whether_or_not_anyone_names_them():
    assert chosen([status(10, "세라", "전투 중 전사")]) == ["세라"]
    assert chosen([status(10, "세라", "killed in the fire")]) == ["세라"]


def test_not_the_persona():
    assert chosen([status(10, "{{user}}", "사망")]) == []
    assert chosen([status(10, "타쿠미", "사망")], persona=["타쿠미"]) == []


def test_not_a_near_miss_or_a_negation():
    assert chosen([status(10, "세라", "죽을 뻔했다")]) == []
    assert chosen([status(10, "세라", "실종되지 않았다")]) == []
    assert chosen([status(10, "세라", "not dead")]) == []


def test_not_when_a_later_status_replaced_it():
    current = _versions([status(10, "세라", "전투 중 전사"), status(12, "세라", "회복함")])
    assert [f["value"] for f in current] == ["회복함"]  # the view's facts hold the current version only
    assert chosen(current) == []


def test_a_place_counts_only_by_its_whole_name():
    assert chosen([place(10, "세라", "죽음의 숲")]) == []
    assert chosen([place(10, "세라", "저승")]) == ["세라"]
    assert chosen([row(10, "열쇠", "located_in", "행방불명", None, subject_type="item", object_type="place")]) == []


def test_not_negative_disputed_canon_or_a_claim():
    assert chosen([status(10, "세라", "사망", polarity="negative")]) == []
    assert chosen([status(10, "세라", "사망", disputed_by={"turn": 11, "position": 11})]) == []
    # canon: how things stood before the story; never pinned (a quiet canon-dead character would be silenced)
    assert chosen([status(-1, "세라", "사망", canon=True)]) == []
    claim = status(10, "세라", "사망", source="character_claim", asserted_by="카이토")
    assert chosen([], claims=[claim]) == []  # what a character said is not the story's word


def test_not_a_character_the_owner_left_out():
    assert chosen([status(10, "세라", "사망")], excluded=["세라"]) == []


def test_the_story_brings_them_back_only_by_a_later_row_in_the_scene_window():
    dead = status(10, "세라", "사망")
    assert chosen([dead, seen(19, "세라")], now=20) == []  # subject, turn 19 within 18..19
    assert chosen([dead, row(18, "카이토", "feels_toward", "세라", "그리움", **C, object_type="character")],
                  now=20) == []  # object
    assert chosen([dead, seen(19, "카이토", participants=[{"name": "세라", "type": "character"}])], now=20) == []
    assert chosen([dead], claims=[seen(19, "세라", source="character_claim")], now=20) == []
    assert chosen([dead], other=[seen(19, "세라", modality="dreamed")], now=20) == []
    assert chosen([dead, seen(15, "세라")], now=20) == ["세라"]  # turn 15 is outside the window
    assert chosen([status(19, "세라", "사망")], now=20) == ["세라"]  # the status's own turn is no return
    assert chosen([dead, seen(9, "세라")], now=11) == ["세라"]  # before the status


def test_one_line_per_character_and_their_own_gone_rows_do_not_bring_them_back():
    rows = [status(10, "세라", "사망"), place(19, "세라", "저승")]
    view = view_of(rows)
    r = resolve(uuid.uuid4(), rows)
    picked = gone_rows(view, r, 20)
    assert [(f["subject"], f["predicate"]) for f in picked] == [("세라", "located_in")]  # the newest


def test_at_most_eight_the_newest_first():
    names = ["세라", "카이토", "하나", "유나", "레오", "미오", "소라", "리쿠", "아오이", "나기"]
    rows = [status(i + 1, n, "사망") for i, n in enumerate(names)]
    assert GONE_MAX == 8
    assert chosen(rows, now=40) == list(reversed(names))[:8]


def test_a_carried_row_is_neither_a_status_nor_a_return():
    """Carry hook (Track 4): rows carried from another chat arrive flagged `carried`."""
    assert chosen([status(10, "세라", "사망", carried=True)]) == []
    assert chosen([status(10, "세라", "사망"), seen(19, "세라", carried=True)], now=20) == ["세라"]


def test_older_policies_choose_nothing():
    rows = [status(10, "세라", "사망")]
    r = resolve(uuid.uuid4(), rows)
    for policy in ("packet-v19", "packet-v8"):
        assert retrieval.gone_lines(view_of(rows), r, {}, 20, RecallOptions(policy=policy)) == []
    assert len(retrieval.gone_lines(view_of(rows), r, {}, 20, V20)) == 1


# --- the line and its placement --------------------------------------------------------------------------------------


def test_the_line_is_the_status_fact_marked():
    f = status(10, "세라", "전투 중 전사")
    assert fact_line(f) == '    <Fact kind="has_status" turn="10">세라 has status: 전투 중 전사</Fact>'
    assert fact_line(f, gone=True) == '    <Fact kind="has_status" turn="10" gone="true">세라 has status: 전투 중 전사</Fact>'
    line = fact_entry(f, gone=True)
    assert line.marks == {"gone": True} and fact_entry(f).marks == {}


def plain(i: int, text: str = "fact") -> Line:
    return Line("fact", f'    <Fact kind="has_trait" turn="{i}">하나 has trait: {text} {i}</Fact>', {"assertion": f"t{i}"},
                i, f"하나 has trait: {text} {i}", f"{text} {i}")


def gone_line(pos: int, who: str = "세라", value: str = "사망") -> Line:
    return fact_entry(status(pos, who, value), gone=True)


def test_gone_lines_open_facts_before_the_lead_with_the_note_and_label():
    lead = Line("fact", '    <Fact kind="relationship" turn="3">하나 relationship 카이토: 친구</Fact>', {"assertion": "l"}, 3,
                "하나 relationship 카이토: 친구", "친구")
    out = compile_lines([], 2000, facts=[plain(4)], lead=[lead], gone=[gone_line(10)], policy="packet-v20")
    body = out.text.split("<Facts>\n", 1)[1]
    assert body.startswith('    <Fact kind="has_status" turn="10" gone="true">세라 has status: 사망</Fact>\n'
                           '    <Fact kind="relationship"')
    assert marked(out.text) == 1 and GONE_NOTE in out.text
    entry = next(e for e in out.ledger if e["ref"] == {"assertion": 10})
    assert entry["placed"] and entry["label"] == "required" and entry["marks"] == {"gone": True}
    # without a gone line, the Note says nothing of it
    none = compile_lines([], 2000, facts=[plain(4)], lead=[lead], policy="packet-v20")
    assert GONE_NOTE not in none.text and GONE_MARK not in none.text


def test_older_policies_ignore_gone_lines():
    for policy in ("packet-v19", "packet-v14", "packet-v8"):
        with_gone = compile_lines([], 2000, facts=[plain(4)], gone=[gone_line(10)], policy=policy)
        without = compile_lines([], 2000, facts=[plain(4)], policy=policy)
        assert with_gone.text == without.text and with_gone.ledger == without.ledger
    # the mark's Note sentence never fires under an older policy, even for a value that spells the mark
    odd = Line("fact", f'    <Fact kind="has_trait" turn="4">하나 has trait: {GONE_MARK}</Fact>', {"assertion": "o"}, 4,
               "x", GONE_MARK)
    assert GONE_NOTE not in compile_lines([], 2000, facts=[odd], policy="packet-v19").text


def test_gone_lines_take_at_most_a_tenth_of_the_budget_newest_kept():
    lines = [gone_line(i + 1, n) for i, n in enumerate(["세라", "카이토", "하나", "유나", "레오", "미오", "소라", "리쿠"])]
    budget = 900
    out = compile_lines([], budget, facts=[plain(30)], gone=lines, policy="packet-v20")
    frame = packet.estimate_tokens("\n".join([packet.PACKET_OPEN, packet.PACKET_NOTE, packet.PACKET_CLOSE]),
                                   non_ascii=packet.NON_ASCII["packet-v20"])
    cap = int((budget - frame) * packet.GONE_SHARE)
    entries = [e for e in out.ledger if (e.get("marks") or {}).get("gone")]
    placed = [e for e in entries if e["placed"]]
    assert 0 < len(placed) < len(lines)
    est = lambda x: packet.estimate_tokens(x + "\n", non_ascii=packet.NON_ASCII["packet-v20"])  # noqa: E731
    assert sum(est(line.xml) for line in lines if line.turn in {e["turn"] for e in placed}) <= cap
    assert {e["why"] for e in entries if not e["placed"]} == {"gone_cap"}
    assert sorted(e["turn"] for e in placed) == sorted(e["turn"] for e in entries)[-len(placed):]  # the newest
    assert '<Fact kind="has_trait" turn="30">' in out.text  # the rest of Facts is not crowded out
    assert packet.cut_lines(out.ledger) == 0  # a capped pin is not a line the budget left out


def test_no_note_when_every_gone_line_is_beyond_the_share():
    out = compile_lines([], 300, facts=[plain(30)], gone=[gone_line(10, value="전투 중 전사, 오랜 원정 끝에")],
                        policy="packet-v20")
    entry = next(e for e in out.ledger if (e.get("marks") or {}).get("gone"))
    assert entry["why"] == "gone_cap" and not entry["placed"]
    assert out.text and GONE_NOTE not in out.text and GONE_MARK not in out.text


def test_a_gone_line_is_first_in_its_cast_group_and_never_twice():
    rows = [status(10, "세라", "사망"), place(11, "세라", "정원"), seen(19, "카이토")]
    rows[1]["position"] = 9  # an older place: the status is newest
    view = view_of(rows)
    r = resolve(uuid.uuid4(), rows)
    g = Gathered()
    g.cast = scene.cast(rows, r, "세라 보고 싶어", "", 20)
    assert "세라" in g.cast.values()  # named now: in the scene, though no row of a later turn brought them back
    g.cast_lines, used = cast_groups(view, g.cast, r, "세라 보고 싶어", V20)
    g.facts = [fact_entry(rows[0])]  # relevant_facts chose it too
    g.facts = [line for line in g.facts if line.ref.get("assertion") not in used]
    pinned = pin_gone(g, view, r, 20, V20)
    assert [f["id"] for f in pinned] == [10]
    group = dict(g.cast_lines)["세라"]
    assert group[0].marks.get("gone") and group[0].ref == {"assertion": 10}
    assert not g.gone and not g.facts
    out = retrieval.compile_gathered(g, 2000, "packet-v20")
    assert out.text.count("세라 has status: 사망") == 1 and marked(out.text) == 1
    assert '<Character name="세라">\n      <Fact kind="has_status" turn="10" gone="true">' in out.text
    assert GONE_NOTE in out.text
    entry = next(e for e in out.ledger if e["ref"] == {"assertion": 10})
    assert entry["label"] == "required" and entry["marks"] == {"gone": True} and entry["section"] == "cast"


def test_a_gone_line_chosen_as_a_fact_too_appears_once_first_in_facts():
    rows = [status(10, "세라", "사망"), seen(19, "카이토")]
    view = view_of(rows)
    r = resolve(uuid.uuid4(), rows)
    g = Gathered()
    g.cast = scene.cast(rows, r, "", "", 20)
    g.facts = [plain(4), fact_entry(rows[0])]
    pin_gone(g, view, r, 20, V20)
    assert [line.ref for line in g.facts] == [{"assertion": "t4"}]
    out = retrieval.compile_gathered(g, 2000, "packet-v20")
    assert out.text.count("세라 has status: 사망") == 1
    assert out.text.split("<Facts>\n", 1)[1].startswith('    <Fact kind="has_status" turn="10" gone="true">')


def test_an_echoed_gone_line_is_dropped_by_the_normalizer():
    """A12 / ADR 0082 item 7: the mark is an attribute of <Fact>, so clean-v3 drops an echo whole (K27)."""
    xml = gone_line(10, value="전투 중 전사").xml.strip()
    cleaned = packet.clean_text(f"카이토가 고개를 숙였다. {xml} 바람이 분다.")
    assert "전사" not in cleaned and "gone" not in cleaned
    assert cleaned == "카이토가 고개를 숙였다. 바람이 분다."


# --- memory modes (pure) ------------------------------------------------------------------------------------------------


SECRET = {"knowledge": "limited", "known_by": ["하나", "{{user}}"], "hidden_from": ["카이토"]}


def secret_scene(options: RecallOptions):
    rows = [status(10, "세라", "사망", **SECRET), seen(19, "카이토"), seen(18, "하나")]
    view = view_of(rows)
    r = resolve(uuid.uuid4(), rows)
    g = Gathered()
    g.cast = scene.cast(rows, r, "", "", 20)
    assert scene.private(rows[0], g.cast, r)  # 카이토 is in the scene and does not know
    g.cast_lines, _ = cast_groups(view, g.cast, r, "", options)
    pin_gone(g, view, r, 20, options)
    return g, retrieval.compile_gathered(g, 2000, options.policy)


def test_a_private_gone_line_goes_to_private_not_facts():
    g, out = secret_scene(V20)
    assert "<Facts>" not in out.text
    cast = out.text.split("<Cast>", 1)[1].split("</Cast>", 1)[0] if "<Cast>" in out.text else ""
    assert "사망" not in cast
    private = out.text.split("<Private>", 1)[1].split("</Private>", 1)[0]
    assert '<Fact kind="has_status" turn="10" gone="true" known_by="하나, {{user}}" hidden_from="카이토">' in private
    assert marked(out.text) == 1 and GONE_NOTE in out.text and packet.PRIVATE_NOTE in out.text


def test_strict_mode_withholds_a_gone_line_as_a_secret_with_no_mark():
    g, out = secret_scene(RecallOptions(policy="packet-v20", strict=True))
    assert "<Secret " in out.text and "사망" not in out.text
    assert GONE_MARK not in out.text and GONE_NOTE not in out.text
    assert g.withheld == 1


def test_a_narrator_who_does_not_know_never_sees_the_gone_line():
    g, out = secret_scene(RecallOptions(policy="packet-v20", narrator="카이토"))
    assert "사망" not in out.text and GONE_MARK not in out.text and GONE_NOTE not in out.text
    assert g.withheld == 1
    g, out = secret_scene(RecallOptions(policy="packet-v20", narrator="하나"))
    assert marked(out.text) == 1  # a narrator who knows it keeps it (in <Private>: 카이토 does not)


# --- end to end (stub model, test database) --------------------------------------------------------------------------


STATUS = re.compile(r"(?P<who>[가-힣]+)의 상태: (?P<what>[^.,]+)\.")
SECRET_STATUS = re.compile(r"(?P<who>[가-힣]+)의 숨긴 상태: (?P<what>[^.,]+), (?P<from>[가-힣]+) 모르게\.")


def gone_stub(system: str, user: str) -> tuple[dict, str]:
    out, raw = stub_extractor(system, user)
    target = user.split("TARGET", 1)[1]
    base = {"subject_type": "character", "predicate": "has_status", "modality": "actual", "source": "narration",
            "epistemic": "stated", "confidence": 0.9}
    out["assertions"] += [{**base, "subject": m["who"], "value": m["what"], "evidence": m.group(0)}
                          for m in STATUS.finditer(target)]
    out["assertions"] += [{**base, "subject": m["who"], "value": m["what"], "evidence": m.group(0),
                           "knowledge": "limited", "known_by": ["하나", "{{user}}"], "hidden_from": [m["from"]]}
                          for m in SECRET_STATUS.finditer(target)]
    return out, raw


def story(c, url: str, first: str) -> SimChat:
    chat = SimChat()
    for line in (first, "하나 has the lantern.", "Idle chatter 1 about clouds.", "Idle chatter 2 about clouds.",
                 "Idle chatter 3 about clouds."):
        step(c, url, chat, gone_stub, line)
    return chat


def ask(c, url: str, chat: SimChat, query: str) -> dict:
    chat.user(query)
    sync(c, chat)
    drain(url, gone_stub)
    return recall(c, chat, query, in_context=[m["chatId"] for m in chat.messages[-4:]], budget=1500)


@pytest.mark.parametrize("policy", ["packet-v20", "packet-v19"])
def test_a_dead_character_is_pinned_under_v20_only(migrated, policy):
    with make_client(migrated, packet_policy=policy, **LLM) as c:
        chat = story(c, migrated, "세라의 상태: 전투 중 전사.")
        out = ask(c, migrated, chat, "오늘은 날씨가 맑네.")
        text = out["packet"]["text"]
        trace = c.get(f"/v1/trace/{out['trace_id']}").json()
    assert trace["policy"] == policy
    if policy == "packet-v20":
        assert '<Fact kind="has_status" turn="0" gone="true">세라 has status: 전투 중 전사</Fact>' in text
        assert marked(text) == 1 and GONE_NOTE in text
        entry = next(e for e in trace["lines"] if (e.get("marks") or {}).get("gone"))
        assert entry["placed"] and entry["label"] == "required"
        with psycopg.connect(migrated, row_factory=dict_row) as conn:  # the recorded pin replays as it was (D39)
            again = audit.replay(conn, UUID(out["trace_id"]), RecallOptions(), policy=None)
        assert again["status"] == "ok" and again["reproduced"] is True and again["text"] == text
    else:
        assert GONE_MARK not in text and GONE_NOTE not in text


@pytest.mark.parametrize("mode", [None, {"strict": True}, {"narrator": "카이토"}])
def test_a_gone_fact_kept_from_someone_in_the_scene_follows_the_memory_mode(migrated, mode):
    with make_client(migrated, packet_policy="packet-v20", **LLM) as c:
        chat = story(c, migrated, "세라의 숨긴 상태: 사망, 카이토 모르게.")
        if mode is not None:
            conv = next(x for x in c.get("/v1/conversations").json() if x["host_chat_ref"] == chat.id)["id"]
            assert c.put(f"/v1/conversations/{conv}/memory-mode", json=mode).status_code == 200
        text = ask(c, migrated, chat, "카이토, 오늘은 어디 갈까?")["packet"]["text"]
    if mode is None:  # private: in <Private>, marked
        private = text.split("<Private>", 1)[1].split("</Private>", 1)[0]
        assert 'gone="true"' in private and "세라 has status: 사망" in private
        assert "<Facts>" not in text or "사망" not in text.split("<Facts>", 1)[1].split("</Facts>", 1)[0]
    elif mode.get("strict"):
        assert "<Secret " in text and "사망" not in text and GONE_MARK not in text and GONE_NOTE not in text
    else:
        assert "사망" not in text and GONE_MARK not in text and GONE_NOTE not in text
