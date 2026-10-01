"""Phase 22 (docs/phases/PHASE-22.md, Q5–Q7): facts a re-extraction dropped, and the owner's restore of one.

AGE-25's case on a synthetic chat: a turn's narrated occupation, gone after the turn is extracted again. Synthetic names
only."""

from __future__ import annotations

from conftest import make_client
from memeval import stub_extractor
from nmos_sidecar.repairs import restated
from simchat import SimChat
from test_extraction import drain
from test_generations import LLM, conv_id
from test_repairs import memory, packet, repair
from test_sidecar_integration import sync


def forgetful(system: str, user: str) -> tuple[dict, str]:
    """A second call that leaves out an occupation stated in a turn "today" (the first call found it)."""
    out, raw = stub_extractor(system, user)
    target = user.split("TARGET", 1)[1]
    return {**out, "assertions": [a for a in out["assertions"]
                                  if not (a["predicate"] == "identity" and "today" in target)]}, raw


def chat_of(*lines: str) -> SimChat:
    chat = SimChat()
    for text in lines:
        chat.user(text)
        chat.reply("Noted.")
    chat.user("Go on.")  # the last turn is extracted once the user continues from it (ADR 0008)
    return chat


def damaged(c, migrated, chat: SimChat) -> str:
    """The chat as AGE-25 found it: extracted once, then rebuilt by a call that dropped the occupation."""
    sync(c, chat)
    drain(migrated, stub_extractor)
    cid = conv_id(c, chat)
    assert "Hana identity: knight" in memory(packet(c, chat, "What is Hana?"))
    assert c.post(f"/v1/conversations/{cid}/rebuild").status_code == 200
    drain(migrated, forgetful)
    return cid


def dropped(c, cid: str) -> list[dict]:
    res = c.get(f"/v1/conversations/{cid}/dropped")
    assert res.status_code == 200, res.text
    return res.json()


def test_age25_end_to_end_dropped_listed_restored_in_the_packet_and_undone(migrated):
    chat = chat_of("Kaito is in the harbor.", "Hana is in the chapel. Hana is a knight. It is today.",
                   "Kaito is in the garden.")
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = damaged(c, migrated, chat)
        assert "knight" not in memory(packet(c, chat, "What is Hana?"))
        (lost,) = dropped(c, cid)  # the place was stated again; only the occupation is gone
        assert (lost["subject"], lost["predicate"], lost["value"], lost["turn"]) == ("Hana", "identity", "knight", 1)
        page = c.get(f"/inspector/c/{cid}", params={"lang": "en"}).text
        assert "dropped by a re-extraction" in page and f'data-repair="fact_restore:{lost["id"]}"' in page
        assert c.get(f"/v1/conversations/{cid}/coverage", params={"usage": "true"}).json()["dropped"] == 1
        # Restore: the owner's version at its turn, in the packet, and no longer listed.
        out = repair(c, cid, kind="fact_restore", item=str(lost["id"]))
        assert out["applied"] is not None and out["repair"]["target"]["fact"]["value"] == "knight"
        assert "Hana identity: knight" in memory(packet(c, chat, "What is Hana?"))
        (fact,) = [f for f in c.get(f"/v1/conversations/{cid}/facts").json() if f["predicate"] == "identity"]
        assert fact["owner"] is True and fact["turn"] == 1
        assert dropped(c, cid) == []
        # Undo: gone again, and listed again.
        assert c.post(f"/v1/conversations/{cid}/repairs/{out['repair']['id']}/remove").status_code == 200
        assert "knight" not in memory(packet(c, chat, "What is Hana?"))
        assert [d["value"] for d in dropped(c, cid)] == ["knight"]


def test_a_restore_matches_nothing_after_an_edit_and_steps_aside_when_the_story_states_it_again(migrated):
    chat = chat_of("Kaito is in the harbor.", "Hana is a knight. It is today.", "Kaito is in the garden.")
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = damaged(c, migrated, chat)
        (lost,) = dropped(c, cid)
        rid = repair(c, cid, kind="fact_restore", item=str(lost["id"]))["repair"]["id"]
        # A rebuild that finds the occupation again: the restore applies to the story's row, adds no second one.
        assert c.post(f"/v1/conversations/{cid}/rebuild").status_code == 200
        drain(migrated, stub_extractor)
        identities = [f for f in c.get(f"/v1/conversations/{cid}/facts").json() if f["predicate"] == "identity"]
        assert [(f["value"], f.get("owner")) for f in identities] == [("knight", None)]
        (applied,) = [x["applied"] for x in c.get(f"/v1/conversations/{cid}/repairs").json()["repairs"] if x["id"] == rid]
        assert applied == str(identities[0]["id"])
        # An edit of the turn: the restore matches nothing (it was about what the turn said then).
        chat.edit(2, "Hana is a baker. It is today.")
        sync(c, chat)
        drain(migrated, stub_extractor)
        (applied,) = [x["applied"] for x in c.get(f"/v1/conversations/{cid}/repairs").json()["repairs"] if x["id"] == rid]
        assert applied is None
        assert [f["value"] for f in c.get(f"/v1/conversations/{cid}/facts").json() if f["predicate"] == "identity"] \
            == ["baker"]


def test_a_fact_held_by_another_turn_or_another_generation_is_not_listed(migrated):
    chat = chat_of("Hana is a knight.", "Hana is a knight. It is today.", "Kaito is in the garden.")
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = damaged(c, migrated, chat)
        assert dropped(c, cid) == []  # turn 0 still says it
    # A new extractor generation is not compared (Q5): its extractions replace none of the same generation.
    chat2 = chat_of("Kaito is in the harbor.", "Hana is a knight. It is today.")
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        sync(c, chat2)
        drain(migrated, stub_extractor)
        cid2 = conv_id(c, chat2)
    with make_client(migrated, extract_backfill=100, llm_url=LLM["llm_url"], llm_model="fake-2") as c:
        drain(migrated, forgetful)
        assert dropped(c, cid2) == []


def row(subject: str, predicate: str, obj: str | None = None, value: str | None = None, quote: str = "") -> dict:
    return {"subject": subject, "subject_type": "character", "predicate": predicate, "object": obj,
            "object_type": "item" if obj else None, "value": value, "evidence": quote}


def test_one_quote_restates_only_the_fact_the_new_extraction_states():
    """Review 2026-10-01 (Q5): a shared quote alone never restates another character's fact, and one row restates one."""
    both = "Hana is a teacher and Kaito is a doctor."
    old = [row("Hana", "identity", value="teacher", quote=both), row("Kaito", "identity", value="doctor", quote=both)]
    assert set(restated(old, [row("Kaito", "identity", value="doctor", quote=both)], None)) == {1}
    pair = "Ren carries a sword and a shield."
    old = [row("Ren", "possesses", "sword", quote=pair), row("Ren", "possesses", "shield", quote=pair)]
    assert set(restated(old, [row("Ren", "possesses", "shield", quote=pair)], None)) == {1}
    # The object worded otherwise, the same quote: stated again (level 3).
    assert set(restated([row("Ren", "possesses", "old sword", quote=pair)],
                        [row("Ren", "possesses", "sword", quote=pair)], None)) == {0}
    # An accumulating fact with a new value: still the same predicate, subject and object (level 2).
    assert set(restated([row("Ren", "has_trait", value="brave")], [row("Ren", "has_trait", value="bold")], None)) == {0}


def claimed(system: str, user: str) -> tuple[dict, str]:
    """A second call that words the occupation as the character's own claim, not as narration."""
    out, raw = stub_extractor(system, user)
    target = user.split("TARGET", 1)[1]
    return {**out, "assertions": [{**a, "source": "character_claim", "asserted_by": a["subject"]}
                                  if a["predicate"] == "identity" and "today" in target else a
                                  for a in out["assertions"]]}, raw


def test_a_claim_or_a_plan_restates_no_fact(migrated):
    """Copilot review of #216: a character's claim, a plan or a dream does not state how things stand (memory_view puts
    them in claims and other), so it neither hides a drop nor makes a restore step aside."""
    old = [row("Hana", "identity", value="knight")]
    for change in ({"source": "character_claim", "asserted_by": "Hana"}, {"modality": "hypothetical"},
                   {"modality": "dreamed"}):
        assert restated(old, [{**row("Hana", "identity", value="knight"), **change}], None) == {}
    chat = chat_of("Kaito is in the harbor.", "Hana is a knight. It is today.", "Kaito is in the garden.")
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        sync(c, chat)
        drain(migrated, stub_extractor)
        cid = conv_id(c, chat)
        assert c.post(f"/v1/conversations/{cid}/rebuild").status_code == 200
        drain(migrated, claimed)
        (lost,) = dropped(c, cid)
        assert lost["value"] == "knight"
        out = repair(c, cid, kind="fact_restore", item=str(lost["id"]))
        assert out["applied"] is not None and "Hana identity: knight" in memory(packet(c, chat, "What is Hana?"))
        assert [f["owner"] for f in c.get(f"/v1/conversations/{cid}/facts").json() if f["predicate"] == "identity"] \
            == [True]


def test_a_restore_survives_an_archive_and_its_restore(migrated, database_url_factory, tmp_path):
    """ADR 0050: the owner's repair, with its nested target, comes back with the chat and applies the same."""
    from nmos_sidecar import archive

    chat = chat_of("Kaito is in the harbor.", "Hana is a knight. It is today.", "Kaito is in the garden.")
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        cid = damaged(c, migrated, chat)
        (lost,) = dropped(c, cid)
        repair(c, cid, kind="fact_restore", item=str(lost["id"]))
        before = memory(packet(c, chat, "What is Hana?"))
        assert "Hana identity: knight" in before
    source = tmp_path / f"a{archive.SUFFIX}"
    archive.export_file(migrated, str(source))
    target = database_url_factory()
    archive.restore_file(target, str(source))
    with make_client(target, **LLM, extract_backfill=100) as c:
        assert memory(packet(c, chat, "What is Hana?")) == before
        assert dropped(c, cid) == []
        (rep,) = c.get(f"/v1/conversations/{cid}/repairs").json()["repairs"]
        assert rep["kind"] == "fact_restore" and rep["applied"] is not None
