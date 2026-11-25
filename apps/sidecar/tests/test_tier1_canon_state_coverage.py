"""Tier 1 wave 1 regressions: canon facts under conditional blocks (B6) and a read that depends on the names (B7);
the setting's side of "Diverged from the setting" (B8); a status key the message asked about (G1); clock keys of a
recalled source (G2); a valueless secret's content, the story's leak bar, a trimmed window and coverage (C1, C3, G4).
Synthetic names and text only."""

from __future__ import annotations

import uuid

import psycopg
from psycopg.rows import dict_row

from conftest import active_generation, make_client
from nmos_sidecar import canonfacts, coverage, divergence, source_time, statechange, summaries
from nmos_sidecar.parsers import load_rules
from simchat import SimChat
from test_canon import push
from test_canon_facts import Model, drain, story, view
from test_generations import LLM, conv_id
from test_packet_ledger import extract
from test_sidecar_integration import recall, sync
from test_source_time import clock_story  # noqa: F401 (a fixture)
from test_summaries import ON as SUMMARIES_ON, drain as drain_summaries, story_chat


# --- B6: a conditional block anywhere no longer hides the text's unconditional facts --------------------------------

CARD_B6 = ("{{char}}는 <b>{{user}}</b>의 경호원이다.\n"
           "{{#if {{getvar::route}}}}{{char}}는 사실 첩자다.{{/if}}\n"
           "<span class=\"x\">{{user}}는 기사단장이다.</span>")


def test_b6_evidence_with_names_and_markup_outside_a_block_is_served():
    rid = uuid.uuid4()
    names = ("세라", "유찬")
    raw = canonfacts.blocks_of(CARD_B6)  # the old reading: raw text, macros and markup in place
    assert canonfacts.shown(raw, rid, "세라는 유찬의 경호원이다") is False  # the bug: wiped
    blocks = canonfacts.read_blocks(CARD_B6, *names)
    served = {ev: canonfacts.shown(blocks, rid, ev, names) for ev in (
        "세라는 유찬의 경호원이다", "유찬는 기사단장이다.", "세라는 사실 첩자다.", "없는 문장입니다만")}
    assert served == {"세라는 유찬의 경호원이다": True, "유찬는 기사단장이다.": True,
                      "세라는 사실 첩자다.": False, "없는 문장입니다만": False}


def test_b6_verdicts_are_per_names_and_cleaning_that_breaks_a_tag_falls_back_to_raw():
    rid = uuid.uuid4()
    a, b = canonfacts.read_blocks(CARD_B6, "세라", "유찬"), canonfacts.read_blocks(CARD_B6, "미오", "카이")
    assert canonfacts.shown(a, rid, "세라는 유찬의 경호원이다", ("세라", "유찬")) is True
    assert canonfacts.shown(b, rid, "세라는 유찬의 경호원이다", ("미오", "카이")) is False  # not that chat's text
    # The cleaner would drop an opener written inside a tag: the raw text's blocks are used instead.
    text = "<x {{#if {{getvar::a}}}}>Hana is a spy.{{/if}} Hana is a keeper."
    blocks = canonfacts.read_blocks(text, "Hana", None)
    assert blocks is not None and blocks == canonfacts.blocks_of(text)
    assert canonfacts.shown(blocks, rid, "Hana is a spy.") is False
    assert canonfacts.shown(blocks, rid, "Hana is a keeper.") is True


def test_b6_a_card_with_one_block_keeps_its_named_facts(migrated):
    chat, model = story(), Model()
    desc = ("{{char}} is a <b>keeper</b>. {{user}} is a <i>traveler</i>.\n"
            "{{#if {{getvar::route}}}}{{char}} is a spy.{{/if}}")
    texts = {"card:name": ("Hana", {"field": "name"}), "card:desc": (desc, {"field": "desc"}),
             "persona": ("{{user}} walks at night.", {"name": "Taku"})}
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        mid = push(c, chat, texts)["manifest_id"]
        drain(migrated, model)
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            cid = view(migrated, chat)["conversation"]
            got = {(a["subject"], a["value"]) for a in canonfacts.rows(
                conn, cid, mid, active_generation(conn, "canon").key)}
    assert got == {("Hana", "keeper"), ("Taku", "traveler")}  # "Hana is a spy." stays out


# --- B7: the persona and the card's fields are always read under the manifest's names ------------------------------

def test_b7_window_tag_rules():
    entries = [{"key": "card:name", "hash": "h1"}, {"key": "persona", "hash": "h2", "metadata": {"name": "유찬"}}]
    tag = canonfacts.names_tag(entries)
    for key in ("persona", "card:desc", "card:personality", "card:scenario", "card:greeting"):
        assert canonfacts.wtag(key, False, entries) == tag
    assert canonfacts.wtag("lore:x", False, entries) == "plain" and canonfacts.wtag("note", False, entries) == "plain"
    assert canonfacts.wtag("lore:x", True, entries) == tag


class NamingModel(Model):
    """As `Model`, and a persona's reader names USER as the prompt gives it (the model writes the name it was told)."""

    def __call__(self, system: str, user: str) -> tuple[dict, str]:
        out, raw = super().__call__(system, user)
        if "SOURCE: the user's persona" in user:
            who = user.split("USER: ", 1)[1].split("\n", 1)[0]
            out["assertions"].append({"subject": who, "subject_type": "character", "predicate": "identity",
                                      "value": "former detective", "modality": "actual", "source": "narration",
                                      "epistemic": "stated", "confidence": 0.9, "evidence": "a former detective",
                                      "knowledge": "unknown"})
        return out, raw


def _texts(persona_name: str) -> dict:
    return {"card:name": ("Hana", {"field": "name"}), "card:desc": ("Hana is a keeper.", {"field": "desc"}),
            "persona": ("Walks at night, a former detective.", {"name": persona_name}),
            "lore:kaito": ("Kaito is a squire.", {"keys": ["Kaito"], "scope": "character", "mode": "normal"})}


def _people(url: str, chat: SimChat) -> set[str]:
    return {a["subject"] for a in view(url, chat)["assertions"] if a.get("canon") == "persona"}


def test_b7_a_plain_persona_is_never_another_chats_and_a_rename_reads_it_again(migrated):
    a, b, model = SimChat("tier1-b7-a"), SimChat("tier1-b7-b"), NamingModel()
    for chat in (a, b):
        chat.user("We walk to the mill.")
        chat.reply("Hana is in the old mill.")
        chat.user("What does Hana do?")
    with make_client(migrated, **LLM) as c:
        for chat, name in ((a, "Doyun"), (b, "Yuki")):
            sync(c, chat)
            out = push(c, chat, _texts(name))
            drain(migrated, model)
            recall(c, chat, "Where is Kaito?", canon_manifest_id=out["manifest_id"], canon_held=["lore:kaito"])
            drain(migrated, model)
        calls = model.canon_calls()
        # each chat reads its card field and persona under its own names; the plain lorebook entry is copied
        assert sum("SOURCE: the user's persona" in u for u in calls) == 2
        assert sum("Kaito is a squire." in u for u in calls) == 1
        assert _people(migrated, a) == {"Doyun"} and _people(migrated, b) == {"Yuki"}  # no ghost "Doyun" in b
        for chat in (a, b):
            cov = c.get(f"/v1/conversations/{conv_id(c, chat)}/coverage").json()["canon"]
            assert cov["read"] == cov["wanted"] == 3 and cov["pending"] == 0
        # a's persona renamed: read again, and its facts follow the new name
        push(c, a, _texts("Minho"))
        drain(migrated, model)
        assert sum("USER: Minho" in u for u in model.canon_calls()) == 2  # the card's field and the persona
        assert _people(migrated, a) == {"Minho"}


# --- B8: the setting's side without conditional branches or entries never activated; short Korean quotes ------------

def _entry(key: str, content: str, **metadata) -> dict:
    return {"key": key, "content": content, "metadata": metadata}


def test_b8_conditional_branches_are_not_the_setting():
    assert divergence.unconditional("A. {{#if x}}B. {{#when y}}C.{{/when}}{{/if}} D.") == "A.  D."
    entries = [_entry("card:name", "세라"),
               _entry("card:desc", "{{char}}는 기사다.{{#if {{getvar::end}}}}{{char}}는 죽었다.{{/if}}")]
    given, _ = divergence.canon_input(entries, [], [], "")
    assert [g["text"] for g in given] == ["세라는 기사다."]


def test_b8_only_held_or_always_active_entries_are_candidates():
    entries = [_entry("lore:a", "카이토는 기사다.", keys=["카이토"]),
               _entry("lore:b", "카이토는 사실 왕자다.", keys=["카이토"]),
               _entry("lore:c", "카이토는 백장미단 소속이다.", always_active=True)]
    entities = [{"id": "e1", "name": "카이토"}]
    story = "카이토가 성문을 지켰다."
    every = {g["key"] for g in divergence.canon_input(entries, entities, [], story)[0]}
    held = {g["key"] for g in divergence.canon_input(entries, entities, [], story, frozenset(), {"lore:a"})[0]}
    assert every == {"lore:a", "lore:b", "lore:c"}  # without held keys: as before
    assert held == {"lore:a", "lore:c"}


def test_b8_short_korean_quotes_hold_and_short_english_ones_do_not():
    given = [{"key": "card:desc", "label": "card", "text": "직업: 기사단장\n상태: 생존\n소속: 백장미단\nrank: low"}]
    items = [{"key": "card:desc", "quote": q, "now": "changed", "turns": [3]}
             for q in ("직업: 기사단장", "상태: 생존", "소속: 백장미단", "상태:", "rank: low")]
    got = [r["quote"] for r in divergence.check(items, given, [(0, 5)], 5)]
    assert got == ["직업: 기사단장", "상태: 생존", "소속: 백장미단"]


# --- G1: a key the message asked about is told even when it did not change ------------------------------------------

def test_g1_an_asked_unchanged_key_is_told_whole():
    w = [{"turn": t, "position": t, "values": {"골드": "120", "인벤토리": "검 / 방패 / 물약 ×2", "HP": str(90 + t)}}
         for t in range(3)]
    plain = {t.key for t in statechange.tell(w)}
    assert "골드" not in plain and "인벤토리" not in plain
    told = {t.key: t for t in statechange.tell(w, asked=frozenset({"골드", "인벤토리"}))}
    assert told["골드"].value == "120" and told["인벤토리"].value == "검 / 방패 / 물약 ×2"


# --- G2: a prefixed clock key and the other clock keys -----------------------------------------------------------------

def test_g2_keys_cue_and_prefix():
    assert source_time.base(" Status.Date ") == "date" and source_time.base("World.시간") == "시간"
    assert {source_time.KEYS[k] for k in ("date", "날짜")} == {"date"}  # Phase 42's categories unchanged
    assert {source_time.KEYS[k] for k in ("time", "시간", "시각")} == {"time"}
    for k in ("현재 시간", "현재 시각", "일차", "day", "요일", "계절", "날짜/시간", "일시"):
        assert source_time.KEYS[k] in source_time.CATEGORIES and source_time.KEYS[k] not in ("date", "time")
    for q in ("지금 며칠째야?", "오늘 몇 일차야?", "오늘 무슨 요일이지?", "그게 어느 날이었지?", "지금 무슨 계절이야?",
              "그때부터 얼마나 지났어?"):
        assert source_time.CUE.search(q), q
    assert not source_time.CUE.search("카이토는 어디 있어?")


def test_g2_a_prefixed_clock_is_read_and_another_clock_key_keeps_the_date(migrated, clock_story):  # noqa: F811
    path, chat, _ = clock_story
    with make_client(migrated, parsers_file=str(path)) as c:
        sync(c, chat, character_name="Clock test")
        with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
            head = conn.execute("SELECT head_commit_id FROM conversation WHERE host_chat_ref=%s",
                                (chat.id,)).fetchone()["head_commit_id"]
            rid = str(conn.execute("SELECT source_revision_id FROM active_membership WHERE commit_id=%s AND position=1",
                                   (head,)).fetchone()["source_revision_id"])
            version = load_rules(str(path)).version
            conn.execute("UPDATE state_observation SET key = 'Status.' || key WHERE source_revision_id = %s", (rid,))
            conn.execute("INSERT INTO state_observation (conversation_id,source_revision_id,rules_version,rule_id,key,value)"
                         " SELECT conversation_id,source_revision_id,rules_version,rule_id,v.k,v.v FROM state_observation,"
                         " (VALUES ('일차', '3일차'), ('요일', '화요일')) v(k, v)"
                         " WHERE source_revision_id=%s AND key='Status.Date'", (rid,))
            clock = source_time.read(conn, head, version, [rid], 16, -1)[rid]
    assert [(k, v) for k, v, _ in clock.fields] == [("Status.Date", "0712-03-01"), ("Status.Time", "07:05"),
                                                    ("일차", "3일차"), ("요일", "화요일")]


# --- C1: a valueless secret's content is its object; summaries listed by the older key stay usable ------------------

KEY = {"text": "김하나 possesses 은열쇠", "subject": "김하나", "predicate": "possesses", "object": "은열쇠",
       "turn": 3, "position": 6, "holders": ["김하나"], "open": ["도윤"]}


def test_c1_content_of_valueless_secrets():
    assert summaries.content(KEY) == "은열쇠"
    assert summaries.content({"text": "서윤 located in 지하감옥"}) == "지하감옥"
    assert summaries.content({"text": "레나 member of 암살단", "subject": "레나", "predicate": "member_of"}) == "암살단"
    assert summaries.content({"text": "하나 knows: 편지는 위조됐다"}) == "편지는 위조됐다"
    assert summaries.content({"text": "하나 relationship 도윤", "predicate": "relationship"}) == "하나 relationship 도윤"
    scene = "김하나는 낡은 은열쇠를 몰래 품에 숨겼다."
    assert summaries.leaks(scene, [KEY], frozenset({"도윤"})) == [KEY]  # caught in the scene of the one it is kept from


def test_c1_a_summary_listed_by_the_whole_line_is_not_held_as_unlisted():
    old = {"last_turn": 7, "coverage": {"secrets": ["김하나 possesses 은열쇠"]}}  # written before this change
    new = {"last_turn": 7, "coverage": {"secrets": [summaries.secret_key(KEY)]}}
    assert summaries.unlisted(old, [KEY]) == [] and summaries.unlisted(new, [KEY]) == []
    assert summaries.unlisted({"last_turn": 7, "coverage": {"secrets": []}}, [KEY]) == [KEY]


# --- C3: the story leaves out a scene that rewords a secret -----------------------------------------------------------

def test_c3_a_scene_that_rewords_a_secret_gives_the_story_none_of_its_text(migrated):
    from test_summaries import lighthouse_chat, story_setup

    chat, prompts = lighthouse_chat(), []

    def recording(system: str, user: str) -> tuple[dict, str]:
        prompts.append(user)
        if system == summaries.STORY_PROMPT:
            return {"summary": "Story."}, "{}"
        return {"summary": "Hana hid that the letter was a forgery." if "turn 0]" in user else "Nothing else."}, "{}"

    secret = {"text": "Hana knows: the letter is forged", "holders": ["Hana"], "open": ["Kaito"]}
    assert summaries.LEAK_NEAR <= summaries.leak_score(secret, "Hana hid that the letter was a forgery.") \
        < summaries.LEAK_MIN
    with make_client(migrated, **SUMMARIES_ON, extract_backfill=100) as c:
        sync(c, chat)
        story_setup(migrated, chat, recording)
    told = next(p for p in prompts if "SCENES:" in p).split("SCENES:")[1]
    assert "(left out: it repeats a secret)" in told and "forgery" not in told


# --- G4: a trim's cut inside a window; coverage at the in-scene bar ---------------------------------------------------

def _ask(c, chat: SimChat, query: str, first_turn: int) -> str:
    chat.user(query)
    sync(c, chat)
    ids = [m["chatId"] for m in chat.messages[2 * first_turn:]]
    return c.post("/v1/retrieve", json={"chat_id": chat.id, "query": query, "previous_ai": "", "budget_tokens": 2000,
                                        "in_context_ids": ids}).json()["packet"]["text"]


def test_g4_a_window_the_prompt_holds_in_part_is_offered(migrated):
    chat = story_chat(30)  # windows 0–7, 8–15, 16–23 due
    with make_client(migrated, **SUMMARIES_ON) as c:
        sync(c, chat)
        drain_summaries(migrated)
        cut = _ask(c, chat, "What happened when Turn 17 begins?", 20)  # turns 16–19 are in no message the prompt has
        assert "Turn 17 begins" in cut[cut.index("<Story>"):cut.index("</Story>")]
        whole = _ask(c, chat, "What happened when Turn 17 begins?", 16)  # the prompt holds the window whole
    assert '<Summary kind="scene" turns="16–23">' in cut and '<Summary kind="scene" turns="16–23">' not in whole


def test_g4_coverage_does_not_count_a_scene_its_summary_would_be_held_in(migrated):
    chat = story_chat(16)
    chat.user("Now asking a question at turn 16.")
    with make_client(migrated, **SUMMARIES_ON) as c:
        sync(c, chat)
        extract(migrated)
        drain_summaries(migrated)
        cid = conv_id(c, chat)
        with psycopg.connect(migrated, row_factory=dict_row) as conn:
            head = conn.execute("SELECT head_commit_id FROM conversation WHERE id = %s", (cid,)).fetchone()["head_commit_id"]
            key = active_generation(conn, "summarize").key
            # stated after the window's NEAR turns (so not `unlisted`), reworded in its summary (below LEAK_MIN)
            secret = {"id": 1, "turn": 20, "position": 40, "holders": ["하나"], "open": ["카이토"],
                      "text": "하나 knows: Reply follows each turn that begins"}
            text = conn.execute("SELECT text FROM summary WHERE level = 'scene'").fetchone()["text"]
            assert summaries.LEAK_NEAR <= summaries.leak_score(secret, text) < summaries.LEAK_MIN
            held = coverage.read(conn, cid, head, key, secrets=[secret])
            free = coverage.read(conn, cid, head, key, secrets=[{**secret, "text": "하나 knows: 카이토의 생일 선물"}])
    assert held.covered_turns == frozenset() and free.covered_through_turn == 7
