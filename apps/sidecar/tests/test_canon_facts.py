"""Canon facts (Phase 14 step 5, PHASE-14 Q3–Q5 and Q7, ADR 0047): what the model reads from the canon and when, canon
facts before turn 0 that the story supersedes, conflicts listed with the owner's choices, the lock and its undo, what
reaches the packet, and replays."""

from __future__ import annotations

import re

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from conftest import active_generation, make_client
from nmos_sidecar import canon, canonfacts
from nmos_sidecar.extraction import normalize, process_extract
from nmos_sidecar.facts import memory_view
from nmos_sidecar.llm import LLMError
from nmos_sidecar.worker import run_once
from simchat import SimChat
from test_canon import push
from test_generations import LLM
from test_sidecar_integration import recall, sync

RULES = [
    (re.compile(r"(?P<who>[A-Z]\w+) is a (?P<what>[a-z ]+?)\."),
     lambda m: {"subject": m["who"], "subject_type": "character", "predicate": "identity", "value": m["what"]}),
    (re.compile(r"(?P<who>[A-Z]\w+) is in the (?P<where>[a-z ]+?)\."),
     lambda m: {"subject": m["who"], "subject_type": "character", "predicate": "located_in", "object": m["where"],
                "object_type": "place"}),
    (re.compile(r"(?P<a>[A-Z]\w+) is (?P<b>[A-Z]\w+)'s (?P<rel>[a-z]+)\."),
     lambda m: {"subject": m["a"], "subject_type": "character", "predicate": "relationship", "object": m["b"],
                "object_type": "character", "value": m["rel"]}),
    (re.compile(r"(?P<who>[A-Z]\w+) wants to (?P<what>[^.]+)\."),
     lambda m: {"subject": m["who"], "subject_type": "character", "predicate": "goal", "value": m["what"]}),
    (re.compile(r"(?P<who>[A-Z]\w+) has the (?P<what>[a-z]+)\."),
     lambda m: {"subject": m["who"], "subject_type": "character", "predicate": "possesses", "object": m["what"],
                "object_type": "item"}),
]


class Model:
    """Stand-in for the extraction model, for turns and canon alike; it records each call, and fails a call whose
    prompt has `fail_on`."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.fail_on: str | None = None

    def __call__(self, system: str, user: str) -> tuple[dict, str]:
        is_canon = "CANON" in system
        if self.fail_on and self.fail_on in user:
            raise LLMError("model unavailable")
        self.calls.append(("canon" if is_canon else "turn", user))
        text = user.split("TEXT", 1)[1] if is_canon else user.split("TARGET", 1)[1]
        items = [{"modality": "actual", "source": "narration", "epistemic": "stated", "confidence": 0.9,
                  "evidence": m.group(0), "knowledge": "unknown", **build(m)}
                 for pattern, build in RULES for m in pattern.finditer(text)]
        return {"assertions": items}, "{}"

    def canon_calls(self) -> list[str]:
        return [u for kind, u in self.calls if kind == "canon"]


def drain(url: str, model: Model) -> int:
    n = 0
    with psycopg.connect(url, row_factory=dict_row, autocommit=True) as conn:
        ex, cg = active_generation(conn, "extract"), active_generation(conn, "canon")
        jobs = {"extract": (ex.key, lambda cn, job: process_extract(cn, job, model, ex, ex.spec["context_turns"])),
                "canon": (cg.key, lambda cn, job: canonfacts.process(cn, job, model, cg))}
        while run_once(conn, jobs):
            n += 1
    return n


def view(url: str, chat: SimChat) -> dict:
    with psycopg.connect(url, row_factory=dict_row) as conn:
        conv = conn.execute("SELECT id, head_commit_id FROM conversation WHERE host_chat_ref = %s", (chat.id,)).fetchone()
        ex, cg = active_generation(conn, "extract"), active_generation(conn, "canon")
        return {**memory_view(conn, conv["head_commit_id"], ex.key, canon_key=cg.key), "conversation": conv["id"]}


def current(v: dict, subject: str, predicate: str) -> list[dict]:
    return [f for f in v["facts"] if f["subject"] == subject and f["predicate"] == predicate]


CARD = ("{{char}} is a lighthouse keeper. {{char}} is in the harbor town. {{char}} is Kaito's sister. "
        "{{char}} wants to find the drowned bell. Always reply in three paragraphs.")


def canon_texts(desc: str = CARD) -> dict:
    return {"card:name": ("Hana", {"field": "name"}), "card:desc": (desc, {"field": "desc"}),
            "persona": ("{{user}} is a traveler.", {"name": "Taku"}),
            "lore:kaito": ("Kaito is a squire.", {"keys": ["Kaito"], "scope": "character", "mode": "normal"}),
            "lore:mira": ("Mira is a baker.", {"keys": ["Mira"], "scope": "character", "mode": "normal"})}


def story() -> SimChat:
    chat = SimChat("canon-facts")
    chat.user("We walk to the mill.")
    chat.reply("Hana is in the old mill.")
    chat.user("And then?")
    chat.reply("Hana is a smuggler.")
    chat.user("What does Hana do?")
    return chat


def test_parts_names_and_what_canon_may_state():
    text = ("a" * 4000 + "\n\n" + "b" * 4000 + "\n" + "c" * 30000)
    pieces, unread = canonfacts.parts(text)
    assert len(pieces) == canonfacts.MAX_PARTS and all(len(p) <= canonfacts.PART_CHARS for p in pieces)
    assert pieces[:2] == ["a" * 4000, "b" * 4000] and unread == 30000 - 2 * canonfacts.PART_CHARS
    assert canonfacts.named("{{char}} meets {{ User }}; {{bot}}.", "Hana", "Taku") == "Hana meets Taku; Hana."
    assert canonfacts.named("{{user}} waits.", "Hana", None) == "{{user}} waits."
    rows = normalize([{"subject": "Hana", "subject_type": "character", "predicate": "goal", "value": "find the bell",
                       "modality": "actual", "source": "narration"}], "Hana wants to find the bell.")
    assert rows[0]["status"] == "valid" and "goal" not in canonfacts.PREDICATES  # process() parks it as pending


def test_the_card_note_and_persona_are_read_at_once_a_lorebook_entry_once_a_prompt_held_it(migrated):
    chat, model = story(), Model()
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        out = push(c, chat, canon_texts())
        drain(migrated, model)
        calls = model.canon_calls()
        assert len(calls) == 2  # card:desc and persona; card:name is a name, lorebook entries wait for a prompt
        desc = next(u for u in calls if "card's description" in u)
        assert "Hana is a lighthouse keeper." in desc and "{{char}}" not in desc  # the host's macros, named
        assert "CHARACTER: Hana" in desc and "USER: Taku" in desc
        # A prompt holds the Kaito entry: read after the answer, off the request's path; Mira's entry never.
        recall(c, chat, "Where is Kaito?", canon_manifest_id=out["manifest_id"], canon_held=["card:desc", "lore:kaito"])
        drain(migrated, model)
        assert len(model.canon_calls()) == 3 and "Kaito is a squire." in model.canon_calls()[-1]
        recall(c, chat, "Where is Kaito?", canon_manifest_id=out["manifest_id"], canon_held=["lore:kaito"])
        drain(migrated, model)
        assert len(model.canon_calls()) == 3  # read once
        cid = view(migrated, chat)["conversation"]
        cov = c.get(f"/v1/conversations/{cid}/coverage").json()["canon"]
        assert (cov["wanted"], cov["read"], cov["calls"], cov["pending"]) == (3, 3, 3, 0)
        assert "lore:mira" not in cov["keys"]
        # A card edit makes a new revision: read again, and the old text's facts leave memory.
        push(c, chat, {**canon_texts(CARD.replace("lighthouse keeper", "ferry pilot"))})
        drain(migrated, model)
        assert len(model.canon_calls()) == 4
        v = view(migrated, chat)
    identity = [f for f in v["assertions"] if f.get("canon") and f["predicate"] == "identity" and f["subject"] == "Hana"]
    assert [f["value"] for f in identity] == ["ferry pilot"]
    goal = [f for f in v["assertions"] if f["predicate"] == "goal"]
    assert goal == []  # open business belongs to the story: parked as pending, never a fact
    with psycopg.connect(migrated, row_factory=dict_row) as conn:
        parked = conn.execute("SELECT reason FROM assertion WHERE predicate = 'goal'").fetchall()
    assert parked and all(r["reason"] == "not a canon predicate" for r in parked)


def test_canon_is_before_turn_0_the_story_supersedes_it_and_a_contradiction_is_listed(migrated):
    chat, model = story(), Model()
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        push(c, chat, canon_texts())
        drain(migrated, model)
        v = view(migrated, chat)
        place = current(v, "Hana", "located_in")
        assert [f["object"] for f in place] == ["old mill"] and place[0]["history"][0]["canon"] == "card:desc"
        assert [f["value"] for f in current(v, "Hana", "identity")] == ["smuggler"]
        assert [f["value"] for f in current(v, "Hana", "relationship")] == ["sister"]
        assert current(v, "Hana", "relationship")[0]["turn"] == -1
        # A place changes as the story goes, and so does who someone is now (ADR 0047 amendment 1): not listed.
        assert [x for x in v["conflicts"] if x["kind"] == "canon"] == []
        # How two stand: listed, with the owner's choices.
        chat.reply("Hana is Kaito's rival.")
        chat.user("How are Hana and Kaito?")
        sync(c, chat)
        drain(migrated, model)
        v = view(migrated, chat)
        assert [f["value"] for f in current(v, "Hana", "relationship")] == ["rival"]
        listed = [x for x in v["conflicts"] if x["kind"] == "canon"]
        assert len(listed) == 1 and listed[0]["against"]["value"] == "sister"
        canon_id = listed[0]["against"]["id"]
        page = c.get(f"/inspector/c/{v['conversation']}", params={"lang": "en"}).text
        attention = page[page.index('id="s-attention"'):page.index("</details>", page.index('id="s-attention"'))]
        assert f'data-repair="fact_lock:{canon_id}"' in attention and f'data-repair="fact_retract:{canon_id}"' in attention
        facts_section = page[page.index('id="s-facts"'):page.index("</details>", page.index('id="s-facts"'))]
        assert "canon" in facts_section and "older generation" not in facts_section  # its own generation, not older

        # Keep canon's: a lock. The canon version stays current, the story's statement is held off and listed.
        res = c.post(f"/v1/conversations/{v['conversation']}/repairs", json={"kind": "fact_lock", "item": str(canon_id)})
        assert res.status_code == 200, res.text
        lock = res.json()["repair"]["id"]
        assert res.json()["applied"] == str(canon_id)
        v = view(migrated, chat)
        (locked,) = current(v, "Hana", "relationship")
        assert (locked["value"], locked["locked"], locked["held_off"]) == ("sister", str(lock), 1)
        assert [x["kind"] for x in v["conflicts"]] == ["locked"] and v["conflicts"][0]["against"]["value"] == "rival"
        # The lock holds in the packet, although the host sent the card (D3 gives way to a lock).
        packet = recall(c, chat, "How are Hana and Kaito?", [m["chatId"] for m in chat.messages], budget=2000,
                        canon_held=["card:desc", "persona"])["packet"]["text"]
        assert 'source="canon" locked="true"' in packet and "sister" in packet and "rival" not in packet
        assert "locked=\"true\" marks a fact the user fixed" in packet and "before the story, from its setting" in packet
        assert c.post(f"/v1/conversations/{v['conversation']}/repairs",
                      json={"kind": "fact_lock", "item": str(canon_id)}).status_code == 422  # locked already

        # Undo: the story's version is current again, and the contradiction is listed again.
        assert c.post(f"/v1/conversations/{v['conversation']}/repairs/{lock}/remove").status_code == 200
        v = view(migrated, chat)
        assert [f["value"] for f in current(v, "Hana", "relationship")] == ["rival"]
        assert [x["kind"] for x in v["conflicts"]] == ["canon"]

        # Keep the story's: canon's statement retracted. Nothing is listed.
        res = c.post(f"/v1/conversations/{v['conversation']}/repairs", json={"kind": "fact_retract", "item": str(canon_id)})
        assert res.status_code == 200 and res.json()["applied"] == str(canon_id)
        v = view(migrated, chat)
        assert [f["value"] for f in current(v, "Hana", "relationship")] == ["rival"] and v["conflicts"] == []


def test_a_story_fact_cannot_be_locked_a_correction_can(migrated):
    chat, model = story(), Model()
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        push(c, chat, canon_texts())
        drain(migrated, model)
        v = view(migrated, chat)
        cid = v["conversation"]
        (place,) = current(v, "Hana", "located_in")
        res = c.post(f"/v1/conversations/{cid}/repairs", json={"kind": "fact_lock", "item": str(place["id"])})
        assert res.status_code == 422 and "canon fact or the owner's correction" in res.text
        res = c.post(f"/v1/conversations/{cid}/repairs", json={"kind": "fact_correct", "item": str(place["id"]),
                                                              "new_object": "mill cellar"})
        assert res.status_code == 200, res.text
        (fixed,) = current(view(migrated, chat), "Hana", "located_in")
        res = c.post(f"/v1/conversations/{cid}/repairs", json={"kind": "fact_lock", "item": str(fixed["id"])})
        assert res.status_code == 200, res.text
        # a later turn moves her: held off by the lock
        chat.reply("Hana is in the chapel.")
        chat.user("Where now?")
        sync(c, chat)
        drain(migrated, model)
        (held,) = current(view(migrated, chat), "Hana", "located_in")
        assert (held["object"], held["held_off"]) == ("mill cellar", 1)


def test_what_reaches_the_packet_and_the_replay(migrated):
    chat, model = story(), Model()
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        out = push(c, chat, canon_texts())
        mid = out["manifest_id"]
        recall(c, chat, "Who is Kaito?", canon_manifest_id=mid, canon_held=["card:desc", "persona", "lore:kaito"])
        drain(migrated, model)
        # The prompt holds the Kaito entry: its fact is not sent again (D3). Without it, the fact is memory.
        held = recall(c, chat, "Who is Kaito?", budget=2000, canon_manifest_id=mid,
                      canon_held=["card:desc", "persona", "lore:kaito"])
        assert "squire" not in held["packet"]["text"]
        free = recall(c, chat, "Who is Kaito?", budget=2000, canon_manifest_id=mid, canon_held=["card:desc", "persona"])
        assert 'kind="identity" source="canon"' in free["packet"]["text"] and "Kaito identity: squire" in free["packet"]["text"]
        # The card's own facts are never sent while the prompt holds the card.
        assert "Hana relationship Kaito: sister" not in free["packet"]["text"]
        replay = c.get(f"/v1/trace/{free['trace_id']}/replay").json()
        assert replay["reproduced"] is True
        # A request from before the canon was read replays without it.
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            first = conn.execute("SELECT id FROM retrieval_trace ORDER BY created_at LIMIT 1").fetchone()["id"]
        assert c.get(f"/v1/trace/{first}/replay").json()["reproduced"] is True


def test_off_means_no_canon_read_or_used(migrated):
    chat, model = story(), Model()
    with make_client(migrated, canon_facts=False, **LLM) as c:
        sync(c, chat)
        push(c, chat, canon_texts())
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            assert conn.execute("SELECT count(*) AS n FROM job WHERE kind = 'canon'").fetchone()["n"] == 0
            assert conn.execute("SELECT count(*) AS n FROM projection_generation WHERE kind = 'canon'").fetchone()["n"] == 0
        page = recall(c, chat, "What does Hana do?", budget=2000)
        assert 'source="canon"' not in page["packet"]["text"]


def test_a_rebuild_reads_the_canon_again(migrated):
    chat, model = story(), Model()
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        push(c, chat, canon_texts())
        drain(migrated, model)
        cid = view(migrated, chat)["conversation"]
        before = len(model.canon_calls())
        out = c.post(f"/v1/conversations/{cid}/rebuild").json()
        assert out["queued"]["canon"] == 2
        drain(migrated, model)
        assert len(model.canon_calls()) == before + 2
        assert [f["value"] for f in current(view(migrated, chat), "Hana", "relationship")] == ["sister"]
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            assert canon.manifest(conn, cid) is not None
        # Deleting the chat takes its canon facts and canon jobs with it (ADR 0009).
        assert c.post(f"/v1/conversations/{cid}/delete").status_code == 200
    with psycopg.connect(migrated, row_factory=dict_row) as conn:
        left = conn.execute("SELECT (SELECT count(*) FROM assertion) + (SELECT count(*) FROM extraction)"
                            " + (SELECT count(*) FROM job) AS n").fetchone()["n"]
        assert left == 0


def test_a_request_whose_manifest_has_not_arrived_reads_no_canon_facts(migrated):
    chat, model = story(), Model()
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        first = push(c, chat, canon_texts())["manifest_id"]
        recall(c, chat, "Who is Kaito?", canon_manifest_id=first, canon_held=["card:desc", "persona", "lore:kaito"])
        drain(migrated, model)
        # The owner deletes the Kaito entry: the next prompt is built from a manifest the sidecar does not have yet.
        texts = {k: v for k, v in canon_texts().items() if k != "lore:kaito"}
        from test_canon import entry
        second = canon.manifest_id([entry(k, t, **m) for k, (t, m) in texts.items()])
        early = recall(c, chat, "Who is Kaito?", budget=2000, canon_manifest_id=second, canon_held=["card:desc", "persona"])
        assert "squire" not in early["packet"]["text"]  # not the removed entry's fact from the canon in force
        push(c, chat, texts)
        after = recall(c, chat, "Who is Kaito?", budget=2000, canon_manifest_id=second, canon_held=["card:desc", "persona"])
        assert "squire" not in after["packet"]["text"]
        for trace in (early, after):
            assert c.get(f"/v1/trace/{trace['trace_id']}/replay").json()["reproduced"] is True
        # while the entry is in force and not in the prompt, its fact is memory
        push(c, chat, canon_texts())
        back = recall(c, chat, "Who is Kaito?", budget=2000, canon_manifest_id=first, canon_held=["card:desc", "persona"])
        assert "squire" in back["packet"]["text"]


def test_a_renamed_card_or_persona_is_read_again_where_the_text_names_them_by_macro(migrated):
    chat, model = story(), Model()
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        out = push(c, chat, {**canon_texts(), "lore:mira": ("Mira is a baker.", {"keys": ["Mira"]})})
        recall(c, chat, "Mira?", canon_manifest_id=out["manifest_id"], canon_held=["lore:mira"])
        drain(migrated, model)
        assert len(model.canon_calls()) == 3
        renamed = {**canon_texts(), "lore:mira": ("Mira is a baker.", {"keys": ["Mira"]}),
                   "card:name": ("Hanna", {"field": "name"})}
        push(c, chat, renamed)
        drain(migrated, model)
        # both texts use the name macros: read again with the new names (a text without them is not)
        assert len(model.canon_calls()) == 5  # not the Mira entry: it names nobody by macro
        assert any("Hanna is a lighthouse keeper." in u for u in model.canon_calls()[3:])
        v = view(migrated, chat)
        assert [f["subject"] for f in v["assertions"] if f.get("canon") == "card:desc" and f["predicate"] == "identity"] \
            == ["Hanna"]
        push(c, chat, {**renamed, "persona": ("{{user}} is a traveler.", {"name": "Tomo"})})
        drain(migrated, model)
        assert len(model.canon_calls()) == 7
        assert all("USER: Tomo" in u for u in model.canon_calls()[5:])
        v = view(migrated, chat)
        assert [f["subject"] for f in v["assertions"] if f.get("canon") == "persona"] == ["Tomo"]


def test_a_text_read_in_part_is_finished_when_canon_facts_come_back_on(migrated):
    chat, model = story(), Model()
    long = "Hana is a lighthouse keeper.\n" + "x" * canonfacts.PART_CHARS + "\nHana is Kaito's sister."
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        model.fail_on = "part 2 of 2"
        push(c, chat, {"card:name": ("Hana", {"field": "name"}), "card:desc": (long, {"field": "desc"})})
        drain(migrated, model)
        assert len(model.canon_calls()) == 1  # part 1 read, part 2 failed and waits for its retry
        assert c.put("/v1/config", json={"canon_facts": False}).status_code == 200  # retires the waiting job
        model.fail_on = None
        assert c.put("/v1/config", json={"canon_facts": True}).status_code == 200
        drain(migrated, model)
        assert len(model.canon_calls()) == 2 and "part 2 of 2" in model.canon_calls()[-1]  # part 1 is not read again
        v = view(migrated, chat)
        assert {f["predicate"] for f in v["assertions"] if f.get("canon")} == {"identity", "relationship"}
        cid = v["conversation"]
        assert c.get(f"/v1/conversations/{cid}/coverage").json()["canon"]["read"] == 1


def test_each_direction_of_a_relationship_holds_its_own_lock_and_a_new_holder_is_held_off(migrated):
    chat, model = SimChat("canon-locks"), Model()
    chat.user("Go on.")
    chat.reply("Hana is Kaito's guardian.")
    chat.user("And?")
    chat.reply("Kaito is Hana's ward.")
    chat.user("Then?")
    chat.reply("Kaito has the lamp.")
    chat.user("Who has the lamp?")
    desc = "Hana is Kaito's mother. Kaito is Hana's son. Hana has the lamp."
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        push(c, chat, {"card:name": ("Hana", {"field": "name"}), "card:desc": (desc, {"field": "desc"})})
        drain(migrated, model)
        v = view(migrated, chat)
        cid = v["conversation"]
        canon_rows = {(a["subject"], a["predicate"]): a for a in v["assertions"] if a.get("canon")}
        locks = {}
        for who, pred in (("Hana", "relationship"), ("Kaito", "relationship"), ("Hana", "possesses")):
            res = c.post(f"/v1/conversations/{cid}/repairs",
                         json={"kind": "fact_lock", "item": str(canon_rows[(who, pred)]["id"])})
            assert res.status_code == 200, res.text
            locks[(who, pred)] = res.json()["repair"]["id"]
        v = view(migrated, chat)
        pairs = {f["subject"]: f for f in v["facts"] if f["predicate"] == "relationship"}
        assert (pairs["Hana"]["value"], pairs["Kaito"]["value"]) == ("mother", "son")
        assert pairs["Hana"]["held_off"] == pairs["Kaito"]["held_off"] == 1
        (lamp,) = [f for f in v["facts"] if f["predicate"] == "possesses"]
        assert (lamp["subject"], lamp["held_off"]) == ("Hana", 1)  # a new holder is no restatement
        packet = recall(c, chat, "Who has the lamp?", budget=2000, canon_held=["card:desc"])["packet"]["text"]
        assert "Hana possesses lamp" in packet and 'locked="true"' in packet
        # undo one direction: the story's statement of that direction is current, and listed against canon
        assert c.post(f"/v1/conversations/{cid}/repairs/{locks[('Hana', 'relationship')]}/remove").status_code == 200
        v = view(migrated, chat)
        pairs = {f["subject"]: f["value"] for f in v["facts"] if f["predicate"] == "relationship"}
        assert pairs == {"Hana": "guardian", "Kaito": "son"}
        assert [x["kind"] for x in v["conflicts"] if x["against"].get("subject") == "Hana"] == ["canon"]


def test_the_names_tag_and_the_macro_test_are_the_same_in_python_and_sql(migrated):
    manifests = [
        [{"key": "card:name", "hash": "a" * 64, "metadata": {"field": "name"}},
         {"key": "persona", "hash": "b" * 64, "metadata": {"name": "타쿠미"}}],
        [{"key": "card:desc", "hash": "c" * 64, "metadata": {}}],
        [{"key": "persona", "hash": "b" * 64, "metadata": {"name": None}}],
    ]
    texts = ["{{char}}는", "{{ User }} waits", "{{bot}}", "{{random::a::b}}", "no macro", "{{chars}}", "{ {user}}"]
    with psycopg.connect(migrated, row_factory=dict_row) as conn:
        for entries in manifests:
            sql = conn.execute("SELECT " + canonfacts.NAMES_TAG.format(e="%s::jsonb") + " AS tag",
                               [Jsonb(entries)] * 2).fetchone()["tag"]
            assert sql == canonfacts.names_tag(entries)
        for text in texts:
            sql = conn.execute("SELECT %s ~* %s AS named", (text, canon.MACRO_SQL)).fetchone()["named"]
            assert sql == bool(canon.MACRO.search(text)), text


def test_the_host_blocks_that_hide_their_body_and_those_that_show_it():
    """H20: `#if`, `#if_pure`, `#when`, `#each` and `#func name` hide their body unless the chat's variables show it;
    `#pure`, `#pure_display`, `#code` and `#escape` show it; `{{/…}}` closes the innermost block."""
    text = ("A. {{#if {{equal::{{getvar::lang}}::en}}}}B.{{#pure}}C.{{/}}{{/if}} D. {{#pure}}E.{{/pure}} "
            "{{#when::x::is::1}}F.{{:else}}G.{{/when}} {{#each [1,2] as n}}H.{{/each}} {{#func}}I. "
            "{{#pure x}}J. {{#escape::keep}}K.{{/}} {{#func f a}}L.{{/}} {{#if_pure 1}}M.")
    spans = canonfacts.conditional_spans(text)
    inside = {ch for ch in "ABCDEFGHIJKLM" if any(a <= text.index(ch + ".") < b for a, b in spans)}
    # `#func` without a name and `#pure x` are no blocks for the host; an unclosed block runs to the end.
    assert inside == {"B", "C", "F", "G", "H", "L", "M"}


def test_a_fact_read_inside_a_conditional_block_is_not_served(migrated):
    chat, model = story(), Model()
    lore = ("Kaito is a squire.\n{{#if {{equal::{{getvar::route}}::north}}}}\nKaito is in the northern keep.\n"
            "{{:else}}\nKaito is a deserter.\n{{/if}}")
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        out = push(c, chat, {**canon_texts(), "lore:kaito": (lore, {"keys": ["Kaito"], "scope": "character",
                                                                    "mode": "normal"})})
        mid = out["manifest_id"]
        recall(c, chat, "Who is Kaito?", canon_manifest_id=mid, canon_held=["card:desc", "persona", "lore:kaito"])
        drain(migrated, model)
        # The model read every branch; only the fact outside the block reaches memory and the packet.
        assert any("Kaito is a deserter." in u for u in model.canon_calls())
        free = recall(c, chat, "Who is Kaito?", budget=2000, canon_manifest_id=mid, canon_held=["card:desc", "persona"])
        text = free["packet"]["text"]
        assert "Kaito identity: squire" in text
        assert "deserter" not in text and "northern keep" not in text
        v = view(migrated, chat)
        kaito = {(f["predicate"], f.get("value") or f.get("object")) for f in v["assertions"]
                 if f.get("canon") and f["subject"] == "Kaito"}
        assert kaito == {("identity", "squire")}
        assert c.get(f"/v1/trace/{free['trace_id']}/replay").json()["reproduced"] is True
