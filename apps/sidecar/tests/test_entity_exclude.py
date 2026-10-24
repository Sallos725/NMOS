"""PHASE-47: the owner leaves a name out of the cast (`cast`: every fact stays) or out of memory (`memory`: its own
facts and the standing it is one end of leave too). Owner input applied at read time: a joined name follows, a replay
reads what was in force then, undo restores. Synthetic names only (a party of two, a monster and a game-master bot)."""

from __future__ import annotations

from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row

from conftest import active_generation, make_client
from nmos_sidecar import inspector
from nmos_sidecar.facts import memory_view
from simchat import SimChat
from test_extraction import drain
from test_generations import LLM, conv_id
from test_sidecar_integration import sync

USED = {"calls": 1, "input": 100, "output": 10}
TURN = "The party camps at the village. SYSTEM-GM announces a quest. Gloomfang attacks; Hana slays it."
STAND = ("relationship", "role_toward", "feels_toward", "addresses")


def fact(subject, predicate, value=None, obj=None, obj_type=None, **kw):
    return {"subject": subject, "subject_type": "character", "predicate": predicate, "object": obj,
            "object_type": obj_type, "value": value, "polarity": "positive", "modality": "actual",
            "source": "narration", "evidence": "", **kw}


def complete(system, user):
    if TURN not in user.split("TARGET turn", 1)[-1]:
        return {"assertions": []}, "{}", USED
    return {"assertions": [
        fact("Hana", "relationship", "childhood friend", "Kaito", "character"),
        fact("SYSTEM-GM", "role_toward", "game master", "Hana", "character"),
        fact("SYSTEM-GM", "has_status", "online"),
        fact("Gloomfang", "event", "attacks the village", salience="major"),
        fact("Hana", "event", "slays Gloomfang", salience="major", **{"with": [{"name": "Gloomfang", "type": "character"}]}),
        fact("Kaito", "feels_toward", "dread", "Gloomfang", "character"),
        fact("Hana", "located_in", None, "village", "place"),
    ]}, "{}", USED


def view(url: str, cid: str, known_at=None) -> dict:
    with psycopg.connect(url, row_factory=dict_row) as conn:
        head = conn.execute("SELECT head_commit_id FROM conversation WHERE id = %s", (cid,)).fetchone()["head_commit_id"]
        return memory_view(conn, head, active_generation(conn, "extract").key, known_at=known_at)


def exclude(c, cid, item, scope="cast", **kw):
    return c.post(f"/v1/conversations/{cid}/repairs", json={"kind": "entity_exclude", "item": item, "scope": scope, **kw})


def setup(c, migrated) -> str:
    sim = SimChat()
    sim.user("We set out.")
    sim.reply(TURN)
    sim.user("Go on.")
    sync(c, sim, character_name="Hana", persona_name="Rowan")
    drain(migrated, complete)
    return conv_id(c, sim)


def ids(v: dict) -> set:
    return {f["id"] for f in v["facts"]}


def standing(v: dict) -> list:
    return [f for f in v["facts"] if f["predicate"] in STAND]


def test_cast_leaves_the_people_and_pairs_and_keeps_every_fact(migrated):
    with make_client(migrated, **LLM) as c:
        cid = setup(c, migrated)
        before = view(migrated, cid)
        assert {"Hana", "Kaito", "SYSTEM-GM", "Gloomfang"} <= {e["name"] for e in before["entities"]}
        assert exclude(c, cid, "Gloomfang").status_code == 200
        after = view(migrated, cid)
        assert ids(after) == ids(before)  # every fact stays, the monster's own event among them
        gone = next(e for e in after["entities"] if e["name"] == "Gloomfang")
        assert gone["excluded"] == "cast" and after["excluded"][str(gone["id"])]["scope"] == "cast"
        assert len(inspector.pairs(standing(after))) == 3
        left = inspector.pairs(standing(after), frozenset(after["excluded"]))
        assert len(left) == 2 and all(str(gone["id"]) not in {str(i) for i in p["ids"]} for p in left)
        mode = c.get(f"/v1/conversations/{cid}/memory-mode").json()["characters"]
        assert "Gloomfang" not in mode and "Kaito" in mode  # not offered as a character
        page = c.get(f"/inspector/c/{cid}/e/{gone['id']}", params={"lang": "en"}).text
        assert "marked not a character" in page and 'data-repair="entity_exclude' not in page
        kaito = next(e for e in after["entities"] if e["name"] == "Kaito")
        assert f'data-repair="entity_exclude:{kaito["id"]}:Kaito"' in c.get(f"/inspector/c/{cid}/e/{kaito['id']}").text
        detail = c.get(f"/inspector/c/{cid}").text  # the pair rows offer it for each end but the persona
        assert f'data-repair="entity_exclude:{kaito["id"]}:Kaito"' in detail and "entity_exclude:" in detail


def test_memory_also_drops_its_own_facts_and_standing_but_not_anothers_event(migrated):
    with make_client(migrated, **LLM) as c:
        cid = setup(c, migrated)
        assert exclude(c, cid, "SYSTEM-GM", "memory").status_code == 200
        assert exclude(c, cid, "Gloomfang", "memory").status_code == 200
        v = view(migrated, cid)
        said = {(f["subject"], f["predicate"]) for f in v["facts"]}
        assert ("SYSTEM-GM", "has_status") not in said and ("SYSTEM-GM", "role_toward") not in said
        assert ("Gloomfang", "event") not in said and ("Kaito", "feels_toward") not in said  # its standing too
        assert ("Hana", "event") in said and ("Hana", "relationship") in said  # Hana's slaying of it stays
        listed = c.get(f"/v1/conversations/{cid}/repairs").json()["repairs"]
        assert sorted(r["hidden"] for r in listed if r["kind"] == "entity_exclude") == [2, 2]


def test_guards(migrated):
    with make_client(migrated, **LLM) as c:
        cid = setup(c, migrated)
        for item, why in (("Rowan", "persona"), ("Nobody", "not mentioned"), ("Hana", "own character")):
            res = exclude(c, cid, item)
            assert res.status_code == 422 and why in res.json()["detail"], (item, res.text)
        assert exclude(c, cid, "Kaito").status_code == 200
        again = exclude(c, cid, "Kaito", "memory")
        assert again.status_code == 422 and "already" in again.json()["detail"]
        bad = exclude(c, cid, "Kaito", "all")
        assert bad.status_code == 422


def test_preview_counts_both_scopes_and_the_fingerprint_guards_the_action(migrated):
    with make_client(migrated, **LLM) as c:
        cid = setup(c, migrated)
        p = c.post(f"/v1/conversations/{cid}/repairs/preview",
                   json={"kind": "entity_exclude", "item": "SYSTEM-GM"}).json()
        assert p["scope"] == "cast" and p["scopes"]["cast"] == {"pairs": 1, "facts": 0}
        assert p["scopes"]["memory"] == {"pairs": 1, "facts": 2} and p["changes"]
        stale = exclude(c, cid, "SYSTEM-GM", "memory", expect=p["fingerprint"])  # the cast preview's, not memory's
        assert stale.status_code == 409
        m = c.post(f"/v1/conversations/{cid}/repairs/preview",
                   json={"kind": "entity_exclude", "item": "SYSTEM-GM", "scope": "memory"}).json()
        done = exclude(c, cid, "SYSTEM-GM", "memory", expect=m["fingerprint"])
        assert done.status_code == 200 and done.json()["applied"]
        rid = done.json()["repair"]["id"]
        undo = c.post(f"/v1/conversations/{cid}/repairs/{rid}/remove/preview").json()
        assert undo["action"] == "unexclude" and undo["scopes"]["memory"]["facts"] == 2
        assert c.post(f"/v1/conversations/{cid}/repairs/{rid}/remove", json={"expect": undo["fingerprint"]}).status_code == 200
        assert ("SYSTEM-GM", "has_status") in {(f["subject"], f["predicate"]) for f in view(migrated, cid)["facts"]}


def test_undo_restores_and_a_replay_reads_what_was_in_force(migrated):
    with make_client(migrated, **LLM) as c:
        cid = setup(c, migrated)
        before = view(migrated, cid)
        at = datetime.now(timezone.utc)
        rid = exclude(c, cid, "Gloomfang", "memory").json()["repair"]["id"]
        assert ids(view(migrated, cid)) != ids(before)
        then = view(migrated, cid, known_at=at)
        assert ids(then) == ids(before) and not then["excluded"]
        assert c.post(f"/v1/conversations/{cid}/repairs/{rid}/remove").status_code == 200
        assert ids(view(migrated, cid)) == ids(before) and not view(migrated, cid)["excluded"]


def test_an_entity_named_by_its_id_is_stored_by_its_name_and_survives_a_rebuild(migrated):
    from nmos_sidecar.rebuild import rebuild_all
    with make_client(migrated, **LLM) as c:
        cid = setup(c, migrated)
        gloom = next(e for e in view(migrated, cid)["entities"] if e["name"] == "Gloomfang")
        out = exclude(c, cid, str(gloom["id"])).json()
        assert out["repair"]["target"] == {"entity_type": "character", "name": "Gloomfang", "scope": "cast"}
        rebuild_all(migrated)
        drain(migrated, complete)
        assert any(e["name"] == "Gloomfang" and e.get("excluded") == "cast" for e in view(migrated, cid)["entities"])


def test_without_an_exclusion_the_view_is_unchanged(migrated):
    """Nothing in force: the view carries an empty `excluded` and no entity is marked (identity with main)."""
    with make_client(migrated, **LLM) as c:
        cid = setup(c, migrated)
        v = view(migrated, cid)
        assert v["excluded"] == {} and not any("excluded" in e for e in v["entities"])


def test_the_person_sheet_offers_it_and_says_when_it_is_marked(migrated):
    with make_client(migrated, **LLM) as c:
        cid = setup(c, migrated)
        ents = {e["name"]: e for e in view(migrated, cid)["entities"]}
        sheet = c.get(f"/v1/views/c/{cid}/person/{ents['Gloomfang']['id']}").json()["html"]
        assert f'data-repair="entity_exclude:{ents["Gloomfang"]["id"]}:Gloomfang"' in sheet
        persona = next((e for e in ents.values() if e.get("persona")), None)
        if persona is not None:
            assert "entity_exclude" not in c.get(f"/v1/views/c/{cid}/person/{persona['id']}").json()["html"]
        exclude(c, cid, "Gloomfang")
        sheet = c.get(f"/v1/views/c/{cid}/person/{ents['Gloomfang']['id']}").json()["html"]
        assert "entity_exclude" not in sheet and "캐릭터 아님으로 표시됨" in sheet


def test_cast_takes_its_cast_group_out_of_the_packet_and_keeps_every_fact_line(migrated):
    """Acceptance 2: its <Character> group goes; its facts are still told, word for word, in <Facts>."""
    import re
    from test_sidecar_integration import recall
    with make_client(migrated, **LLM) as c:
        sim = SimChat()
        sim.user("We set out.")
        sim.reply(TURN)
        sim.user("What does SYSTEM-GM say now?")
        sync(c, sim, character_name="Hana", persona_name="Rowan")
        drain(migrated, complete)
        cid = conv_id(c, sim)

        def packet():
            return recall(c, sim, "What does SYSTEM-GM say now?", budget=2000)["packet"]["text"]

        before = packet()
        exclude(c, cid, "SYSTEM-GM")
        after = packet()
    facts = lambda t: sorted(re.findall(r"<Fact [^>]*>[^<]*</Fact>", t))  # noqa: E731
    assert '<Character name="SYSTEM-GM">' in before and '<Character name="SYSTEM-GM">' not in after
    assert facts(after) == facts(before) and "SYSTEM-GM has status: online" in after
