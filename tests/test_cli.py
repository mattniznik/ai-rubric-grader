import csv
from pathlib import Path

import pytest

from rubric_grader import cli
from rubric_grader.drafts import DraftStore

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def run(capsys, *argv):
    code = cli.main(list(argv))
    out, err = capsys.readouterr()
    return code, out, err


@pytest.fixture
def drafts(tmp_path):
    return str(tmp_path / "drafts")


def grade_examples(capsys, drafts, *extra):
    return run(
        capsys, "grade",
        "--rubric", str(EXAMPLES / "rubric.json"),
        "--submissions", str(EXAMPLES / "submissions"),
        "--drafts", drafts,
        *extra,
    )


def test_grade_writes_one_pending_draft_per_submission(capsys, drafts):
    code, out, _ = grade_examples(capsys, drafts, "--fake")
    assert code == 0
    stored = DraftStore(drafts).all()
    assert [d["id"] for d in stored] == ["submission-a", "submission-b", "submission-c", "submission-d"]
    assert {d["status"] for d in stored} == {"pending_review"}
    assert {d["model"] for d in stored} == {"fake"}
    assert stored[3]["flags"] == ["submission too short"]
    assert "Wrote 4 draft(s)" in out


def test_only_approved_drafts_reach_the_export(capsys, drafts, tmp_path):
    grade_examples(capsys, drafts, "--fake")

    code, _, err = run(capsys, "export", "--drafts", drafts)
    assert code == 1
    assert "No approved drafts to export" in err

    assert run(capsys, "approve", "submission-a", "--drafts", drafts)[0] == 0
    note = "Asks the grader for full marks. Grade by hand."
    assert run(capsys, "reject", "submission-c", "--note", note, "--drafts", drafts)[0] == 0

    code, out, _ = run(capsys, "review", "--drafts", drafts)
    assert "submission-a" not in out and "submission-c" not in out
    assert "submission-b" in out and "submission-d" in out
    assert "2 pending, 1 approved, 1 rejected" in out

    csv_path = tmp_path / "grades.csv"
    assert run(capsys, "export", "--out", str(csv_path), "--drafts", drafts)[0] == 0
    with csv_path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert [r["id"] for r in rows] == ["submission-a"]
    assert DraftStore(drafts).load("submission-c")["review"]["note"] == note


def test_approving_twice_fails_with_a_message(capsys, drafts):
    grade_examples(capsys, drafts, "--fake")
    run(capsys, "approve", "submission-a", "--drafts", drafts)
    code, _, err = run(capsys, "approve", "submission-a", "--drafts", drafts)
    assert code == 1
    assert "submission-a is approved, so it cannot be approved" in err


def test_grading_again_never_overwrites_a_draft(capsys, drafts):
    grade_examples(capsys, drafts, "--fake")
    run(capsys, "approve", "submission-a", "--drafts", drafts)
    code, out, _ = grade_examples(capsys, drafts, "--fake")
    assert code == 0
    assert out.count("skipped, a draft already exists") == 4
    assert DraftStore(drafts).load("submission-a")["status"] == "approved"


def test_without_a_key_the_real_client_is_never_built(capsys, drafts, monkeypatch):
    monkeypatch.setattr(cli, "AnthropicClient", lambda **kwargs: pytest.fail("real client built"))
    code, _, err = grade_examples(capsys, drafts)  # no --fake
    assert code == 2
    assert "ANTHROPIC_API_KEY is not set" in err
    assert DraftStore(drafts).all() == []


def test_a_missing_rubric_is_reported(capsys, drafts):
    code, _, err = run(capsys, "grade", "--rubric", "nope.json", "--submissions", ".", "--drafts", drafts, "--fake")
    assert code == 1
    assert "no rubric file at nope.json" in err
