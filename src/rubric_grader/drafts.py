"""Drafts and the approval gate.

A draft is one JSON file per submission. Its status only moves one way:

    pending_review -> approved
    pending_review -> rejected

Grading only ever writes pending_review. approve() and reject() are the only ways out, and
export only reads approved drafts. An approval stores a fingerprint of the scores and feedback
it covered, so a draft edited after approval is refused at export instead of going out unseen.

The functions above the I/O line are pure: they take a draft and the time, and return a new
draft. The DraftStore below it reads and writes files and decides nothing.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
from typing import TextIO

from .contract import ContractError, total, validate_scores
from .rubric import Rubric

PENDING, APPROVED, REJECTED = "pending_review", "approved", "rejected"


class GateError(RuntimeError):
    """An action the approval gate does not allow."""


def new_draft(draft_id: str, source: str, rubric: Rubric, result: dict, model: str, now: str) -> dict:
    return {
        "id": draft_id,
        "source": source,
        "status": PENDING,
        "graded_at": now,
        "model": model,
        "rubric": rubric.snapshot(),
        "max_total": rubric.max_total,
        **result,
        "review": None,
    }


def fingerprint(draft: dict) -> str:
    """A short hash of what an approval covers: the scores, the total and the feedback."""
    body = json.dumps(
        {"scores": draft.get("scores"), "total": draft.get("total"), "feedback": draft.get("feedback")},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


def _require_pending(draft: dict, action: str) -> None:
    if draft.get("status") != PENDING:
        raise GateError(
            f"{draft['id']} is {draft.get('status')}, so it cannot be {action}. "
            "Only pending_review drafts can."
        )


def approve(draft: dict, now: str, note: str | None = None) -> dict:
    """Approve a pending draft.

    The scores are checked against the rubric again first. A reviewer may have edited them
    by hand, and an edit has to meet the same contract as the model's reply.
    """
    _require_pending(draft, "approved")
    rubric = Rubric.from_dict(draft["rubric"])
    try:
        scores = validate_scores(draft.get("scores"), rubric)
    except ContractError as e:
        raise GateError(
            f"{draft['id']} cannot be approved: {e}. Fix the scores in its file, or reject it."
        ) from None
    approved = {**draft, "scores": scores, "total": total(scores), "status": APPROVED}
    approved["review"] = {"decision": APPROVED, "at": now, "note": note, "fingerprint": fingerprint(approved)}
    return approved


def reject(draft: dict, note: str, now: str) -> dict:
    _require_pending(draft, "rejected")
    if not note or not note.strip():
        raise GateError("a rejection needs a note saying why")
    return {**draft, "status": REJECTED, "review": {"decision": REJECTED, "at": now, "note": note.strip()}}


def export_row(draft: dict) -> dict:
    if draft.get("status") != APPROVED:
        raise GateError(f"{draft['id']} is {draft.get('status')}. Only approved drafts are exported.")
    # Covers a draft edited after approval, and one marked approved by hand without the command.
    if (draft.get("review") or {}).get("fingerprint") != fingerprint(draft):
        raise GateError(
            f"{draft['id']} does not match what was approved, so nothing was exported. "
            "Set its status back to pending_review and approve it again."
        )
    row = {"id": draft["id"], "source": draft["source"]}
    row.update({name: entry["score"] for name, entry in draft["scores"].items()})
    row.update(
        {
            "total": draft["total"],
            "max_total": draft["max_total"],
            "feedback": draft["feedback"],
            "approved_at": draft["review"]["at"],
        }
    )
    return row


def export_rows(drafts: list[dict]) -> list[dict]:
    """One row per approved draft. One stale approval stops the whole export,
    so a partly checked file never goes out."""
    return [export_row(d) for d in drafts if d.get("status") == APPROVED]


# ---------- I/O ----------


class DraftStore:
    """A folder of draft JSON files, one per submission id."""

    def __init__(self, folder: str | Path):
        self.folder = Path(folder)

    def path(self, draft_id: str) -> Path:
        if not draft_id or draft_id in (".", "..") or Path(draft_id).name != draft_id:
            raise GateError(f"not a valid draft id: {draft_id!r}")
        return self.folder / f"{draft_id}.json"

    def exists(self, draft_id: str) -> bool:
        return self.path(draft_id).exists()

    def load(self, draft_id: str) -> dict:
        path = self.path(draft_id)
        if not path.exists():
            raise GateError(f"no draft named {draft_id} in {self.folder}")
        return json.loads(path.read_text(encoding="utf-8"))

    def save(self, draft: dict) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self.path(draft["id"])
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(draft, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(tmp, path)  # a crash mid-write never leaves a half-written draft

    def all(self) -> list[dict]:
        if not self.folder.is_dir():
            return []
        return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(self.folder.glob("*.json"))]


def write_csv(rows: list[dict], out: TextIO) -> None:
    fields: list[str] = []
    for row in rows:
        fields += [k for k in row if k not in fields]
    writer = csv.DictWriter(out, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
