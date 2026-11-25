"""Tier 4 (audit B4.3): per-turn persona attribution.

Each synced `source_revision` records the host persona active when it arrived (nullable for legacy revisions).
Switching personas mid-chat (e.g. interlude '타쿠미' -> '레이' -> '타쿠미') keeps older `{{user}}` facts unified with
the earlier persona instead of retroactively attributing them to the new persona or splitting them from named rows.
Renaming the same persona ('카일' <-> '아오키 카일', '윤기현' <-> '기현', 'Ronan Voss/ 윤기현' <-> 'Ronan Voss') stays
unified as the persona.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from conftest import make_client
from nmos_sidecar import archive, extraction, facts, generations, worker
from nmos_sidecar.config import Settings
from simchat import SimChat
from test_generations import LLM
from test_sidecar_integration import sync


def _extract_all(conn: psycopg.Connection, settings: Settings, by_turn: dict[int, list[dict]]) -> str:
    gen = extraction.extractor(settings)
    assert gen is not None
    generations.activate(conn, gen)
    while worker.run_once(conn, {"extract": (gen.key, lambda c, j: extraction.process_extract(
        c, j,
        lambda _s, u: ({"assertions": _pick(c, j, by_turn)}, "{}", {"prompt_tokens": 10, "completion_tokens": 10}),
        gen, turns=settings.extract_turns,
    ))}):
        pass
    return gen.key


def _pick(conn: psycopg.Connection, job: dict, by_turn: dict[int, list[dict]]) -> list[dict]:
    row = conn.execute(
        "SELECT am.turn FROM active_membership am WHERE am.source_revision_id = %s AND am.turn_hash = %s LIMIT 1",
        (UUID(job["payload"]["revision_id"]), job["payload"]["window_hash"]),
    ).fetchone()
    assert row is not None
    return by_turn.get(row["turn"], [])


def _a(subject: str, predicate: str, obj: str | None = None, value: str | None = None, **extra) -> dict:
    return {
        "subject": subject,
        "subject_type": extra.pop("subject_type", "character"),
        "predicate": predicate,
        "object": obj,
        "object_type": extra.pop("object_type", "place" if predicate == "located_in" else "character" if obj else None),
        "value": value,
        "epistemic": "stated",
        "confidence": "explicit",
        "evidence": extra.pop("evidence", "ev"),
        "knowledge": extra.pop("knowledge", "public"),
        "known_by": extra.pop("known_by", None),
        "hidden_from": extra.pop("hidden_from", None),
        "polarity": "positive",
        "modality": "actual",
        "source": extra.pop("source", "narration"),
        "asserted_by": extra.pop("asserted_by", None),
        **extra,
    }


def test_attribute_persona_unit_switch_and_rename():
    rows = [
        {"subject": "{{user}}", "subject_type": "character", "predicate": "located_in",
         "object": "도서관", "object_type": "place", "turn_persona": "타쿠미",
         "known_by": ["{{user}}", "세라"], "hidden_from": ["유저"],
         "participants": ({"type": "character", "name": "{{user}}"}, {"type": "character", "name": "세라"})},
        {"subject": "세라", "subject_type": "character", "predicate": "feels_toward",
         "object": "{{user}}", "object_type": "character", "value": "신뢰",
         "asserted_by": "{{user}}", "turn_persona": "타쿠미"},
        {"subject": "{{user}}", "subject_type": "character", "predicate": "also_called",
         "value": "아오키", "turn_persona": "타쿠미"},
        {"subject": "{{user}}", "subject_type": "character", "predicate": "located_in",
         "object": "성당", "object_type": "place", "turn_persona": "레이"},
        {"subject": "{{user}}", "subject_type": "character", "predicate": "located_in",
         "object": "광장", "object_type": "place", "turn_persona": None},  # legacy row untouched
    ]
    personas = facts.attribute_persona(rows, "레이")
    assert personas == ["레이"]
    # Turn under 타쿠미 rewritten to 타쿠미 across all USER_NAMES slots
    assert rows[0]["subject"] == "타쿠미"
    assert rows[0]["known_by"] == ["타쿠미", "세라"]
    assert rows[0]["hidden_from"] == ["타쿠미"]
    assert rows[0]["participants"][0]["name"] == "타쿠미"
    assert rows[1]["object"] == "타쿠미"
    assert rows[1]["asserted_by"] == "타쿠미"
    assert rows[2]["subject"] == "타쿠미"
    # Current persona row and legacy NULL row stay {{user}}
    assert rows[3]["subject"] == "{{user}}"
    assert rows[4]["subject"] == "{{user}}"
    # Idempotent
    assert facts.attribute_persona(rows, "레이") == ["레이"]

    # Rename cases stay unified as persona (never rewritten to a stray NPC)
    for old, new in (("카일", "아오키 카일"), ("아오키 카일", "카일"),
                     ("윤기현", "기현"), ("기현", "윤기현"),
                     ("Ronan Voss/ 윤기현", "Ronan Voss"), ("Ronan Voss", "Ronan Voss/ 윤기현")):
        r = [{"subject": "{{user}}", "subject_type": "character", "predicate": "located_in",
              "object": "항구", "object_type": "place", "turn_persona": old}]
        got = facts.attribute_persona(r, new)
        assert r[0]["subject"] == "{{user}}", (old, new)
        assert new in got and old in got, (old, new, got)


def test_mid_chat_persona_switch_and_switch_back_end_to_end(migrated: str):
    settings = Settings(database_url=migrated, **LLM)
    with make_client(migrated, **LLM) as client:
        chat = SimChat("b43-interlude")
        # Turn 0 under 타쿠미
        chat.user("도서관에서 은검을 챙겼다.")
        chat.reply("세라가 타쿠미에게 미소 지었다.")
        sync(client, chat, persona_name="타쿠미")
        # Turn 1 under 레이 (interlude switch)
        chat.user("레이는 성당에서 촛불을 켰다.")
        chat.reply("레이는 창밖을 바라보았다.")
        sync(client, chat, persona_name="레이")
        # Turn 2 user confirms turn 1 so turn 1 is accepted
        chat.user("성당 종소리가 울렸다.")
        out2 = sync(client, chat, persona_name="레이")
        head = UUID(out2["active_commit"])

        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            # Verify source_revision.persona_name recorded per turn
            revs = conn.execute(
                "SELECT am.turn, sr.persona_name FROM active_membership am"
                " JOIN source_revision sr ON sr.id = am.source_revision_id"
                " WHERE am.commit_id = %s ORDER BY am.position",
                (head,),
            ).fetchall()
            assert [r["persona_name"] for r in revs[:2]] == ["타쿠미", "타쿠미"]
            assert [r["persona_name"] for r in revs[2:]] == ["레이", "레이", "레이"]

            key = _extract_all(conn, settings, {
                0: [
                    _a("{{user}}", "located_in", "도서관", evidence="도서관에서 은검을 챙겼다."),
                    _a("타쿠미", "possesses", "은검", object_type="item", evidence="도서관에서 은검을 챙겼다."),
                    _a("세라", "feels_toward", "{{user}}", "신뢰", evidence="세라가 타쿠미에게 미소 지었다."),
                ],
                1: [
                    _a("{{user}}", "located_in", "성당", evidence="레이는 성당에서 촛불을 켰다."),
                    _a("레이", "possesses", "촛불", object_type="item", evidence="레이는 성당에서 촛불을 켰다."),
                ],
            })

            # Live read while active persona is 레이:
            # - 타쿠미's {{user}} located_in 도서관 AND 타쿠미's holds 은검 unify into ONE non-persona entity 타쿠미!
            # - 레이 (persona=True) ONLY has located_in 성당 + holds 촛불, NEVER inherits 도서관 or 세라's 신뢰!
            view_rei = facts.memory_view(conn, head, key)
            by_name = {e["name"]: e for e in view_rei["entities"] if e["type"] == "character"}
            assert "타쿠미" in by_name and not by_name["타쿠미"]["persona"]
            rei = next(e for e in view_rei["entities"] if e["persona"])
            assert "레이" in rei["names"]
            assert "타쿠미" not in rei["names"]

            loc_by_subj = {f["subject_entity"]["id"]: f["object"] for f in view_rei["facts"]
                           if f["predicate"] == "located_in"}
            assert loc_by_subj[by_name["타쿠미"]["id"]] == "도서관"
            assert loc_by_subj[rei["id"]] == "성당"
            feels = [f for f in view_rei["facts"] if f["predicate"] == "feels_toward"]
            assert len(feels) == 1 and feels[0]["object_entity"]["id"] == by_name["타쿠미"]["id"]

            # Extraction hints when extracting a turn under 레이 MUST include 타쿠미 as a known character!
            ctx_rei = {"target": {"conversation_id": UUID(out2["conversation_id"]), "commit_id": head,
                                  "turn": 2, "turn_persona": "레이", "host_persona_name": "레이"}}
            hints = extraction.entity_hints(conn, ctx_rei, key, 20)
            hint_names = {h["name"] for h in hints}
            assert "타쿠미" in hint_names
            assert "레이" not in hint_names

            # Historical replay as of turn 0 (`upto=1`) STILL treats 타쿠미 as the persona!
            view_replay = facts.memory_view(conn, head, key, upto=1)
            replay_persona = next(e for e in view_replay["entities"] if e["persona"])
            assert "타쿠미" in replay_persona["names"]
            assert not any(e["name"] == "레이" for e in view_replay["entities"])

        # Switch BACK to 타쿠미 on turn 2 reply + turn 3:
        chat.reply("타쿠미가 돌아왔다.")
        chat.user("다시 도서관으로 갔다.")
        out3 = sync(client, chat, persona_name="타쿠미")
        head3 = UUID(out3["active_commit"])

        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            view_back = facts.memory_view(conn, head3, key)
            persona_back = next(e for e in view_back["entities"] if e["persona"])
            assert "타쿠미" in persona_back["names"]
            rei_npc = next(e for e in view_back["entities"] if e["name"] == "레이")
            assert not rei_npc["persona"]
            loc_back = {f["subject_entity"]["id"]: f["object"] for f in view_back["facts"]
                        if f["predicate"] == "located_in"}
            assert loc_back[persona_back["id"]] == "도서관"
            assert loc_back[rei_npc["id"]] == "성당"


def test_mid_chat_rename_keeps_single_persona_and_branch_and_archive_preserve_turn_persona(migrated: str, tmp_path: Path):
    settings = Settings(database_url=migrated, **LLM)
    with make_client(migrated, **LLM) as client:
        # 1) Mid-chat rename: 카일 -> 아오키 카일 stays one persona
        chat = SimChat("b43-rename")
        chat.user("항구에서 나침반을 챙겼다.")
        chat.reply("카일은 부두를 걸었다.")
        sync(client, chat, persona_name="카일")
        chat.user("등대로 향했다.")
        chat.reply("아오키 카일은 등대 문을 열었다.")
        sync(client, chat, persona_name="아오키 카일")
        chat.user("안으로 들어갔다.")
        out = sync(client, chat, persona_name="아오키 카일")
        head = UUID(out["active_commit"])

        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            key = _extract_all(conn, settings, {
                0: [_a("{{user}}", "possesses", "나침반", object_type="item", evidence="항구에서 나침반을 챙겼다.")],
                1: [_a("아오키 카일", "located_in", "등대", evidence="아오키 카일은 등대 문을 열었다.")],
            })
            view = facts.memory_view(conn, head, key)
            personas = [e for e in view["entities"] if e["persona"]]
            assert len(personas) == 1
            holds = [f for f in view["facts"] if f["predicate"] == "possesses"]
            loc = [f for f in view["facts"] if f["predicate"] == "located_in"]
            assert holds[0]["subject_entity"]["id"] == personas[0]["id"]
            assert loc[0]["subject_entity"]["id"] == personas[0]["id"]

        # 2) Branch inheritance preserves per-turn persona_name on the prefix even if branch syncs under a new persona
        br = chat.branch(len(chat.messages) - 1, name="b43-branch")
        out_br = sync(client, br, persona_name="아오키 카일")
        br_head = UUID(out_br["active_commit"])
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            br_revs = conn.execute(
                "SELECT am.position, sr.persona_name FROM active_membership am"
                " JOIN source_revision sr ON sr.id = am.source_revision_id"
                " WHERE am.commit_id = %s ORDER BY am.position",
                (br_head,),
            ).fetchall()
            # First two messages came from turn 0 where origin had persona_name = '카일'
            assert [r["persona_name"] for r in br_revs[:2]] == ["카일", "카일"]
            assert [r["persona_name"] for r in br_revs[2:]] == ["아오키 카일"] * 4

        # 3) Archive export/restore round-trips persona_name
        arc = str(tmp_path / "b43.zip")
        archive.export_file(migrated, arc)
        with zipfile.ZipFile(arc) as zf:
            sr_entry = next(n for n in zf.namelist() if n.endswith("source_revision.jsonl"))
            sr_text = zf.read(sr_entry).decode("utf-8")
            assert "카일" in sr_text and "아오키 카일" in sr_text
        with psycopg.connect(migrated) as conn:
            conn.execute("TRUNCATE conversation CASCADE")
            conn.commit()
        archive.restore_file(migrated, arc)
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            restored = conn.execute(
                "SELECT count(*) AS n FROM source_revision WHERE persona_name = '카일'"
            ).fetchone()
            assert restored["n"] == 4  # origin (2) + branch (2) both preserved through export/restore
