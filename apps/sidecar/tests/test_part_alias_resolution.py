"""ADR 0012 amended for PHASE-28 Q4 (S1 turn 182, the owner's review of 4e76c70): under extract-v16 a full name's
alias to a part of it (checked with the part written on its own, PARTS_APART) does not make the full name ambiguous.
윤하람 → 하람 and 윤하람 → 람이 are one person's names; before, 윤하람 read as a name of two unlinked names and the
three stayed apart. extract-v15's rows resolve as before."""
import uuid

import pytest

from nmos_sidecar import entities, extraction
from nmos_sidecar.entities import resolve
from test_semantics import row

C = {"subject_type": "character"}
V16 = {**C, "compiler": "extract-v16"}


def alias(turn, subject, value, **kw):
    return row(turn, subject, "also_called", None, value, **kw)


def keys(r, *names):
    return [r.key("character", n) for n in names]


def test_the_part_edge_compilers_are_those_that_check_the_part_apart():
    assert entities.PART_EDGES == extraction.PARTS_APART


def test_a_full_name_with_its_given_name_and_a_nickname_is_one_person():
    r = resolve(uuid.uuid4(), [alias(33, "윤하람", "하람", **V16), alias(182, "윤하람", "람이", **V16)])
    a, b, c = keys(r, "윤하람", "하람", "람이")
    assert a == b == c and r.status("character", "윤하람") == "resolved"


@pytest.mark.parametrize("second", [("윤하람", "람이"), ("람이", "윤하람")], ids=["as-stored", "reversed"])
def test_extract_v15_rows_resolve_as_before(second):
    r = resolve(uuid.uuid4(), [alias(33, "윤하람", "하람", **C), alias(182, *second, **C)])
    assert r.status("character", "윤하람") == "ambiguous"


def test_a_letter_s_addressee_taken_for_its_writer_stays_ambiguous_and_the_pair_holds():
    """S1 turn 237 (람이 → 도도, both in the turn) after 182: 람이 names two unlinked names and joins neither; the full
    name and its given name stay one."""
    r = resolve(uuid.uuid4(), [alias(33, "윤하람", "하람", **V16), alias(182, "윤하람", "람이", **V16),
                               alias(237, "람이", "도도", **V16)])
    a, b, c, d = keys(r, "윤하람", "하람", "람이", "도도")
    assert a == b and r.status("character", "람이") == "ambiguous" and d not in {a, c}


def test_two_names_besides_the_part_still_make_the_full_name_ambiguous():
    r = resolve(uuid.uuid4(), [alias(33, "윤하람", "하람", **V16), alias(182, "윤하람", "람이", **V16),
                               alias(200, "윤하람", "도도", **V16)])
    assert r.status("character", "윤하람") == "ambiguous"


def test_a_given_name_two_full_names_share_is_still_ambiguous():
    r = resolve(uuid.uuid4(), [alias(10, "윤하람", "하람", **V16), alias(20, "김하람", "하람", **V16)])
    assert r.status("character", "하람") == "ambiguous"
    assert r.key("character", "윤하람") != r.key("character", "김하람")


def test_the_accepted_cost_one_wrong_alias_beside_the_part_joins():
    """Recorded, not wanted (ADR 0012 amendment): one wrong alias of a full name that also has its part is joined
    where it used to leave the full name ambiguous. The turn check of the alias (ADR 0064 item 2) and NMO-35's alias
    confirmation are the guards; the owner splits it (ADR 0044)."""
    r = resolve(uuid.uuid4(), [alias(24, "백이안", "이안", **V16), alias(81, "백이안", "곽 조합장", **V16)])
    assert len(set(keys(r, "백이안", "이안", "곽 조합장"))) == 1


# --- through the worker and the read (the served rows carry their compiler) -------------------------------------------

TURNS = ["윤하람이 빵집 문을 열었다. 하람은 반죽을 치댔다.", "\"람이, 빵은 다 구웠어?\" 하람이 웃었다."]


@pytest.mark.parametrize("compiler", ["extract-v16", None])
def test_the_worker_s_two_aliases_resolve_to_one_person_under_extract_v16_only(migrated, compiler):
    from conftest import make_client
    from simchat import SimChat
    from test_extraction import drain, filler
    from test_sidecar_integration import sync
    from conftest import alias_yes
    from nmos_sidecar import extraction

    chat = SimChat()
    said = {TURNS[0]: ("윤하람", "하람"), TURNS[1]: ("윤하람", "람이")}

    def complete(system, user):
        if system == extraction.ALIAS_CONFIRM_SYSTEM:  # PHASE-29: the two aliases are confirmed
            return alias_yes(user)
        shown = user.split("TARGET turn", 1)[-1]
        found = [pair for text, pair in said.items() if text in shown]
        return {"assertions": [{"subject": s, "subject_type": "character", "predicate": "also_called", "value": v,
                                "modality": "actual", "source": "narration", "evidence": text}
                               for text, (s, v) in said.items() if (s, v) in found],
                "roles_ended": [], "same_names": []}, "{}"

    settings = {"extract_compiler": compiler} if compiler else {}
    with make_client(migrated, llm_url="http://fake/v1", llm_model="fake", **settings) as c:
        for i, text in enumerate(TURNS):  # in story order: the second turn's extraction knows 윤하람 / 하람
            chat.user(text)
            chat.reply("가게 안은 따뜻했다.")
            filler(chat, 1, tag=str(i))
            sync(c, chat)
            drain(migrated, complete)
        conv = next(x["id"] for x in c.get("/v1/conversations").json() if x["host_chat_ref"] == chat.id)
        names = [set(e["names"]) for e in c.get(f"/v1/conversations/{conv}/entities").json()]
    one = {"윤하람", "하람", "람이"} in names
    assert one == ((compiler or extraction.DEFAULT_COMPILER) == "extract-v16"), names  # empty: the default
