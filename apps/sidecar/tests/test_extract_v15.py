"""extract-v15 (PHASE-25, ADR 0059): `role_toward`, a role one character holds toward another (tenant, employer,
teacher…), its own fact beside the pair's relationship, and read as how two characters stand."""

from __future__ import annotations

import re
from uuid import UUID

from conftest import make_client
from nmos_sidecar import canonfacts, extraction, inspector
from nmos_sidecar.entities import resolve
from nmos_sidecar.facts import PRIOR_STANDING, STANDING, _versions, earlier, prior, version_key
from nmos_sidecar.predicates import REGISTRY, registry_prompt, validate
from simchat import SimChat
from test_extract_v14 import SETTINGS
from test_extraction import drain, facts, filler
from test_semantics import row
from test_sidecar_integration import recall, sync

CHAR = "character"
C = {"subject_type": CHAR, "object_type": CHAR}
CONV = UUID("01900000-0000-7000-8000-000000000059")
# The generations' specs under extract-v14 for test_extract_v14.SETTINGS (before PHASE-25).
V14_EXTRACT = {"kind": "extract", "endpoint": "http://x/v1", "model": "y", "compiler": "extract-v14",
               "prompt": "b14ab384c24e450f", "predicates": "bbb4f7b3610846dc", "normalizer": "clean-v3",
               "json_mode": True, "temperature": 0, "unit": "turn", "context_turns": 3, "target_chars": 6000,
               "context_chars": 1000, "hints": 40}
V14_CANON = {"kind": "canon", "endpoint": "http://x/v1", "model": "y", "version": "canon-v1",
             "prompt": "c084747d55328ce7", "predicates": "edb186b802c42a45", "normalizer": "clean-v3",
             "json_mode": True, "temperature": 0, "part_chars": 6000, "max_parts": 4}


def role(subject, obj, value, **extra):
    return {"subject": subject, "subject_type": CHAR, "predicate": "role_toward", "object": obj, "object_type": CHAR,
            "value": value, "modality": "actual", "source": "narration", "knowledge": "public", **extra}


def current(rows):
    """Current facts as memory_view folds them: grouped by version key, then folded."""
    r = resolve(CONV, rows)
    groups: dict[tuple, list] = {}
    for x in rows:
        groups.setdefault(version_key(x, r), []).append(x)
    return sorted((f["predicate"], f["subject"], f["object"], f["value"]) for h in groups.values()
                  for f in _versions(h, r))


def test_role_toward_is_single_per_direction_and_standing():
    p = REGISTRY["role_toward"]
    assert (p.cardinality, p.per_object, p.subject_types, p.object_types, p.needs_value) == \
        ("single", True, (CHAR,), (CHAR,), True)
    assert "- role_toward (subject: character, object: character, value: text) — the subject's role toward" \
        in registry_prompt()
    assert "role_toward" in STANDING and "role_toward" in canonfacts.PREDICATES
    assert validate(role("하나", "카이토", "세입자")) == ("valid", None)
    assert validate({**role("하나", "카이토", "세입자"), "value": None}) == ("pending", "missing value")
    assert validate({**role("하나", "카이토", "세입자"), "object": None}) == ("pending", "missing object")


def test_relationship_is_narrowed_to_personal_ties_and_points_roles_elsewhere():
    d = REGISTRY["relationship"].description
    assert d.startswith("personal relationship of subject to object: kin, romance, rivalry, friendship")
    assert "a role such as tenant or employer is role_toward" in d
    # canon reads the same registry lines (its own prompt is unchanged)
    canon = canonfacts.PROMPT.format(registry=registry_prompt(canonfacts.PREDICATES))
    assert "- role_toward (subject: character" in canon and "is role_toward" in canon


def test_the_prompt_asks_for_a_place_and_a_role_both_with_synthetic_names():
    prompt = extraction.SYSTEM_PROMPT.format(registry=registry_prompt())
    for phrase in ("`role_toward` when the TARGET turn states a role one character holds toward another",
                   "One assertion\n  per direction", "A role is not a `relationship`", "a pair can have both",
                   "says both where someone lives and the role they hold\n  there, give both",
                   "e.g. \"하나가 하녀로 일하며 지내는 카이토의 저택\": `located_in` (하나, 카이토의 저택) and\n"
                   "  `role_toward` (하나 to 카이토, \"하녀: 카이토의 저택에서 일하며 지냄\")"):
        assert phrase in prompt, phrase


def test_the_extractor_generation_changes_and_canon_only_by_its_predicates():
    ex = extraction.extractor(SETTINGS).spec
    assert extraction.COMPILER_VERSION == "extract-v15"
    assert {k for k in V14_EXTRACT if ex[k] != V14_EXTRACT[k]} == {"compiler", "prompt", "predicates"}
    canon = canonfacts.generation(SETTINGS).spec
    assert {k for k in V14_CANON if canon[k] != V14_CANON[k]} == {"predicates"}  # role_toward and relationship's text


def test_a_role_is_current_per_direction_and_its_earlier_value_becomes_history():
    rows = [row(1, "하나", "role_toward", "카이토", "세입자", **C), row(2, "카이토", "role_toward", "하나", "집주인", **C),
            row(5, "하나", "role_toward", "카이토", "집을 산 사람", **C)]
    assert current(rows) == [("role_toward", "카이토", "하나", "집주인"), ("role_toward", "하나", "카이토", "집을 산 사람")]
    r = resolve(CONV, rows)
    assert version_key(rows[0], r) != version_key(rows[1], r)  # each direction its own history, unlike relationship
    (hana,) = [f for f in _versions([rows[0], rows[2]], r)]
    assert [h["outcome"] for h in hana["history"]] == ["superseded", "current"]
    assert earlier(hana)["value"] == "세입자"


def test_a_pair_keeps_its_relationship_and_its_roles_at_once():
    rows = [row(1, "하나", "relationship", "카이토", "소꿉친구", **C), row(2, "하나", "role_toward", "카이토", "세입자", **C),
            row(2, "카이토", "role_toward", "하나", "집주인", **C), row(3, "하나", "located_in", "카이토의 집",
                                                                  subject_type=CHAR, object_type="place")]
    assert current(rows) == [("located_in", "하나", "카이토의 집", None), ("relationship", "하나", "카이토", "소꿉친구"),
                             ("role_toward", "카이토", "하나", "집주인"), ("role_toward", "하나", "카이토", "세입자")]
    # a newer relationship replaces the relationship only, not a role
    later = rows + [row(4, "카이토", "relationship", "하나", "연인", **C)]
    assert ("role_toward", "하나", "카이토", "세입자") in current(later)
    assert ("relationship", "하나", "카이토", "소꿉친구") not in current(later)


def test_a_role_ranks_as_a_standing_fact():
    assert prior(row(1, "하나", "role_toward", "카이토", "세입자", **C)) == PRIOR_STANDING


def test_the_inspector_shows_a_role_per_direction_in_its_own_column():
    rows = [{"id": 1, "predicate": "relationship", "subject": "Hana", "object": "Kaito", "value": "childhood friend",
             "position": 1, "turn": 1},
            {"id": 2, "predicate": "role_toward", "subject": "Hana", "object": "Kaito", "value": "tenant",
             "position": 2, "turn": 2},
            {"id": 3, "predicate": "role_toward", "subject": "Kaito", "object": "Hana", "value": "landlord",
             "position": 2, "turn": 2}]
    (p,) = inspector.pairs(rows)
    assert [f["value"] for f in p["role"]] == ["tenant", "landlord"] and [f["value"] for f in p["relationship"]] == \
        ["childhood friend"]
    conv = {"id": "c", "host_chat_ref": "r", "head_commit_id": "h", "character_name": "Hana", "chat_name": "t"}
    en = inspector.detail(conv, [], [], [], [], [], None, lang="en", standing=rows)
    assert "<th>Pair</th><th>Relationship</th><th>Role</th><th>Feelings</th><th>Speech</th>" in en
    assert "Hana → Kaito: tenant" in en and "Kaito → Hana: landlord" in en
    ko = inspector.detail(conv, [], [], [], [], [], None, lang="ko", standing=rows)
    assert "<th>두 인물</th><th>관계</th><th>역할</th><th>감정</th><th>말투·호칭</th>" in ko


def tenancy(system, user):
    """The story states the tenancy one turn after the friendship; the model gives the place and the role (v15)."""
    target = user.split("TARGET", 1)[1]
    items = []
    if "소꿉친구" in target:
        items.append({**role("하나", "카이토", "소꿉친구"), "predicate": "relationship"})
    if "세 들어" in target:
        items += [role("하나", "카이토", "세입자: 카이토의 집에 세 들어 삶"),
                  {**role("하나", "카이토의 집", None), "predicate": "located_in", "object_type": "place"}]
    if "다락방" in target:
        for predicate, value in (("has_trait", "다락방을 좋아함"), ("goal", "월세를 모으기")):
            items.append({"subject": "하나", "subject_type": CHAR, "predicate": predicate, "value": value,
                          "modality": "actual", "source": "narration", "knowledge": "public"})
    return {"assertions": items}, "{}"


def test_a_role_leads_the_packet_and_a_request_recorded_before_it_replays_as_it_was(migrated):
    with make_client(migrated, llm_url="http://fake/v1", llm_model="fake") as c:
        chat = SimChat()
        chat.user("하나와 카이토는 소꿉친구다.")
        chat.reply("둘은 어릴 때부터 같은 골목에서 자랐다.")
        filler(chat, 5)
        sync(c, chat)
        drain(migrated, tenancy)
        before = recall(c, chat, "하나는 카이토에게 어떤 사람이야?", budget=600)
        chat.user("하나는 카이토의 집에 세 들어 산다. 하나는 다락방을 좋아하고, 월세를 모으려 한다.")
        chat.reply("카이토는 월세 봉투를 받아 들었다.")
        filler(chat, 5, tag="b")
        sync(c, chat)
        drain(migrated, tenancy)
        rows = [f for f in facts(c, chat) if f["predicate"] in ("role_toward", "relationship", "located_in")]
        # the trait's own words in the message: as a plain fact it would rank above the role
        out = recall(c, chat, "하나는 카이토에게 어떤 사람이야? 다락방을 좋아한다던데.", budget=600)
        packet, lines = out["packet"]["text"], c.get(f"/v1/trace/{out['trace_id']}").json()["lines"]
        again = c.get(f"/v1/trace/{before['trace_id']}/replay").json()
    assert {(f["predicate"], f["value"] or f["object"]) for f in rows} == {
        ("relationship", "소꿉친구"), ("role_toward", "세입자: 카이토의 집에 세 들어 삶"), ("located_in", "카이토의 집")}
    assert re.search(r"하나 role toward 카이토: 세입자: 카이토의 집에 세 들어 삶</Fact>", packet)
    # a lead line (ADR 0026): before the other facts whatever their score
    role_at, trait_at = (next(i for i, e in enumerate(lines) if needle in e["text"])
                         for needle in ("role toward", "다락방을 좋아함"))
    assert role_at < trait_at
    assert "role toward" not in before["packet"]["text"]
    assert again["status"] == "ok" and again["reproduced"] is True and again["text"] == before["packet"]["text"]
