"""Command line for the grader.

    rubric-grader grade --rubric RUBRIC.json --submissions FOLDER [--fake] [--model ID]
    rubric-grader review
    rubric-grader approve ID [--note TEXT]
    rubric-grader reject ID --note TEXT
    rubric-grader export [--out FILE.csv]

Every command takes --drafts FOLDER (default: drafts).
"""

from __future__ import annotations

import argparse
import os
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

import anthropic

from .clients import DEFAULT_MODEL, AnthropicClient, FakeClient, placeholder_reply
from .drafts import (
    APPROVED,
    PENDING,
    REJECTED,
    DraftStore,
    GateError,
    approve,
    export_rows,
    new_draft,
    reject,
    write_csv,
)
from .engine import grade
from .rubric import RubricError, load_rubric

SUBMISSION_TYPES = (".txt", ".md")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _summary(draft: dict) -> str:
    score = "no score" if draft.get("total") is None else f"{draft['total']}/{draft['max_total']}"
    flags = f"  flags: {', '.join(draft['flags'])}" if draft.get("flags") else ""
    return f"{draft['id']:<14} {score:>8}  confidence {draft.get('confidence')}{flags}"


def cmd_grade(args: argparse.Namespace) -> int:
    rubric = load_rubric(args.rubric)
    folder = Path(args.submissions)
    files = sorted(
        p for p in (folder.iterdir() if folder.is_dir() else [])
        if p.is_file() and p.suffix.lower() in SUBMISSION_TYPES
    )
    if not files:
        print(f"No .txt or .md files in {folder}", file=sys.stderr)
        return 1
    stems = [p.stem for p in files]
    shared = sorted({s for s in stems if stems.count(s) > 1})
    if shared:
        print(f"Two files share a draft id: {', '.join(shared)}. Rename one.", file=sys.stderr)
        return 1

    if args.fake:
        client, label = FakeClient(placeholder_reply(rubric)), "fake client, no model called"
    else:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print(
                "ANTHROPIC_API_KEY is not set. Set it, or add --fake to run without a model.",
                file=sys.stderr,
            )
            return 2
        client, label = AnthropicClient(model=args.model), args.model

    store = DraftStore(args.drafts)
    print(f'Grading {len(files)} submission(s) against "{rubric.title}" ({label})')
    written = 0
    for path in files:
        if store.exists(path.stem):
            print(f"  {path.stem:<14} skipped, a draft already exists")
            continue
        try:
            result = grade(path.read_text(encoding="utf-8"), rubric, client)
        except anthropic.APIError as e:
            print(
                f"Stopped at {path.stem}: {e}\n"
                f"The {written} draft(s) written so far are kept. Run grade again to continue.",
                file=sys.stderr,
            )
            return 1
        draft = new_draft(path.stem, path.as_posix(), rubric, result, client.name, _now())
        store.save(draft)
        written += 1
        print(f"  {_summary(draft)}")
    print(f"Wrote {written} draft(s) to {store.folder}. Nothing is final until it is approved.")
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    drafts = DraftStore(args.drafts).all()
    pending = [d for d in drafts if d.get("status") == PENDING]
    for d in pending:
        print(_summary(d))
        criteria = {c["name"]: c for c in d["rubric"]["criteria"]}
        for name, entry in d["scores"].items():
            c = criteria.get(name, {"label": name, "points": "?"})
            print(f"    {c['label']}: {entry['score']}/{c['points']} - {entry['justification']}")
        if d.get("error"):
            print(f"    error: {d['error']}")
        if d.get("feedback"):
            print(textwrap.indent(f"feedback: {d['feedback']}", "    "))
        print()
    counts = {s: sum(d.get("status") == s for d in drafts) for s in (PENDING, APPROVED, REJECTED)}
    print(f"{counts[PENDING]} pending, {counts[APPROVED]} approved, {counts[REJECTED]} rejected")
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    store = DraftStore(args.drafts)
    draft = approve(store.load(args.id), _now(), args.note)
    store.save(draft)
    print(f"Approved {draft['id']}: {draft['total']}/{draft['max_total']}")
    return 0


def cmd_reject(args: argparse.Namespace) -> int:
    store = DraftStore(args.drafts)
    draft = reject(store.load(args.id), args.note, _now())
    store.save(draft)
    print(f"Rejected {draft['id']}. Note: {draft['review']['note']}")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    rows = export_rows(DraftStore(args.drafts).all())
    if not rows:
        print("No approved drafts to export.", file=sys.stderr)
        return 1
    if args.out:
        with open(args.out, "w", encoding="utf-8", newline="") as f:
            write_csv(rows, f)
        print(f"Exported {len(rows)} approved draft(s) to {args.out}")
    else:
        write_csv(rows, sys.stdout)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rubric-grader",
        description="Draft rubric grades with Claude. Nothing is exported until a person approves it.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def command(name: str, func, help: str) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help)
        p.add_argument("--drafts", default="drafts", help="folder of draft files (default: drafts)")
        p.set_defaults(func=func)
        return p

    p = command("grade", cmd_grade, "grade a folder of .txt/.md submissions into pending drafts")
    p.add_argument("--rubric", required=True, help="rubric JSON file")
    p.add_argument("--submissions", required=True, help="folder of .txt or .md submissions")
    p.add_argument("--model", default=DEFAULT_MODEL, help=f"Claude model id (default: {DEFAULT_MODEL})")
    p.add_argument("--fake", action="store_true", help="use the fake client: no API key, no network")

    command("review", cmd_review, "list drafts waiting for review, with their scores")

    p = command("approve", cmd_approve, "approve one pending draft")
    p.add_argument("id")
    p.add_argument("--note", help="optional note kept with the approval")

    p = command("reject", cmd_reject, "reject one pending draft")
    p.add_argument("id")
    p.add_argument("--note", required=True, help="why it was rejected (kept in the draft)")

    p = command("export", cmd_export, "write approved drafts as CSV")
    p.add_argument("--out", help="CSV file to write (default: print to stdout)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (RubricError, GateError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
