"""Rubrics: load one from JSON and refuse it early if it cannot be graded against."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


class RubricError(ValueError):
    """The rubric cannot be used as written."""


@dataclass(frozen=True)
class Criterion:
    name: str
    label: str
    points: int
    description: str = ""


@dataclass(frozen=True)
class Rubric:
    title: str
    criteria: tuple[Criterion, ...]
    assignment: str = ""

    @property
    def max_total(self) -> int:
        return sum(c.points for c in self.criteria)

    @property
    def names(self) -> list[str]:
        return [c.name for c in self.criteria]

    @classmethod
    def from_dict(cls, data: object) -> Rubric:
        if not isinstance(data, dict):
            raise RubricError("a rubric is a JSON object")
        raw = data.get("criteria")
        if not isinstance(raw, list) or not raw:
            raise RubricError("a rubric needs a non-empty 'criteria' list")

        criteria = []
        for i, c in enumerate(raw):
            if not isinstance(c, dict):
                raise RubricError(f"criterion {i} is not an object")
            name, points = c.get("name"), c.get("points")
            if not isinstance(name, str) or not name.strip():
                raise RubricError(f"criterion {i} needs a 'name'")
            if not isinstance(points, int) or isinstance(points, bool) or points <= 0:
                raise RubricError(f"criterion '{name}' needs whole, positive 'points'")
            criteria.append(
                Criterion(name, str(c.get("label") or name), points, str(c.get("description") or ""))
            )

        names = [c.name for c in criteria]
        repeated = sorted({n for n in names if names.count(n) > 1})
        if repeated:
            raise RubricError(f"criterion names must be unique, repeated: {', '.join(repeated)}")

        rubric = cls(
            title=str(data.get("title") or "Untitled rubric"),
            criteria=tuple(criteria),
            assignment=str(data.get("assignment") or ""),
        )
        stated = data.get("total_points")
        if stated is not None and stated != rubric.max_total:
            raise RubricError(
                f"total_points is {stated} but the criteria add up to {rubric.max_total}"
            )
        return rubric

    def snapshot(self) -> dict:
        """The part of the rubric a draft keeps, so it can be checked later without the file."""
        return {
            "title": self.title,
            "criteria": [
                {"name": c.name, "label": c.label, "points": c.points} for c in self.criteria
            ],
        }


def load_rubric(path: str | Path) -> Rubric:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise RubricError(f"no rubric file at {path}") from None
    except json.JSONDecodeError as e:
        raise RubricError(f"{path} is not valid JSON: {e.msg} (line {e.lineno})") from None
    return Rubric.from_dict(data)
