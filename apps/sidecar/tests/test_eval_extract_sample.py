"""The sampled-turn comparison tool (PHASE-19 step 4): which turns it takes, how it scores the evidence check on rows
of a generation with and without the check, and what counts as finding a ledger fact. Synthetic rows only."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path

from nmos_sidecar import extraction

TOOL = Path(__file__).resolve().parents[3] / "tools/eval_extract_sample.py"
_spec = importlib.util.spec_from_file_location("eval_extract_sample", TOOL)
tool = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tool)

TURN = "하나가 카이토에게 등대 열쇠를 건네주었다. 카이토는 고개를 끄덕였다."


def row(evidence: str | None, status: str = "valid", reason: str | None = None, **extra) -> dict:
    return {"subject": "하나", "predicate": "event", "object": None, "value": "등대 열쇠를 건넴", "evidence": evidence,
            "status": status, "reason": reason, **extra}


def test_the_tool_uses_the_extractors_evidence_test():
    assert (tool.QUOTE_MIN, tool.QUOTE_MIN_CHARS) == (extraction.EVIDENCE_MIN, extraction.EVIDENCE_MIN_CHARS)
    assert tool.in_turn("하나가 카이토에게 등대 열쇠를", TURN) is True
    assert tool.in_turn("유이는 어젯밤 항구의 창고에서", TURN) is False
    assert tool.in_turn("등대 열쇠", TURN) is None and tool.in_turn(None, TURN) is None  # not checked


def test_ledger_turns_are_nmos_turns(tmp_path):
    ledger = tmp_path / "ledger.json"
    ledger.write_text(json.dumps([{"must_appear_in_turn": 1}, {"must_appear_in_turn": 5}, {"must_appear_in_turn": None},
                                  {"must_appear_in_turn": 5}]))
    assert tool.ledger_turns(ledger) == {0, 4}


def test_a_ledger_fact_is_found_by_a_row_that_names_its_character_and_overlaps_it():
    fact = {"subject": "하나-카이토", "statement": "하나가 카이토에게 등대 열쇠를 건넨다", "kind": "event"}
    assert tool.hit(row(None), fact, "타쿠미")
    assert not tool.hit({**row(None), "subject": "유이"}, fact, "타쿠미")  # no character of the fact named
    assert not tool.hit({**row(None), "value": "항구로 떠남"}, fact, "타쿠미")  # another fact
    persona = {"subject": "{{user}}-카이토", "statement": "타쿠미가 카이토를 도와준다", "kind": "event"}
    assert tool.hit({**row(None), "subject": "{{user}}", "value": "카이토를 도와준다"}, persona, "타쿠미")


def test_score_counts_the_check_the_same_way_with_and_without_it(tmp_path, capsys):
    # Today's rows are valid and only marked; extract-v14 parks the same row itself.
    today = {"turn": 4, "usage": {"input": 900, "output": 90}, "assertions": [
        row("하나가 카이토에게 등대 열쇠를", quote_in_turn=True),
        row("유이는 어젯밤 항구의 창고에서", quote_in_turn=False),
        row("열쇠", quote_in_turn=None)]}
    v14 = {"turn": 4, "usage": {"input": 700, "output": 95}, "assertions": [
        row("하나가 카이토에게 등대 열쇠를", quote_in_turn=True),
        row("유이는 어젯밤 항구의 창고에서", "pending", "evidence not in the turn", quote_in_turn=False),
        row("?", "invalid", "unknown predicate", quote_in_turn=None)]}
    for label, data in (("v13", today), ("v14", v14)):
        path = tmp_path / label / "1" / "synth-4.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(data, ensure_ascii=False))
    ledger = tmp_path / "ledger.json"
    ledger.write_text(json.dumps([{"must_appear_in_turn": 5, "subject": "하나", "statement": "하나가 등대 열쇠를 건넴",
                                   "kind": "event"}], ensure_ascii=False))
    tool.score(argparse.Namespace(out=tmp_path, labels="v13,v14", name="synth", ledger=ledger, persona=""))
    lines = [x for x in capsys.readouterr().out.splitlines() if x.startswith("| v1")]
    assert lines[0].startswith("| v13 | 1 | 1 | 3 | 1 | 1 | 33.3 % | 1/1 | 1/1 | 0 | 0 | 0 | 0 | 0 / 0 | 0 | 1k | 90 |")
    assert lines[1].startswith("| v14 | 1 | 1 | 2 | 0 | 1 | 50.0 % | 1/1 | 1/1 | 0 | 0 | 0 | 0 | 0 / 0 | 0 | 1k | 95 |")


def test_turns_are_chosen_from_one_chat(migrated):
    import psycopg
    import pytest
    from psycopg.rows import dict_row

    from conftest import make_client
    from simchat import SimChat
    from test_generations import LLM
    from test_sidecar_integration import sync

    chats = [SimChat("sample-a"), SimChat("sample-b")]
    with make_client(migrated, **LLM) as c:
        for n, chat in enumerate(chats):
            for i in range(3 + n):
                chat.user(f"Question {i} of chat {n}.")
                chat.reply(f"Answer {i} of chat {n}.")
            chat.user("Next.")
            sync(c, chat)
    with psycopg.connect(migrated, row_factory=dict_row) as conn:
        ids = {r["host_chat_ref"]: str(r["id"]) for r in conn.execute("SELECT id, host_chat_ref FROM conversation")}
        with pytest.raises(SystemExit, match="give --conversation"):
            tool.conversation_of(conn, None)
        rows = tool.anchors(conn, ids["sample-b"])
        members = conn.execute("SELECT DISTINCT so.conversation_id FROM source_revision sr"
                               " JOIN source_object so ON so.id = sr.source_object_id WHERE sr.id = ANY(%s)",
                               ([r["id"] for r in rows],)).fetchall()
    assert [r["turn"] for r in rows] == list(range(len(rows))) and len(rows) >= 4
    assert [str(m["conversation_id"]) for m in members] == [ids["sample-b"]]


def test_score_counts_relationship_and_role_rows_apart(tmp_path, capsys):
    rows = [{**row(None), "predicate": p, "object": "카이토", "quote_in_turn": None}
            for p in ("relationship", "role_toward", "role_toward", "addresses")]
    path = tmp_path / "v15" / "1" / "synth-4.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"turn": 4, "usage": {"input": 800, "output": 80}, "assertions": rows}, ensure_ascii=False))
    tool.score(argparse.Namespace(out=tmp_path, labels="v15", name="synth", ledger=None, persona=""))
    (line,) = [x for x in capsys.readouterr().out.splitlines() if x.startswith("| v15")]
    assert line.startswith("| v15 | 1 | 1 | 4 | 0 | 0 | 0.0 % | 0/0 | 0/0 | 0 | 1 | 1 | 2 | 0 / 0 | 0 | 1k | 80 |")


def test_score_counts_role_endings_as_listed_and_others_apart(tmp_path, capsys):
    """PHASE-28 Q5 (c): an ending with a listed role's subject, object and value closes it (ADR 0013); another does not."""
    listed = [{"by": "하나", "to": "카이토", "role": "세입자: 카이토의 집에 삶", "turn": 1}]
    ending = {**row(None), "predicate": "role_toward", "object": "카이토", "polarity": "negative", "quote_in_turn": None}
    rows = [{**ending, "value": "세입자:  카이토의 집에 삶"}, {**ending, "value": "세입자였음"},
            {**ending, "value": "집주인", "subject": "카이토", "object": "하나"}]
    path = tmp_path / "v16" / "1" / "synth-4.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"turn": 4, "compiler": "extract-v16", "roles": listed, "usage": {"input": 800, "output": 80},
                                "assertions": rows}, ensure_ascii=False))
    tool.score(argparse.Namespace(out=tmp_path, labels="v16", name="synth", ledger=None, persona=""))
    (line,) = [x for x in capsys.readouterr().out.splitlines() if x.startswith("| v16")]
    assert "| 3 | 1 / 2 | 0 |" in line


def test_another_compiler_is_one_the_checkout_has():
    assert tool.compiler_of(argparse.Namespace(compiler=None)) == extraction.COMPILER_VERSION
    assert tool.compiler_of(argparse.Namespace(compiler="extract-v16")) == "extract-v16"
    import pytest
    with pytest.raises(SystemExit, match="no compiler extract-v61"):
        tool.compiler_of(argparse.Namespace(compiler="extract-v61"))


def test_turns_from_a_stored_run_are_those_turns_and_no_others(migrated, tmp_path):
    import psycopg
    import pytest
    from psycopg.rows import dict_row

    from conftest import make_client
    from simchat import SimChat
    from test_generations import LLM
    from test_sidecar_integration import sync

    chats = [SimChat("stored-a"), SimChat("stored-b")]
    with make_client(migrated, **LLM) as c:
        for n, chat in enumerate(chats):
            for i in range(4 + 2 * n):
                chat.user(f"Question {i} of chat {n}.")
                chat.reply(f"Answer {i} of chat {n}.")
            chat.user("Next.")
            sync(c, chat)
    run_dir = tmp_path / "v14" / "1"
    run_dir.mkdir(parents=True)
    for turn in (0, 2, 5):
        (run_dir / f"main-{turn}.json").write_text("{}")
    (run_dir / "synth-1.json").write_text("{}")
    assert sorted(tool.stored_turns(run_dir, "main")) == [0, 2, 5]
    args = argparse.Namespace(turns_from=run_dir, name="main", every_chat=True, conversation=None, ledger=None,
                              sample=20)
    with psycopg.connect(migrated, row_factory=dict_row) as conn:
        assert [a["turn"] for a in tool.chosen(conn, args)] == [0, 2, 5]  # turn 5: only the longer chat has it
        ids = {r["host_chat_ref"]: str(r["id"]) for r in conn.execute("SELECT id, host_chat_ref FROM conversation")}
        with pytest.raises(SystemExit, match="1 stored turns are not in this copy"):
            tool.chosen(conn, argparse.Namespace(**{**vars(args), "every_chat": False,
                                                    "conversation": ids["stored-a"]}))
