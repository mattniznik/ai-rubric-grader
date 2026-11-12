from types import SimpleNamespace as Obj

import pytest

from rubric_grader.clients import (
    DEFAULT_MODEL,
    AnthropicClient,
    FakeClient,
    ModelError,
    placeholder_reply,
)
from rubric_grader.engine import grade


class StubSDK:
    """Stands in for anthropic.Anthropic: records the request and returns a canned message."""

    def __init__(self, message):
        self.message = message
        self.request = None
        self.messages = self

    def create(self, **kwargs):
        self.request = kwargs
        return self.message


def test_reply_is_the_text_blocks_with_thinking_skipped():
    sdk = StubSDK(
        Obj(
            stop_reason="end_turn",
            content=[
                Obj(type="thinking", thinking=""),
                Obj(type="text", text='{"a": '),
                Obj(type="text", text="1}"),
            ],
        )
    )
    client = AnthropicClient(model="some-model", sdk=sdk)
    assert client.complete("SYSTEM", "PROMPT") == '{"a": 1}'
    assert sdk.request["model"] == "some-model"
    assert sdk.request["system"] == "SYSTEM"
    assert sdk.request["messages"] == [{"role": "user", "content": "PROMPT"}]


@pytest.mark.parametrize(
    "stop_reason, message",
    [("refusal", "declined"), ("max_tokens", r"stopped early \(max_tokens\)")],
)
def test_refusals_and_cut_off_replies_raise(stop_reason, message):
    sdk = StubSDK(Obj(stop_reason=stop_reason, content=[Obj(type="text", text="{")]))
    with pytest.raises(ModelError, match=message):
        AnthropicClient(sdk=sdk).complete("s", "p")


def test_default_model():
    assert AnthropicClient(sdk=StubSDK(None)).model == DEFAULT_MODEL


def test_tests_cannot_build_the_real_client():
    with pytest.raises(AssertionError, match="real Anthropic client"):
        AnthropicClient()


def test_fake_placeholder_meets_the_contract_and_says_it_is_fake(rubric, long_text):
    result = grade(long_text, rubric, FakeClient(placeholder_reply(rubric)))
    assert result["error"] is None
    assert result["flags"] == ["fake client"]
    for c in rubric.criteria:
        assert 0 <= result["scores"][c.name]["score"] <= c.points


def test_fake_placeholder_is_stable_for_the_same_prompt(rubric):
    reply = placeholder_reply(rubric)
    assert reply("system", "prompt one") == reply("system", "prompt one")
