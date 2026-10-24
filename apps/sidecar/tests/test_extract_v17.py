"""extract-v17 (PHASE-45 S1–S2, PHASE-51 S1–S2, S4): extract-v16 with a thread's horizon and the speakers of the TARGET
turn's quoted lines. Selectable, not the default; extract-v15 and extract-v16 are untouched."""

from __future__ import annotations

import psycopg
from psycopg.rows import dict_row

from conftest import make_client
from nmos_sidecar import archive, extraction as X
from test_archive import read
from nmos_sidecar.config import Settings
from simchat import SimChat
from test_extraction import drain, filler
from test_sidecar_integration import sync

USED = {"calls": 1, "input": 100, "output": 10}
SCENE = ('하나가 문을 열었다. "오늘 저녁에 등대 앞에서 만나." 카이토가 고개를 끄덕였다. "알았어, 늦지 마."'
         ' 그리고 둘은 말없이 걸었다. "평생 이 빚은 갚을게."')


def row(turn, content, name="CHAR"):
    return {"turn": turn, "content": content, "metadata": {"name": name, "role": "assistant"}}


def ctx(members):
    return {"context": [], "members": members, "target": {"turn": 3, "host_persona_name": None}}


def test_v16_is_untouched_and_v17_adds_two_things():
    assert X.DEFAULT_COMPILER == "extract-v16" and "extract-v17" in X.COMPILERS
    v16, v17 = X.prompt_of("extract-v16"), X.prompt_of("extract-v17")
    assert X.HORIZON_RULE not in v16 and '"horizon"' not in v16 and '"speakers"' not in v16
    assert X.HORIZON_RULE in v17 and '"horizon": "scene|arc|lasting' in v17 and '"speakers": {{"Q1"' in v17
    assert X.prompt_of("extract-v17", roles=False) == X.SYSTEM_V17 and X.ROLE_ENDINGS not in X.SYSTEM_V17
    assert v17.format(registry="R")  # still a template the worker can fill
    Settings(llm_url="http://x/v1", llm_model="m", extract_compiler="extract-v17")
    keys = {c: X.extractor(Settings(llm_url="http://x/v1", llm_model="m", extract_compiler=c)).key
            for c in ("extract-v16", "extract-v17")}
    assert keys["extract-v16"] != keys["extract-v17"]


def test_the_user_prompt_lists_the_targets_quoted_lines_for_v17_only():
    c = ctx([row(3, SCENE)])
    v17 = X.build_prompt(c, compiler="extract-v17")
    assert "QUOTED LINES of the TARGET turn:" in v17 and X.SPEAKER_RULE in v17
    assert '[Q1] "오늘 저녁에 등대 앞에서 만나."' in v17 and '[Q3] "평생 이 빚은 갚을게."' in v17
    assert "QUOTED LINES" not in X.build_prompt(c, compiler="extract-v16")
    assert "QUOTED LINES" not in X.build_prompt(ctx([row(3, "하나가 조용히 웃었다.")]), compiler="extract-v17")
    many = " ".join(f'"대사 번호 {i}번이다."' for i in range(40))
    assert X.target_quotes(ctx([row(3, many)]))[-1] == f"대사 번호 {X.QUOTES_LISTED - 1}번이다."


def test_speakers_are_read_by_number_and_unknown_ones_left_out():
    lines = ["오늘 저녁에 등대 앞에서 만나.", "알았어, 늦지 마.", "평생 이 빚은 갚을게."]
    got = X.speakers_of({"speakers": {"Q1": "하나", "q2": "카이토", "Q3": "?", "Q9": "누구", "Q0": "x"}}, lines)
    assert got == [{"q": lines[0], "speaker": "하나"}, {"q": lines[1], "speaker": "카이토"}]
    assert X.speakers_of({"speakers": {"Q1": "{{user}}"}}, lines) == [{"q": lines[0], "speaker": "{{user}}"}]
    assert X.speakers_of({"speakers": {"Q1": "?"}}, lines) is None
    assert X.speakers_of({"speakers": ["하나"]}, lines) is None and X.speakers_of({}, lines) is None
    assert X.speakers_of({"speakers": {"Q1": "하나"}}, []) is None


def test_a_horizon_is_kept_only_where_asked():
    goal = {"subject": "하나", "subject_type": "character", "predicate": "goal", "value": "등대의 비밀을 밝힌다",
            "horizon": "lasting", "salience": "major", "evidence": ""}
    event = {"subject": "하나", "subject_type": "character", "predicate": "event", "value": "문을 열었다",
             "salience": "major", "horizon": "scene", "evidence": ""}
    v17 = X.normalize([goal, event], SCENE, horizons=True)
    v16 = X.normalize([goal, event], SCENE)
    assert [r["salience"] for r in v17] == ["lasting", "major"]
    assert [r["salience"] for r in v16] == [None, "major"]


def complete(system, user):
    """The model: under extract-v17 a lasting debt and the speakers of SCENE's lines; anything else empty."""
    if "TARGET turn" not in user or "평생 이 빚은" not in user.split("TARGET turn", 1)[1]:
        return {"assertions": []}, "{}", USED
    return {"assertions": [{"subject": "하나", "subject_type": "character", "predicate": "owes", "object": "카이토",
                            "object_type": "character", "value": "평생 갚을 빚", "horizon": "lasting",
                            "polarity": "positive", "modality": "actual", "source": "narration",
                            "evidence": "평생 이 빚은 갚을게."}],
            "speakers": {"Q1": "하나", "Q2": "카이토", "Q3": "하나"}}, "{}", USED


def extracted(migrated, compiler):
    chat = SimChat()
    with make_client(migrated, llm_url="http://fake/v1", llm_model="fake", extract_compiler=compiler) as c:
        chat.user("하나와 카이토가 등대에 왔다.")
        chat.reply(SCENE)
        filler(chat, 1)
        sync(c, chat)
        drain(migrated, complete)
    with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
        x = conn.execute("SELECT e.speakers, e.compiler_version, a.salience FROM extraction e JOIN assertion a"
                         " ON a.extraction_id = e.id WHERE a.predicate = 'owes'").fetchone()
        failed = conn.execute("SELECT count(*) AS n FROM job WHERE status <> 'done'").fetchone()["n"]
    return x, failed


def test_v17_stores_the_horizon_and_the_speakers(migrated):
    x, failed = extracted(migrated, "extract-v17")
    assert failed == 0 and x["compiler_version"] == "extract-v17" and x["salience"] == "lasting"
    assert x["speakers"] == [{"q": "오늘 저녁에 등대 앞에서 만나.", "speaker": "하나"},
                             {"q": "알았어, 늦지 마.", "speaker": "카이토"}, {"q": "평생 이 빚은 갚을게.", "speaker": "하나"}]


def test_v16_stores_neither_from_the_same_answer(migrated):
    x, failed = extracted(migrated, "extract-v16")
    assert failed == 0 and x["compiler_version"] == "extract-v16"
    assert x["salience"] is None and x["speakers"] is None


def test_an_archive_carries_the_speakers_and_horizons_and_names_its_schema(migrated, database_url_factory, tmp_path):
    """PHASE-45 acceptance 4: export → restore round-trips them; the archive's schema level is 0030, which a build
    without the migration refuses as newer (`test_restore`'s "newer NMOS")."""
    extracted(migrated, "extract-v17")
    source = tmp_path / f"a{archive.SUFFIX}"
    archive.export_file(migrated, str(source))
    assert read(source.read_bytes())[0]["schema"]["level"] == "0030_extract_v17.sql"
    target = database_url_factory()
    archive.restore_file(target, str(source))
    query = ("SELECT e.speakers, a.salience FROM extraction e JOIN assertion a ON a.extraction_id = e.id"
             " WHERE a.predicate = 'owes'")
    with psycopg.connect(migrated, row_factory=dict_row) as a, psycopg.connect(target, row_factory=dict_row) as b:
        before, after = a.execute(query).fetchall(), b.execute(query).fetchall()
    assert before == after and after[0]["salience"] == "lasting" and len(after[0]["speakers"]) == 3
