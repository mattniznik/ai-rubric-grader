# ai-rubric-grader

[![CI](https://github.com/mattniznik/ai-rubric-grader/actions/workflows/ci.yml/badge.svg)](https://github.com/mattniznik/ai-rubric-grader/actions/workflows/ci.yml) ![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB) ![Claude](https://img.shields.io/badge/LLM-Claude-D97757) [![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

By [Mat Niznik](https://www.linkedin.com/in/matniznik).

A small Python engine that drafts rubric grades with Claude and holds every one of them for a person to approve. You give it a rubric in JSON and a folder of text submissions. For each submission it asks Claude for a score and a short justification per criterion, checks the reply against a strict JSON contract, and saves the result as a draft. Nothing is exported as a grade until someone approves it. It is prompted Claude plus a validation layer and an approval step. There is no fine-tuning and no trained classifier.

I teach programming courses at a university and built the first version of this to draft rubric grades for my own courses; this is that engine with the LMS integration taken out.

## Why the approval gate is the design

An AI grade is a draft. The teacher stays the system of record. So the code is built around that:

- `grade` only ever writes drafts with status `pending_review`.
- `approve` and `reject` are the only ways out of `pending_review`, and both are final.
- `export` only reads approved drafts. A pending or rejected draft never reaches the CSV.
- `approve` checks the scores against the rubric again, because a reviewer may have edited them by hand. It then stores a fingerprint of the scores and feedback. If the draft is edited after that, `export` refuses to run.
- `reject` requires a note, and the note stays in the draft.

The drafts are plain JSON files, so this is a process gate, not access control. It stops the easy mistakes: exporting something nobody looked at, or a score that changed after it was checked.

## How it works

1. The rubric is loaded and checked: unique criterion names, whole positive points, and `total_points` (if given) equal to the sum.
2. A submission under 100 characters is not sent to the model. It gets a zero draft flagged `submission too short`, which a person still has to approve.
3. Otherwise Claude gets the assignment, the rubric and the submission, with the submission inside `<submission>` tags.
4. The reply is parsed as JSON. If the model wrapped it in a sentence or a code fence, the text from the first `{` to the last `}` is tried instead. Then every field is checked.
5. A reply that fails the contract still becomes a draft: no scores, the error, the raw reply, and the flag `needs manual grading`.
6. Each draft is saved as `drafts/<submission name>.json`. An existing draft is never overwritten, so running `grade` again skips what is already there.

The default model is `claude-opus-5-5`. Pass `--model` to use another one. Current Claude models can return thinking blocks before the answer, so the client reads only the text blocks of the reply.

## Quick start

Python 3.11 or newer.

```
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

Run it on the examples with the fake client. It needs no API key and makes no network calls. Its scores are placeholders, flagged `fake client`, so you can see the whole flow without a model. This is what it printed:

```
$ rubric-grader grade --rubric examples/rubric.json --submissions examples/submissions --fake
Grading 4 submission(s) against "Lists and dictionaries" (fake client, no model called)
  submission-a     83/100  confidence low  flags: fake client
  submission-b     74/100  confidence low  flags: fake client
  submission-c     76/100  confidence low  flags: fake client
  submission-d      0/100  confidence low  flags: submission too short
Wrote 4 draft(s) to drafts. Nothing is final until it is approved.

$ rubric-grader review
submission-a     83/100  confidence low  flags: fake client
    Explains both structures: 36/40 - Placeholder from the fake client - no model was called.
    Examples with a reason: 28/35 - Placeholder from the fake client - no model was called.
    Clarity: 19/25 - Placeholder from the fake client - no model was called.
    feedback: Placeholder feedback from the fake client. Run without --fake to get a real draft from Claude.

submission-b     74/100  confidence low  flags: fake client
    Explains both structures: 30/40 - Placeholder from the fake client - no model was called.
    Examples with a reason: 25/35 - Placeholder from the fake client - no model was called.
    Clarity: 19/25 - Placeholder from the fake client - no model was called.
    feedback: Placeholder feedback from the fake client. Run without --fake to get a real draft from Claude.

submission-c     76/100  confidence low  flags: fake client
    Explains both structures: 28/40 - Placeholder from the fake client - no model was called.
    Examples with a reason: 27/35 - Placeholder from the fake client - no model was called.
    Clarity: 21/25 - Placeholder from the fake client - no model was called.
    feedback: Placeholder feedback from the fake client. Run without --fake to get a real draft from Claude.

submission-d      0/100  confidence low  flags: submission too short
    Explains both structures: 0/40 - Submission is empty or too short to grade.
    Examples with a reason: 0/35 - Submission is empty or too short to grade.
    Clarity: 0/25 - Submission is empty or too short to grade.
    feedback: Submission is empty or too short to grade.

4 pending, 0 approved, 0 rejected
```

Then decide on each draft. Approving twice is refused, and only the approved draft is exported:

```
$ rubric-grader approve submission-a
Approved submission-a: 83/100

$ rubric-grader approve submission-a
error: submission-a is approved, so it cannot be approved. Only pending_review drafts can.

$ rubric-grader reject submission-c --note "Asks the grader for full marks. Grade by hand."
Rejected submission-c. Note: Asks the grader for full marks. Grade by hand.

$ rubric-grader export
id,source,concepts,examples,clarity,total,max_total,feedback,approved_at
submission-a,examples/submissions/submission-a.md,36,28,19,83,100,Placeholder feedback from the fake client. Run without --fake to get a real draft from Claude.,2026-11-11T10:51:34+00:00
```

To fix a score before approving, edit the draft's JSON file and then run `approve`. Use `export --out grades.csv` to write a file instead of printing.

With a real key, drop `--fake`. A separate drafts folder keeps the two runs apart:

```
export ANTHROPIC_API_KEY=...      # Windows PowerShell: $env:ANTHROPIC_API_KEY = "..."
rubric-grader grade --rubric examples/rubric.json --submissions examples/submissions --drafts drafts-claude
rubric-grader review --drafts drafts-claude
```

Without `ANTHROPIC_API_KEY` set, `grade` stops before building the client and tells you to set it or use `--fake`.

## The JSON contract

The model is asked for exactly this, one object and nothing else:

```json
{
  "scores": {
    "concepts": { "score": 34, "justification": "Explains both structures correctly." },
    "examples": { "score": 30, "justification": "Two examples, each with a reason." },
    "clarity":  { "score": 20, "justification": "Clear and organized." }
  },
  "feedback": "Text for the student: strengths first, then what to improve.",
  "flags": [],
  "confidence": "high"
}
```

What is checked:

- Every rubric criterion is present, and no unknown criterion is.
- Each score is a whole number from 0 to that criterion's points. A score outside the range is rejected, not clamped.
- Each score has a non-empty justification.
- `feedback` is non-empty text, `flags` is a list of strings, and `confidence` is `high`, `medium` or `low`.
- The total is computed from the scores. A `total` sent by the model is ignored, as is any other extra top-level key.

A rubric is JSON with a `title`, optional `assignment` text, and `criteria`, each with `name`, `label`, `points` and `description`. See [examples/rubric.json](examples/rubric.json).

## Design decisions

- **Drafts, not grades.** The model's output is a starting point for a person, so the only thing `grade` can produce is a pending draft. Making the gate the core of the data model, instead of a review screen on top, means no code path can export an unreviewed result.
- **Validate, do not trust.** Out-of-range scores are rejected rather than clamped. A 32 on a 30-point criterion means the model misread the rubric, and turning it into a 30 would hide that. The total is computed, so it cannot disagree with its parts.
- **A bad reply is a visible draft, not a crash or a silent retry.** The raw reply is kept, so the reviewer can see what went wrong and grade it by hand. Network and authentication errors are different: they stop the run, and because existing drafts are never overwritten, running `grade` again picks up where it stopped.
- **Submissions are untrusted input.** `submission-c` ends with a request for full marks. The system prompt tells the model to ignore text addressed to it and to flag it, but that is an instruction, not a guarantee. The approval gate is what keeps a grade like that from going out unchecked.
- **One JSON file per draft, no database.** Drafts are easy to read, diff and fix by hand, and the approval fingerprint catches an edit made after approval.

## Running tests

```
pip install -e ".[dev]"
python -m pytest
```

The tests use the fake client only. They never call the API and need no key, and a fixture makes any attempt to build the real SDK client fail. The Anthropic client is tested against a stub of the SDK, so the request it sends and the way it reads the reply are covered, but a live call is not. GitHub Actions runs the same suite on Python 3.11, 3.12 and 3.13 for every push and pull request.

## Layout

```
src/rubric_grader/
  rubric.py     load and check a rubric
  contract.py   parse the model's reply and check it against the rubric
  engine.py     prompt, short-circuit, grade one submission
  clients.py    the Anthropic client and the fake client
  drafts.py     drafts, the approval gate, CSV export
  cli.py        grade, review, approve, reject, export
examples/       a made-up assignment, its rubric and four synthetic submissions
tests/
```

## License

MIT. See [LICENSE](LICENSE).
