import json

import pytest

from rubric_grader.clients import FakeClient, ModelError
from rubric_grader.engine import MIN_CHARS, build_prompt, grade


def test_short_submission_never_reaches_the_model(rubric):
    client = FakeClient("not used")
    result = grade("A list has an order. A dictionary has keys.", rubric, client)
    assert client.calls == []
    assert result["total"] == 0
    assert all(entry["score"] == 0 for entry in result["scores"].values())
    assert result["flags"] == ["submission too short"]


def test_whitespace_does_not_count_toward_the_length(rubric):
    client = FakeClient("not used")
    grade("x" * (MIN_CHARS - 1) + " " * 500, rubric, client)
    assert client.calls == []


def test_good_reply_becomes_a_checked_result(rubric, make_reply, long_text):
    raw = json.dumps(make_reply())
    client = FakeClient(raw)
    result = grade(long_text, rubric, client)
    assert len(client.calls) == 1
    assert result["total"] == 84
    assert result["error"] is None
    assert result["raw_response"] == raw


def test_bad_reply_becomes_a_result_for_manual_grading(rubric, long_text):
    client = FakeClient("Sorry, I would rather not use JSON today.")
    result = grade(long_text, rubric, client)
    assert result["scores"] == {}
    assert result["total"] is None
    assert result["flags"] == ["needs manual grading"]
    assert "no JSON object" in result["error"]
    assert result["raw_response"] == "Sorry, I would rather not use JSON today."


def test_out_of_range_reply_is_not_clamped_into_a_grade(rubric, make_reply, long_text):
    data = make_reply()
    data["scores"]["clarity"]["score"] = 30
    result = grade(long_text, rubric, FakeClient(json.dumps(data)))
    assert result["scores"] == {}
    assert "outside 0-25" in result["error"]


def test_model_error_becomes_a_result_for_manual_grading(rubric, long_text):
    class Declines:
        name = "declines"

        def complete(self, system, prompt):
            raise ModelError("the model declined to grade this submission")

    result = grade(long_text, rubric, Declines())
    assert result["error"] == "the model declined to grade this submission"
    assert result["raw_response"] is None


def test_network_errors_are_not_swallowed(rubric, long_text):
    class Offline:
        name = "offline"

        def complete(self, system, prompt):
            raise ConnectionError("no network")

    with pytest.raises(ConnectionError):
        grade(long_text, rubric, Offline())


def test_prompt_carries_the_assignment_every_criterion_and_the_submission(rubric):
    prompt = build_prompt("THE SUBMISSION TEXT", rubric)
    assert rubric.assignment in prompt
    for c in rubric.criteria:
        assert f'"{c.name}" ({c.label}, 0-{c.points} points)' in prompt
    assert "<submission>\nTHE SUBMISSION TEXT\n</submission>" in prompt
