"""ADR 0064 item 2, the owner's S1 review of `4e76c70`: under extract-v16 a known name the turn does not write stands
in for an alias only when the turn is about that character: a description of someone unnamed (the reveal of ADR
0024), or a character the turn writes by another of its known names. Checked on the five preserved S1 turns
(`fixtures/model/phase28/2026-10-03-s1-confirmation-review`): the model's original `also_called` items, the
KNOWN ENTITIES the extraction was shown, and the TARGET it read. No model call."""
import json
from pathlib import Path

import pytest

from nmos_sidecar import extraction

CHAR = "character"
EXCERPTS = Path(__file__).resolve().parents[3] / "fixtures/model/phase28/2026-10-03-s1-confirmation-review"


def alias(subject, value):
    return {"subject": subject, "subject_type": CHAR, "predicate": "also_called", "value": value}


def known(*entities):
    return [{"name": names[0], "also": list(names[1:]), "type": CHAR} for names in entities]


def test_a_known_character_the_turn_never_names_is_not_joined():
    hints = known(("백이안", "이안"), ("곽은비",))
    text = "곽 조합장이 직접 오 사장한테 제안을 넣었다."
    assert extraction.alias_evidenced(alias("백이안", "곽 조합장"), text, hints)  # extract-v15, as it was (ADR 0024)
    assert not extraction.alias_evidenced(alias("백이안", "곽 조합장"), text, hints, apart=True)
    assert not extraction.alias_evidenced(alias("곽 조합장", "백이안"), text, hints, apart=True)  # either way round


def test_a_known_character_the_turn_writes_by_another_name_still_takes_a_new_one():
    hints = known(("윤하람", "하람"))
    text = '"람이, 빵집은 괜찮아?" 도윤은 하람의 목도리를 여며 주었다.'
    assert extraction.alias_evidenced(alias("윤하람", "람이"), text, hints, apart=True)
    assert not extraction.alias_evidenced(alias("윤하람", "람이"), '"람이, 빵집은 괜찮아?"', hints, apart=True)


def test_a_described_character_is_still_revealed_by_its_name():
    hints = [{"name": "?검은 망토의 남자", "type": CHAR}]
    text = "망토를 벗은 남자가 말했다. 내 이름은 카이토다."
    assert extraction.alias_evidenced(alias("카이토", "?검은 망토의 남자"), text, hints, apart=True)


def test_both_names_in_the_turn_are_unchanged():
    assert extraction.alias_evidenced(alias("하나", "Hana"), "하나(Hana)가 웃었다.", [], apart=True)


def excerpt(turn):
    folder = EXCERPTS / f"turn-{turn:03d}"
    evidence = json.loads((folder / "evidence.json").read_text(encoding="utf-8"))
    lines = (folder / "target.txt").read_text(encoding="utf-8").splitlines()[1:]  # after "TARGET turn N:"
    text = "\n".join(line.split(": ", 1)[1] if line.startswith(("USER: ", "CHARACTER: ")) else line for line in lines)
    return evidence, text


# (turn, subject, value): stored then → under this rule. 237 both names are in the turn: a model error this rule does
# not catch (the alias confirmation of the follow-up issue is for it).
S1 = [(81, "백이안", "곽 조합장", "valid", "pending"), (182, "윤하람", "람이", "valid", "valid"),
      (200, "추오월", "도도", "valid", "pending"), (237, "람이", "도도", "valid", "valid")]


@pytest.mark.parametrize(("turn", "subject", "value", "stored", "now"), S1)
def test_the_preserved_s1_aliases(turn, subject, value, stored, now):
    evidence, text = excerpt(turn)
    (item,) = [i for i in evidence["original_also_called_items"] if (i["subject"], i["value"]) == (subject, value)]
    (row,) = [r for r in evidence["stored_also_called_rows"] if (r["subject"], r["value"]) == (subject, value)]
    hints = evidence["known_entities_stored"]
    assert row["status"] == stored
    assert extraction.normalize([item], text, hints)[0]["status"] == stored  # the check as the run applied it
    (out,) = extraction.normalize([item], text, hints, apart=True)
    assert out["status"] == now
    if now == "pending":
        assert out["reason"] == "alias not stated in the turn"
