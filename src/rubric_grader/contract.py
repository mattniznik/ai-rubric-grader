"""The JSON contract between the model and the engine.

The model is asked for exactly this shape:

    {
      "scores": {
        "<criterion name>": {"score": <whole number 0..points>, "justification": "<text>"}
      },
      "feedback": "<text for the student>",
      "flags": ["<anything a reviewer should look at>"],
      "confidence": "high" | "medium" | "low"
    }

Every field is checked. The total is never read from the model. It is the sum of the
checked scores, so it cannot disagree with them.
"""

from __future__ import annotations

import json

from .rubric import Rubric

CONFIDENCE_LEVELS = ("high", "medium", "low")


class ContractError(ValueError):
    """The model's reply does not meet the contract."""


def extract_json(raw: str) -> dict:
    """Parse the reply as one JSON object.

    Models sometimes wrap the object in a sentence or a code fence even when told not to.
    If the whole reply does not parse, the text from the first "{" to the last "}" is tried
    before giving up.
    """
    text = raw.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end < start:
            raise ContractError("the reply contains no JSON object") from None
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError as e:
            raise ContractError(f"the reply's JSON does not parse: {e.msg}") from None
    if not isinstance(data, dict):
        raise ContractError("the reply's JSON is not an object")
    return data


def _is_whole_number(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def validate_scores(scores: object, rubric: Rubric) -> dict:
    """Every criterion present, nothing extra, each score a whole number within its points.

    Out-of-range scores are rejected, not clamped. A 32 on a 30-point criterion means the
    model misread the rubric, and quietly turning it into a 30 would hide that.
    """
    if not isinstance(scores, dict):
        raise ContractError("'scores' must be an object keyed by criterion name")
    missing = [n for n in rubric.names if n not in scores]
    if missing:
        raise ContractError(f"missing criteria: {', '.join(missing)}")
    unknown = sorted(set(scores) - set(rubric.names))
    if unknown:
        raise ContractError(f"unknown criteria: {', '.join(unknown)}")

    checked = {}
    for c in rubric.criteria:
        entry = scores[c.name]
        if not isinstance(entry, dict):
            raise ContractError(f"'{c.name}' must be an object with 'score' and 'justification'")
        score, why = entry.get("score"), entry.get("justification")
        if not _is_whole_number(score):
            raise ContractError(f"'{c.name}' score must be a whole number, got {score!r}")
        if not 0 <= score <= c.points:
            raise ContractError(f"'{c.name}' score {score} is outside 0-{c.points}")
        if not isinstance(why, str) or not why.strip():
            raise ContractError(f"'{c.name}' needs a justification")
        checked[c.name] = {"score": score, "justification": why.strip()}
    return checked


def total(scores: dict) -> int:
    return sum(entry["score"] for entry in scores.values())


def validate_reply(data: dict, rubric: Rubric) -> dict:
    """Check a parsed reply and return it in the shape a draft stores."""
    scores = validate_scores(data.get("scores"), rubric)
    feedback, flags, confidence = data.get("feedback"), data.get("flags"), data.get("confidence")
    if not isinstance(feedback, str) or not feedback.strip():
        raise ContractError("'feedback' must be non-empty text")
    if not isinstance(flags, list) or not all(isinstance(f, str) for f in flags):
        raise ContractError("'flags' must be a list of strings")
    if confidence not in CONFIDENCE_LEVELS:
        raise ContractError(f"'confidence' must be one of: {', '.join(CONFIDENCE_LEVELS)}")
    return {
        "scores": scores,
        "total": total(scores),
        "feedback": feedback.strip(),
        "flags": flags,
        "confidence": confidence,
    }


def parse_reply(raw: str, rubric: Rubric) -> dict:
    return validate_reply(extract_json(raw), rubric)
