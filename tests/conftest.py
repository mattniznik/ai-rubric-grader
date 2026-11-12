from pathlib import Path

import anthropic
import pytest

from rubric_grader.rubric import load_rubric

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


@pytest.fixture(autouse=True)
def no_real_api(monkeypatch):
    """No test may reach the real API: the key is cleared and the SDK client cannot be built."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    def refuse(*args, **kwargs):
        raise AssertionError("a test tried to build the real Anthropic client")

    monkeypatch.setattr(anthropic, "Anthropic", refuse)


@pytest.fixture
def rubric():
    return load_rubric(EXAMPLES / "rubric.json")


@pytest.fixture
def make_reply():
    """A reply that meets the contract for the example rubric (total 84), with overrides."""

    def make(**overrides):
        data = {
            "scores": {
                "concepts": {"score": 34, "justification": "Explains both correctly."},
                "examples": {"score": 30, "justification": "Two examples, each with a reason."},
                "clarity": {"score": 20, "justification": "Clear and organized."},
            },
            "feedback": "Good work. Say more about why lookup by key is fast.",
            "flags": [],
            "confidence": "high",
        }
        data.update(overrides)
        return data

    return make


@pytest.fixture
def long_text():
    return (EXAMPLES / "submissions" / "submission-a.md").read_text(encoding="utf-8")
