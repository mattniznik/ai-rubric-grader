"""Model clients. The engine needs one method: complete(system, prompt) -> reply text."""

from __future__ import annotations

import hashlib
import json
from typing import Callable, Protocol

from .rubric import Rubric

DEFAULT_MODEL = "claude-opus-5-5"


class ModelError(RuntimeError):
    """The model answered, but not with a reply the engine can use."""


class ModelClient(Protocol):
    name: str

    def complete(self, system: str, prompt: str) -> str: ...


class AnthropicClient:
    """Claude through the official anthropic SDK. The SDK reads ANTHROPIC_API_KEY."""

    def __init__(self, model: str = DEFAULT_MODEL, max_tokens: int = 16000, sdk=None):
        if sdk is None:
            import anthropic

            sdk = anthropic.Anthropic()
        self._sdk = sdk
        self.model = model
        self.max_tokens = max_tokens
        self.name = model

    def complete(self, system: str, prompt: str) -> str:
        message = self._sdk.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        if message.stop_reason == "refusal":
            raise ModelError("the model declined to grade this submission")
        if message.stop_reason != "end_turn":
            raise ModelError(f"the reply stopped early ({message.stop_reason})")
        # Current Claude models can return thinking blocks before the answer,
        # so the reply is the text blocks only, never content[0] by position.
        return "".join(block.text for block in message.content if block.type == "text")


class FakeClient:
    """A stand-in for tests and --fake runs. It never touches the network.

    `reply` is a fixed string or a function of (system, prompt). Every call is recorded,
    so a test can check what was sent, or that nothing was.
    """

    name = "fake"

    def __init__(self, reply: str | Callable[[str, str], str]):
        self._reply = reply
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, prompt: str) -> str:
        self.calls.append((system, prompt))
        return self._reply(system, prompt) if callable(self._reply) else self._reply


def placeholder_reply(rubric: Rubric) -> Callable[[str, str], str]:
    """A reply function for --fake: valid under the contract, and plainly not a real grade.

    Scores come from a hash of the prompt, so each submission gets stable, different numbers.
    """

    def reply(system: str, prompt: str) -> str:
        seed = int(hashlib.sha256(prompt.encode("utf-8")).hexdigest(), 16)
        scores = {}
        for i, c in enumerate(rubric.criteria):
            share = 60 + (seed >> (8 * i)) % 36  # 60 to 95 percent of the points
            scores[c.name] = {
                "score": c.points * share // 100,
                "justification": "Placeholder from the fake client - no model was called.",
            }
        return json.dumps(
            {
                "scores": scores,
                "feedback": "Placeholder feedback from the fake client. "
                "Run without --fake to get a real draft from Claude.",
                "flags": ["fake client"],
                "confidence": "low",
            }
        )

    return reply
