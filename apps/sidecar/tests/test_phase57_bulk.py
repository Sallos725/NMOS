"""PHASE-57 B1 and B2 (ADR 0080): Needs attention applied or retracted in bulk, one batch written in one transaction
or none, undone together; a conflicting statement corrected from its row, canon's kept as corrected."""

from __future__ import annotations

import html
import json
import re

from conftest import make_client
from test_canon import push
from test_canon_facts import Model, canon_texts, current, drain, story, view
from test_generations import LLM
from test_sidecar_integration import sync


def conflicted(migrated, c):
    """A chat whose story contradicts its card on how Hana and Kaito stand (ADR 0047): one canon conflict listed."""
    chat, model = story(), Model()
    sync(c, chat)
    push(c, chat, canon_texts())
    drain(migrated, model)
    chat.reply("Hana is Kaito's rival.")
    chat.user("How are Hana and Kaito?")
    sync(c, chat)
    drain(migrated, model)
    v = view(migrated, chat)
    (listed,) = [x for x in v["conflicts"] if x["kind"] == "canon"]
    return chat, v["conversation"], listed


def attention(c, cid) -> str:
    page = c.get(f"/inspector/c/{cid}", params={"lang": "en"}).text
    start = page.index('id="s-attention"')
    return page[start:page.index("</details>", start)]


def bulk_marks(section: str) -> list[dict]:
    return [json.loads(html.unescape(m)) for m in re.findall(r'class="rq" data-bulk="([^"]*)"', section)]


def test_a_row_says_what_apply_and_retract_send_and_offers_both_corrections(migrated):
    with make_client(migrated, **LLM) as c:
        _, cid, listed = conflicted(migrated, c)
        section = attention(c, cid)
        canon_id = str(listed["against"]["id"])
        assert bulk_marks(section) == [{"g": "canon", "l": "Conflicts with the setting",
                                        "apply": {"kind": "fact_lock", "item": canon_id},
                                        "retract": {"kind": "fact_retract", "item": canon_id}}]
        # a relationship is corrected in its counterpart or its value: canon's (kept, locked) and the story's
        for field in ("object", "value"):
            assert f'data-repair="fact_correct:{canon_id}:{field}.lock"' in section
            assert f'data-repair="fact_correct:{listed["fact"]}:{field}"' in section


def test_a_batch_is_previewed_written_at_once_and_undone_together(migrated, db):
    with make_client(migrated, **LLM) as c:
        chat, cid, listed = conflicted(migrated, c)
        canon_id = str(listed["against"]["id"])
        body = {"items": [{"kind": "fact_lock", "item": canon_id}]}
        out = c.post(f"/v1/conversations/{cid}/repairs/batch", json={**body, "preview": True}).json()
        assert out["counts"] == {"fact_lock": 1} and out["errors"] == 0 and "batch" not in out
        assert c.get(f"/v1/conversations/{cid}/repairs").json()["repairs"] == []  # a preview writes nothing
        out = c.post(f"/v1/conversations/{cid}/repairs/batch", json=body).json()
        reps = c.get(f"/v1/conversations/{cid}/repairs").json()["repairs"]
        assert [(r["kind"], r["batch_id"]) for r in reps] == [("fact_lock", out["batch"])]
        assert [f["value"] for f in current(view(migrated, chat), "Hana", "relationship")] == ["sister"]
        assert bulk_marks(attention(c, cid)) == []  # settled: the row is gone
        page = c.get(f"/inspector/c/{cid}", params={"lang": "en"}).text
        assert "1 repairs at once" in page and f'data-repair="undo_batch:{out["batch"]}"' in page
        assert c.post(f"/v1/conversations/{cid}/repairs/batch/{out['batch']}/remove").json() == {"removed": 1}
        assert [f["value"] for f in current(view(migrated, chat), "Hana", "relationship")] == ["rival"]
        assert c.post(f"/v1/conversations/{cid}/repairs/batch/{out['batch']}/remove").status_code == 404


def test_one_refused_item_writes_none(migrated):
    with make_client(migrated, **LLM) as c:
        _, cid, listed = conflicted(migrated, c)
        canon_id = str(listed["against"]["id"])
        good = {"kind": "fact_lock", "item": canon_id}
        for bad in ({"kind": "fact_restore", "item": "999999"},  # nothing dropped by that id
                    {"kind": "name_split", "item": "Hana", "other": "Kaito"},  # one at a time, from its preview
                    good):  # the same repair twice
            res = c.post(f"/v1/conversations/{cid}/repairs/batch", json={"items": [good, bad]})
            assert res.status_code == 422, bad
            plan = res.json()["detail"]["plan"]
            assert "error" not in plan[0] and "error" in plan[1]
            assert c.get(f"/v1/conversations/{cid}/repairs").json()["repairs"] == []
        preview = c.post(f"/v1/conversations/{cid}/repairs/batch", json={"items": [good, good], "preview": True})
        assert preview.status_code == 200 and preview.json()["errors"] == 1  # a preview says which, and writes none
        too_many = c.post(f"/v1/conversations/{cid}/repairs/batch", json={"items": [good] * 201})
        assert too_many.status_code == 422
        assert c.post(f"/v1/conversations/{cid}/repairs/batch", json={}).status_code == 422


def test_a_batch_takes_repairs_back_and_each_of_a_batch_is_undone_on_its_own(migrated):
    with make_client(migrated, **LLM) as c:
        chat, cid, listed = conflicted(migrated, c)
        canon_id = str(listed["against"]["id"])
        single = c.post(f"/v1/conversations/{cid}/repairs", json={"kind": "fact_retract", "item": canon_id}).json()
        rid = single["repair"]["id"]
        out = c.post(f"/v1/conversations/{cid}/repairs/batch", json={"undo": [rid]}).json()
        assert out["counts"] == {"undo": 1}
        assert [r["removed_at"] is not None for r in c.get(f"/v1/conversations/{cid}/repairs").json()["repairs"]] == [True]
        again = c.post(f"/v1/conversations/{cid}/repairs/batch", json={"undo": [rid]})
        assert again.status_code == 422 and again.json()["detail"]["plan"][0]["error"] == "taken back already"
        out = c.post(f"/v1/conversations/{cid}/repairs/batch", json={"items": [{"kind": "fact_lock", "item": canon_id}]})
        lock = next(r for r in c.get(f"/v1/conversations/{cid}/repairs").json()["repairs"] if r["kind"] == "fact_lock")
        assert c.post(f"/v1/conversations/{cid}/repairs/{lock['id']}/remove").status_code == 200  # one of a batch
        assert [f["value"] for f in current(view(migrated, chat), "Hana", "relationship")] == ["rival"]


def test_correcting_canons_statement_keeps_it_locked_and_the_storys_to_agree_settles_the_row(migrated):
    with make_client(migrated, **LLM) as c:
        chat, cid, listed = conflicted(migrated, c)
        canon_id = str(listed["against"]["id"])
        alone = c.post(f"/v1/conversations/{cid}/repairs",
                       json={"kind": "fact_correct", "item": canon_id, "new_value": "elder sister"})
        assert alone.status_code == 422  # it would be replaced by the story's at once
        res = c.post(f"/v1/conversations/{cid}/repairs",
                     json={"kind": "fact_correct", "item": canon_id, "new_value": "elder sister", "lock": True})
        assert res.status_code == 200, res.text
        v = view(migrated, chat)
        (rel,) = current(v, "Hana", "relationship")
        assert (rel["value"], bool(rel.get("owner")), bool(rel.get("locked")), rel["held_off"]) == ("elder sister", True,
                                                                                                    True, 1)
        kinds = sorted(r["kind"] for r in c.get(f"/v1/conversations/{cid}/repairs").json()["repairs"])
        assert kinds == ["fact_correct", "fact_lock"]
        assert bulk_marks(attention(c, cid)) == []
        assert c.post(f"/v1/conversations/{cid}/repairs",
                      json={"kind": "fact_lock", "item": canon_id, "lock": True}).status_code == 422
    with make_client(migrated, **LLM) as c:  # another chat: the story's statement corrected to agree with canon's
        chat2 = story()
        chat2.id = "canon-facts-2"
        model = Model()
        sync(c, chat2)
        push(c, chat2, canon_texts())
        drain(migrated, model)
        chat2.reply("Hana is Kaito's rival.")
        chat2.user("How are Hana and Kaito?")
        sync(c, chat2)
        drain(migrated, model)
        v = view(migrated, chat2)
        (listed2,) = [x for x in v["conflicts"] if x["kind"] == "canon"]
        res = c.post(f"/v1/conversations/{v['conversation']}/repairs",
                     json={"kind": "fact_correct", "item": str(listed2["fact"]), "new_value": "sister"})
        assert res.status_code == 200, res.text
        v = view(migrated, chat2)
        assert [x for x in v["conflicts"] if x["kind"] == "canon"] == []
        assert [f["value"] for f in current(v, "Hana", "relationship")] == ["sister"]
