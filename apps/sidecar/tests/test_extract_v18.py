"""extract-v18 (PHASE-58 S1–S5, ADR 0081): extract-v16 with how a feeling feels — its strength, its sign and a feeling
under it — stored on the `feels_toward` row, shown to the owner only, and a switch from extract-v16 that re-extracts
nothing. Synthetic names only."""

from __future__ import annotations

import psycopg
from psycopg.rows import dict_row

from conftest import active_generation, make_client
from nmos_sidecar import archive, extraction as X, generations, inspector, views
from nmos_sidecar.config import Settings
from nmos_sidecar.facts import fact_line, memory_view
from simchat import SimChat
from test_archive import read
from test_extraction import drain, filler
from test_generations import LLM, conv_id
from test_sidecar_integration import sync
from test_summaries import ask

USED = {"calls": 1, "input": 100, "output": 10}
WARM = "하나는 카이토의 손을 꼭 잡았다. 고마운 마음이 가득했지만, 버려졌던 기억이 아직 가슴에 남아 있었다."
WARMER = "하나는 카이토를 끌어안고 한참을 울었다. 이제 그 없이는 하루도 버틸 수 없을 것 같았다."
FEELING = {"intensity": "clear", "valence": "positive",
           "under": {"value": "원망", "intensity": "faint", "valence": "negative"}}


def feels(value, feeling, evidence):
    return {"subject": "하나", "subject_type": "character", "predicate": "feels_toward", "object": "카이토",
            "object_type": "character", "value": value, "feeling": feeling, "polarity": "positive",
            "modality": "actual", "source": "narration", "evidence": evidence}


def complete(system, user):
    """The model: a fond feeling with resentment under it for WARM, the same feeling stronger for WARMER."""
    target = user.split("TARGET turn", 1)[1] if "TARGET turn" in user else ""
    if WARM in target:
        return {"assertions": [feels("고마움", FEELING, "고마운 마음이 가득했지만")]}, "{}", USED
    if WARMER in target:
        return {"assertions": [feels("고마움", {"intensity": "strong", "valence": "positive", "under": None},
                                     "한참을 울었다")]}, "{}", USED
    return {"assertions": []}, "{}", USED


def chat_of(*replies: str) -> SimChat:
    chat = SimChat()
    for i, reply in enumerate(replies):
        chat.user(f"장면 {i}.")
        chat.reply(reply)
    chat.user("다음.")
    chat.reply("잔잔한 오후였다.")
    return chat


def feelings_of(url: str, client, chat) -> list[dict]:
    with psycopg.connect(url, row_factory=dict_row) as conn:
        head = conn.execute("SELECT head_commit_id FROM conversation WHERE id = %s",
                            (conv_id(client, chat),)).fetchone()["head_commit_id"]
        view = memory_view(conn, head, active_generation(conn, "extract").key)
    return [f for f in view["facts"] if f["predicate"] == "feels_toward"]


def test_v16_is_untouched_and_v18_adds_the_feeling_only():
    assert X.DEFAULT_COMPILER == "extract-v16" and "extract-v18" in X.COMPILERS and X.FEELINGS == {"extract-v18", "extract-v19", "extract-v20"}
    v16, v18 = X.prompt_of("extract-v16"), X.prompt_of("extract-v18")
    assert X.FEELING_RULE not in v16 and '"feeling"' not in v16
    assert v18 == X._v18(v16) and X.FEELING_RULE in v18 and '"feeling": {{"intensity": "faint|clear|strong"' in v18
    assert v18.replace(X.FEELING_RULE, "").replace(X._FEELING_ANSWER, X._BECAUSE_ANSWER) == v16
    assert X.prompt_of("extract-v18", roles=False) == X.SYSTEM_V18 and X.ROLE_ENDINGS not in X.SYSTEM_V18
    assert v18.format(registry="R")  # still a template the worker can fill
    assert len(v18) < 1.15 * len(v16)  # PHASE-58 stop condition
    keys = {c: X.extractor(Settings(**LLM, extract_compiler=c)).key for c in ("extract-v16", "extract-v18")}
    assert keys["extract-v16"] != keys["extract-v18"]
    assert "extract-v18" in X.ROLES & X.PARTS_APART & X.CONFIRMS and "extract-v18" not in X.HORIZONS | X.SPEAKERS


def test_normalize_keeps_cleans_and_drops_the_feeling_as_s2_says():
    def one(feeling, predicate="feels_toward", feelings=True):
        item = {**feels("고마움", feeling, ""), "predicate": predicate}
        return X.normalize([item], WARM, feelings=feelings)[0]["feeling"]

    assert one(FEELING) == FEELING
    assert one({"intensity": "STRONG", "valence": "neutral"}) == {"intensity": "strong", "valence": None, "under": None}
    assert one({"intensity": "very", "valence": "positive"}) is None  # no valid strength: the value stands as before
    assert one({"intensity": "faint", "under": {"value": "원망"}})["under"] is None  # an under without a strength
    assert one({"intensity": "faint", "under": {"value": "null", "intensity": "clear"}})["under"] is None
    assert one({"intensity": "faint", "under": "원망"})["under"] is None
    assert one("strong") is None and one(None) is None
    assert one(FEELING, predicate="relationship") is None  # feels_toward only
    assert one(FEELING, feelings=False) is None  # another compiler's rows never carry it


def test_v18_stores_the_feeling_and_a_stronger_restatement_replaces_the_weaker(migrated):
    chat = chat_of(WARM, WARMER)
    with make_client(migrated, **LLM, extract_compiler="extract-v18") as c:
        sync(c, chat)
        drain(migrated, complete)
        [f] = feelings_of(migrated, c, chat)
    assert f["value"] == "고마움" and f["feeling"] == {"intensity": "strong", "valence": "positive", "under": None}
    assert [(h["outcome"], h["feeling"]["intensity"]) for h in f["history"]] == [("superseded", "clear"),
                                                                               ("current", "strong")]
    assert f["history"][0]["feeling"]["under"]["value"] == "원망"


def test_v16_stores_none_from_the_same_answer(migrated):
    chat = chat_of(WARM)
    with make_client(migrated, **LLM) as c:
        sync(c, chat)
        drain(migrated, complete)
        [f] = feelings_of(migrated, c, chat)
    assert f["value"] == "고마움" and "feeling" not in f and "feeling" not in f["history"][0]


def test_the_packet_is_the_same_with_or_without_the_detail(migrated):
    """PHASE-58 S5 and acceptance 3: the detail never reaches the packet."""
    chat = chat_of(WARM)
    filler(chat, 8)  # the feeling's turn leaves the prompt's window, so the packet carries it
    with make_client(migrated, **LLM, extract_compiler="extract-v18") as c:
        sync(c, chat)
        drain(migrated, complete)
        assert feelings_of(migrated, c, chat)[0]["feeling"]
        with_detail = ask(c, chat, "하나는 카이토를 어떻게 생각해?")["text"]
        with psycopg.connect(migrated, autocommit=True) as conn:
            conn.execute("UPDATE assertion SET feeling = NULL")
        without = ask(c, chat, "하나는 카이토를 어떻게 생각해?")["text"]
    assert "고마움" in with_detail and with_detail == without
    f = {**feels("고마움", None, "x"), "turn": 1, "position": 2, "knowledge": None, "known_by": None,
         "hidden_from": None}
    assert fact_line({**f, "feeling": FEELING}) == fact_line(f)


def test_an_archive_carries_the_feeling(migrated, database_url_factory, tmp_path):
    chat = chat_of(WARM)
    with make_client(migrated, **LLM, extract_compiler="extract-v18") as c:
        sync(c, chat)
        drain(migrated, complete)
    source = tmp_path / f"a{archive.SUFFIX}"
    archive.export_file(migrated, str(source))
    from test_upgrade import LATEST
    assert read(source.read_bytes())[0]["schema"]["level"] == LATEST >= "0035_feeling.sql"
    target = database_url_factory()
    archive.restore_file(target, str(source))
    query = "SELECT feeling FROM assertion WHERE predicate = 'feels_toward'"
    with psycopg.connect(migrated, row_factory=dict_row) as a, psycopg.connect(target, row_factory=dict_row) as b:
        assert a.execute(query).fetchall() == b.execute(query).fetchall() == [{"feeling": FEELING}]


def test_a_switch_between_v16_and_v18_is_classified_adds(migrated, db):
    with make_client(migrated, **LLM):
        pass
    v16 = active_generation(db, "extract").key
    v18 = X.extractor(Settings(**LLM, extract_compiler="extract-v18"))
    v17 = X.extractor(Settings(**LLM, extract_compiler="extract-v17"))
    both = X.extractor(Settings(llm_url="http://other/v1", llm_model="fake-9", extract_compiler="extract-v18"))
    v18_turns = X.extractor(Settings(**LLM, extract_compiler="extract-v18", extract_turns=2))
    assert generations.classify(db, v16, v18) == "adds"
    assert generations.classify(db, v16, both) == "model"  # the model changed too: the owner's choice decides
    assert generations.classify(db, v16, v17) == "version"  # not a pair of ADDS: PHASE-57 Q5 as before
    assert generations.classify(db, v16, v18_turns) == "version"  # a setting changed besides the compiler
    generations.activate(db, v18)
    assert generations.classify(db, v18.key, X.extractor(Settings(**LLM))) == "adds"  # and back


def queued_extract(db) -> int:
    return db.execute("SELECT count(*) AS n FROM job WHERE kind = 'extract' AND status = 'queued'").fetchone()["n"]


def test_switching_to_v18_and_back_re_extracts_nothing(migrated, db):
    """PHASE-58 S3, acceptance 2 and 5: older turns keep their extract-v16 facts; only new turns get v18."""
    chat = chat_of(WARM)
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        sync(c, chat)
        drain(migrated, complete)
        before = feelings_of(migrated, c, chat)
    with make_client(migrated, **LLM, extract_backfill=100, extract_compiler="extract-v18") as c:
        assert queued_extract(db) == 0
        assert feelings_of(migrated, c, chat) == before  # served by extract-v16, without detail
        chat.user("장면 2.")
        chat.reply(WARMER)
        chat.user("다음.")
        sync(c, chat)
        # the two turns that became eligible since (the earlier last turn and the new one), no older turn
        assert queued_extract(db) == 2
        drain(migrated, complete)
        [f] = feelings_of(migrated, c, chat)
        assert f["feeling"]["intensity"] == "strong" and "feeling" not in f["history"][0]
    with make_client(migrated, **LLM, extract_backfill=100) as c:
        assert queued_extract(db) == 0
        [f] = feelings_of(migrated, c, chat)
        assert f["feeling"]["intensity"] == "strong"  # the turn only extract-v18 read is still served by it


def test_the_detail_is_shown_with_its_sign_and_a_row_without_it_as_before():
    plain = {**feels("고마움", None, ""), "turn": 3}
    rich = {**plain, "feeling": FEELING}
    assert inspector.feeling_sign(rich) == "mix"
    assert inspector.feeling_sign({**plain, "feeling": {"intensity": "faint", "valence": "negative"}}) == "neg"
    assert inspector.feeling_sign({**plain, "feeling": {"intensity": "faint", "valence": None}}) is None
    assert inspector.feeling_detail(rich, "ko") == " (뚜렷함, 긍정적) · 밑에: 원망 (옅음, 부정적)"
    assert inspector.feeling_detail(rich, "en") == " (clear, positive) · under: 원망 (faint, negative)"
    assert inspector.feeling_dot(rich, "ko") == '<span class="fd mix" title="긍정과 부정이 섞인 감정"></span>'
    assert inspector.feeling_detail(plain, "ko") == inspector.feeling_dot(plain, "ko") == ""
    escaped = {**plain, "feeling": {**FEELING, "under": {**FEELING["under"], "value": "<b>"}}}
    assert "&lt;b&gt;" in inspector.feeling_detail(escaped, "ko")

    def pair(f):
        return {"names": {"a": "하나", "b": "카이토"}, "relationship": [], "role": [], "feels": [f], "speech": []}

    old = [f"{views._named(f, 'subject')}→{views._named(f, 'object')} {views.t('ko', 'feels_toward')} {f.get('value')}"
           for f in (plain,)]
    assert views._pair_bits(pair(plain), "ko") == [inspector._v(x) for x in old]  # byte-identical without detail
    assert views._pair_bits(pair(rich), "ko") == [
        "하나→카이토 감정 " + '<span class="fd mix" title="긍정과 부정이 섞인 감정"></span>'
        + "고마움 (뚜렷함, 긍정적) · 밑에: 원망 (옅음, 부정적)"]
    table = inspector._pairs_table([pair(rich)], "ko")
    assert 'class="fd mix"' in table and "고마움 (뚜렷함, 긍정적)" in table
    assert ".fd.mix" in views.STYLE and "--mix:" in inspector.STYLE
