"""PHASE-45 S3–S5: the quote route reads the speakers extract-v17 stored, only where the text names nobody; a line two
extractions name differently names nobody; "{{user}}" is the persona; the asked speaker's other lines of a message follow
their line. With no stored speakers (extract-v16 in use) the route is unchanged. Synthetic text."""

from __future__ import annotations

import psycopg
from psycopg.rows import dict_row

from nmos_sidecar import retrieval
from nmos_sidecar.entities import PERSONA, norm
from nmos_sidecar.quotes import QUOTE_CHARS, pick
from test_extract_v17 import extracted

NAMES = {"도윤": "도윤", "이안": "이안", "한솔": "한솔"}
# untagged alternating dialogue: no speech cue names anyone
TALK = ('"오늘은 등대까지 걸어가자." "바람이 너무 차가워." "그래도 노을은 봐야지." "그럼 목도리라도 줘."'
        ' "등대지기한테 열쇠도 받아야 해."')
LINES = ["오늘은 등대까지 걸어가자.", "바람이 너무 차가워.", "그래도 노을은 봐야지.", "그럼 목도리라도 줘.",
         "등대지기한테 열쇠도 받아야 해."]
KNOWN = {norm(LINES[0]): "도윤", norm(LINES[1]): "이안", norm(LINES[2]): "도윤", norm(LINES[3]): "이안",
         norm(LINES[4]): "도윤"}


def msg(n, text, role="assistant", name="narrator"):
    return {"id": f"r{n}", "clean": text, "turn": n, "position": n, "role": role, "name": name}


def test_without_stored_speakers_the_route_is_unchanged():
    chat = [msg(3, TALK), msg(5, '"등대는 멀다." 이안이 말했다.')]
    for q in ("이안이 등대 얘기할 때 뭐라고 했어?", "바람 얘기 때 뭐라고 했지?", "도윤이 노을 보자고 할 때 뭐라고 했어?"):
        assert pick(chat, q, NAMES, 9, False) == pick(chat, q, NAMES, 9, False, known={}) \
            == pick(chat, q, NAMES, 9, False, known=None)


def test_a_stored_speaker_names_a_line_the_text_does_not():
    plain = pick([msg(3, TALK)], "이안이 바람 얘기할 때 뭐라고 했어?", NAMES, 9, False)
    known = pick([msg(3, TALK)], "이안이 바람 얘기할 때 뭐라고 했어?", NAMES, 9, False, known=KNOWN)
    assert all(q.speaker is None for q in plain)
    assert known[0].words == LINES[1] and known[0].speaker == "이안"


def test_the_text_still_decides_where_it_names_the_speaker():
    said = msg(4, '"바람이 너무 차가워." 한솔이 말했다.')
    [top] = pick([said], "바람 얘기할 때 뭐라고 했어?", NAMES, 9, False, known={norm("바람이 너무 차가워."): "이안"})
    assert top.speaker == "한솔"


def test_the_persona_is_read_from_the_user_label():
    names = {**NAMES, norm(PERSONA): "서하"}
    [top, *_] = pick([msg(3, TALK)], "서하가 바람 얘기할 때 뭐라고 했어?", {**names, "서하": "서하"}, 9, False,
                     known={norm(LINES[1]): PERSONA})
    assert top.speaker == "서하" and top.words == LINES[1]


PAD = " 파도가 방파제를 때렸고 갈매기 몇 마리가 낮게 날며 소금기 섞인 바람을 갈랐다." * 4
LONG = PAD.join(f'"{w}"' for w in LINES)  # each line far from the next: one placed line cannot show them all


def test_the_asked_speakers_other_lines_follow_and_nothing_the_line_showed_is_cut():
    [top, *_] = pick([msg(3, LONG)], "도윤이 등대지기 열쇠 얘기할 때 뭐라고 했어?", NAMES, 9, False, known=KNOWN)
    assert top.speaker == "도윤" and top.words == LINES[4]
    line_alone = pick([msg(3, LONG)], "도윤이 등대지기 열쇠 얘기할 때 뭐라고 했어?", NAMES, 9, False)[0].text
    assert LINES[0] not in line_alone  # without the speakers, the first line is not shown
    assert top.text.startswith(line_alone) and top.text != line_alone  # today's excerpt, then the additions
    assert top.text[len(line_alone):].startswith(" … 도윤: ") and LINES[0] in top.text and LINES[2] in top.text
    assert LINES[1] not in top.text[len(line_alone):]  # another's line is not added
    assert len(top.text) <= len(line_alone) + len(" … 도윤: ") + QUOTE_CHARS


def test_speakers_are_read_from_the_generation_in_use_and_a_disagreement_names_nobody(migrated):
    extracted(migrated, "extract-v17")
    with psycopg.connect(migrated, row_factory=dict_row, autocommit=True) as conn:
        x = conn.execute("SELECT id, members, extractor_key FROM extraction WHERE speakers IS NOT NULL").fetchone()
        ids = list(x["members"])
        got = retrieval._quote_speakers(conn, ids, x["extractor_key"])
        assert got == {norm("오늘 저녁에 등대 앞에서 만나."): "하나", norm("알았어, 늦지 마."): "카이토",
                       norm("평생 이 빚은 갚을게."): "하나"}
        assert retrieval._quote_speakers(conn, ids, "extract-other") == {}  # another generation in use: none
        assert retrieval._quote_speakers(conn, ids, None) == {}
        # a second live extraction of the turn names one line's speaker differently
        second = conn.execute("INSERT INTO extraction (id, source_revision_id, window_hash, compiler_version, extractor_key, model,"
                     " raw, coverage, members, speakers) SELECT gen_random_uuid(), source_revision_id, window_hash || 'b',"
                     " compiler_version, extractor_key, model, raw, coverage, members,"
                     " jsonb_build_array(jsonb_build_object('q', '알았어, 늦지 마.', 'speaker', '하나'))"
                     " FROM extraction WHERE id = %s RETURNING id", (x["id"],)).fetchone()["id"]
        got = retrieval._quote_speakers(conn, ids, x["extractor_key"])
        assert norm("알았어, 늦지 마.") not in got and got[norm("평생 이 빚은 갚을게.")] == "하나"
        # by id: the first row's window hash is hex and may itself end in "b"
        conn.execute("UPDATE extraction SET discarded_at = now() WHERE id = %s", (second,))
        assert retrieval._quote_speakers(conn, ids, x["extractor_key"])[norm("알았어, 늦지 마.")] == "카이토"
