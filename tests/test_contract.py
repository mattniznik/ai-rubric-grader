import json

import pytest

from rubric_grader.contract import ContractError, extract_json, parse_reply


def test_clean_reply_passes_and_the_total_is_computed(rubric, make_reply):
    result = parse_reply(json.dumps(make_reply()), rubric)
    assert result["total"] == 84
    assert result["scores"]["concepts"] == {"score": 34, "justification": "Explains both correctly."}
    assert result["confidence"] == "high"


def test_a_total_from_the_model_is_ignored(rubric, make_reply):
    assert parse_reply(json.dumps(make_reply(total=100)), rubric)["total"] == 84


@pytest.mark.parametrize(
    "wrapper",
    [
        "Here is the grade you asked for:\nJSON\nLet me know if you need anything else.",
        "```json\nJSON\n```",
    ],
)
def test_json_wrapped_in_prose_or_a_fence_is_recovered(rubric, make_reply, wrapper):
    raw = wrapper.replace("JSON", json.dumps(make_reply()))
    assert parse_reply(raw, rubric)["total"] == 84


@pytest.mark.parametrize(
    "raw, message",
    [
        ("I would rather not grade this one.", "no JSON object"),
        ('Sure: {"scores": {"concepts": 3,}', "does not parse"),
        ("[1, 2, 3]", "not an object"),
    ],
)
def test_unusable_replies_are_rejected(raw, message):
    with pytest.raises(ContractError, match=message):
        extract_json(raw)


@pytest.mark.parametrize("score", [41, -1])
def test_out_of_range_scores_are_rejected_not_clamped(rubric, make_reply, score):
    data = make_reply()
    data["scores"]["concepts"]["score"] = score
    with pytest.raises(ContractError, match=f"'concepts' score {score} is outside 0-40"):
        parse_reply(json.dumps(data), rubric)


def test_boundary_scores_are_accepted(rubric, make_reply):
    data = make_reply()
    data["scores"]["concepts"]["score"] = 40
    data["scores"]["clarity"]["score"] = 0
    assert parse_reply(json.dumps(data), rubric)["total"] == 70


@pytest.mark.parametrize("score", [30.0, "30", True, None])
def test_scores_must_be_whole_numbers(rubric, make_reply, score):
    data = make_reply()
    data["scores"]["examples"]["score"] = score
    with pytest.raises(ContractError, match="must be a whole number"):
        parse_reply(json.dumps(data), rubric)


def test_every_criterion_must_be_present(rubric, make_reply):
    data = make_reply()
    del data["scores"]["clarity"]
    with pytest.raises(ContractError, match="missing criteria: clarity"):
        parse_reply(json.dumps(data), rubric)


def test_unknown_criteria_are_rejected(rubric, make_reply):
    data = make_reply()
    data["scores"]["style"] = {"score": 5, "justification": "Nice."}
    with pytest.raises(ContractError, match="unknown criteria: style"):
        parse_reply(json.dumps(data), rubric)


def test_every_score_needs_a_justification(rubric, make_reply):
    data = make_reply()
    data["scores"]["examples"]["justification"] = "   "
    with pytest.raises(ContractError, match="'examples' needs a justification"):
        parse_reply(json.dumps(data), rubric)


@pytest.mark.parametrize(
    "field, value, message",
    [
        ("confidence", "certain", "'confidence' must be one of"),
        ("flags", "none", "'flags' must be a list"),
        ("feedback", "", "'feedback' must be non-empty"),
        ("scores", [34, 30, 20], "'scores' must be an object"),
    ],
)
def test_other_fields_are_checked(rubric, make_reply, field, value, message):
    with pytest.raises(ContractError, match=message):
        parse_reply(json.dumps(make_reply(**{field: value})), rubric)
