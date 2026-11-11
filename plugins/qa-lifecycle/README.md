# QA Lifecycle

Turns a BRD into an understanding doc, test plan, test scenarios and test cases, with a human review gate after every stage and requirement traceability from start to finish.

## How it works

The lifecycle is modelled as artifacts with dependencies, not as a chat. A small script owns all state so the model only writes content:

| Stage | Output | Built from | Gate |
|---|---|---|---|
| Understanding | `understanding.md`, `requirements.json` | BRD | Schema check, then human approval |
| Test plan | `test-plan.md` | Understanding | Template sections present, then human approval |
| Scenarios | `scenarios.json` | Understanding, test plan | Every testable requirement covered, then human approval |
| Test cases | `test-cases.json` | Scenarios | Every scenario covered, every step has an expected result, then human approval |
| Export | `test-cases.csv`, `traceability.csv` | All of the above approved | - |

Stage statuses: `pending`, `in_review`, `changes_requested`, `approved`, `stale`.

Each stage records the hash of the inputs it was built from. If the BRD or an upstream artifact changes, or an approved file is edited, the affected stages become `stale` automatically and are reworked through the same gates, with a list of exactly which requirement or scenario IDs changed.

## Components

- **Skill `qa-lifecycle`** - the orchestrator, four stage guides, and the state script (`scripts/qa_state.py`, Python 3 standard library only).
- **Template** - `skills/qa-lifecycle/assets/test-plan-template.md` is a placeholder. Replace it with your own; keep top-level sections as `## ` headings.

## Setup

Connect the connectors that hold your BRDs:

- **Atlassian** for Confluence pages
- **Microsoft 365** for SharePoint documents

Without them, attach or paste the BRD instead.

## Usage

- "Run the QA lifecycle for this BRD: <Confluence or SharePoint link>"
- "What's the status of the QA run?"
- "Approved" / "Change the scope section to exclude reporting"
- "The BRD changed, update the tests"

Each run is kept in `qa-runs/<name>/` in the working folder, so a run can be resumed in a later session from the same folder.

## Not included yet

Pushing test cases straight into a test management tool. The CSV export is one row per step and imports into Xray, Zephyr or Azure Test Plans with column mapping.
