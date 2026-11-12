import pytest

from rubric_grader.contract import validate_reply
from rubric_grader.drafts import (
    APPROVED,
    PENDING,
    REJECTED,
    DraftStore,
    GateError,
    approve,
    export_row,
    export_rows,
    new_draft,
    reject,
)

GRADED = "2026-01-05T10:00:00+00:00"
LATER = "2026-01-06T09:30:00+00:00"


@pytest.fixture
def draft(rubric, make_reply):
    result = {**validate_reply(make_reply(), rubric), "error": None, "raw_response": "{}"}
    return new_draft("submission-a", "examples/submissions/submission-a.md", rubric, result, "fake", GRADED)


def test_grading_writes_pending_drafts_only(draft):
    assert draft["status"] == PENDING
    assert draft["review"] is None


def test_approve_moves_a_pending_draft_to_approved(draft):
    approved = approve(draft, LATER, note="Checked against the essay.")
    assert approved["status"] == APPROVED
    assert approved["review"]["at"] == LATER
    assert approved["review"]["note"] == "Checked against the essay."
    assert len(approved["review"]["fingerprint"]) == 16
    assert draft["status"] == PENDING  # the input draft is left alone


def test_cannot_approve_twice(draft):
    approved = approve(draft, LATER)
    with pytest.raises(GateError, match="submission-a is approved, so it cannot be approved"):
        approve(approved, LATER)


def test_cannot_approve_a_rejected_draft(draft):
    rejected = reject(draft, "Off topic.", LATER)
    with pytest.raises(GateError, match="is rejected, so it cannot be approved"):
        approve(rejected, LATER)


def test_cannot_reject_an_approved_draft(draft):
    with pytest.raises(GateError, match="is approved, so it cannot be rejected"):
        reject(approve(draft, LATER), "Changed my mind.", LATER)


def test_reject_keeps_the_note(draft):
    rejected = reject(draft, "  Asks the grader for full marks. Grade by hand.  ", LATER)
    assert rejected["status"] == REJECTED
    assert rejected["review"] == {
        "decision": REJECTED,
        "at": LATER,
        "note": "Asks the grader for full marks. Grade by hand.",
    }


@pytest.mark.parametrize("note", ["", "   ", None])
def test_reject_needs_a_note(draft, note):
    with pytest.raises(GateError, match="needs a note"):
        reject(draft, note, LATER)


def test_a_pending_draft_cannot_be_exported(draft):
    with pytest.raises(GateError, match="pending_review. Only approved drafts are exported"):
        export_row(draft)
    assert export_rows([draft]) == []


def test_export_has_only_approved_drafts(draft):
    b = {**draft, "id": "submission-b"}
    c = {**draft, "id": "submission-c"}
    rows = export_rows([approve(draft, LATER), b, reject(c, "Off topic.", LATER)])
    assert [r["id"] for r in rows] == ["submission-a"]
    assert rows[0] == {
        "id": "submission-a",
        "source": "examples/submissions/submission-a.md",
        "concepts": 34,
        "examples": 30,
        "clarity": 20,
        "total": 84,
        "max_total": 100,
        "feedback": "Good work. Say more about why lookup by key is fast.",
        "approved_at": LATER,
    }


def test_a_hand_edited_score_is_checked_again_on_approve(draft):
    draft["scores"]["concepts"]["score"] = 45
    with pytest.raises(GateError, match="outside 0-40"):
        approve(draft, LATER)


def test_a_hand_edited_score_updates_the_total_on_approve(draft):
    draft["scores"]["concepts"]["score"] = 20  # the file still says total 84
    assert approve(draft, LATER)["total"] == 70


def test_a_draft_without_scores_cannot_be_approved(rubric):
    failed = {"scores": {}, "total": None, "feedback": "", "flags": ["needs manual grading"],
              "confidence": "low", "error": "the reply contains no JSON object", "raw_response": "?"}
    d = new_draft("submission-x", "x.md", rubric, failed, "fake", GRADED)
    with pytest.raises(GateError, match="missing criteria"):
        approve(d, LATER)


def test_an_edit_after_approval_blocks_the_export(draft):
    approved = approve(draft, LATER)
    approved["scores"]["clarity"]["score"] = 25
    with pytest.raises(GateError, match="does not match what was approved"):
        export_rows([approved])


def test_a_status_set_to_approved_by_hand_is_not_exported(draft):
    hand_edited = {**draft, "status": APPROVED}  # no approval record, no fingerprint
    with pytest.raises(GateError, match="does not match what was approved"):
        export_rows([hand_edited])


def test_store_round_trip(tmp_path, draft):
    store = DraftStore(tmp_path / "drafts")
    store.save(draft)
    assert store.exists("submission-a")
    assert store.load("submission-a") == draft
    assert store.all() == [draft]
    assert [p.name for p in (tmp_path / "drafts").iterdir()] == ["submission-a.json"]


@pytest.mark.parametrize("bad_id", ["../outside", "a/b", "", ".."])
def test_store_refuses_ids_that_are_paths(tmp_path, bad_id):
    with pytest.raises(GateError, match="not a valid draft id"):
        DraftStore(tmp_path).load(bad_id)


def test_store_says_when_a_draft_is_missing(tmp_path):
    with pytest.raises(GateError, match="no draft named submission-z"):
        DraftStore(tmp_path).load("submission-z")
