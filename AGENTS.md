# AGENTS.md

Instructions for coding agents working in this repository.

## What this is

A Claude plugin that runs a QA lifecycle: a BRD goes in, and an understanding doc, test plan, test scenarios and test cases come out, each approved by a human before the next is produced.

It is **not an application**. There is no server, no build step and no dependencies. The repo contains:

- markdown instructions that a Claude model follows at run time, and
- one Python script that holds all state and enforces all rules.

## Layout

```
.claude-plugin/marketplace.json                 marketplace listing (points at the plugin)
plugins/qa-lifecycle/
  .claude-plugin/plugin.json                    plugin manifest (name, version)
  README.md                                     user-facing docs
  skills/qa-lifecycle/
    SKILL.md                                    orchestrator instructions for the model
    scripts/qa_state.py                         state engine (Python 3.8+, stdlib only)
    references/stage-*.md                       one guide per stage: schema + quality rules
    assets/test-plan-template.md                placeholder test plan template
tests/test_state.py                             tests for the state engine
build.sh                                        packages dist/qa-lifecycle.plugin
```

## Core design: code owns transitions, the model only writes content

This is the rule every change must preserve.

- `qa_state.py` decides what happens next. The model asks it (`next`), writes the files for the stage it names, and asks it to move the stage (`submit`, `approve`, `reject`).
- `SKILL.md` and the stage guides tell the model **how to write** an artifact. They must never contain logic about ordering, coverage or approval. If a rule can be checked mechanically, it belongs in `qa_state.py`, not in prose.
- The model never edits `state.json`.

## How a run works

A run is a folder (`qa-runs/<name>/`) in the user's working directory:

```
state.json                 statuses, hashes, history (script-owned)
brd.md                     BRD snapshot       brd.previous.md  prior snapshot after a change
test-plan-template.md      template copy taken at init
understanding.md, requirements.json           stage: understanding
test-plan.md                                  stage: test_plan
scenarios.json                                stage: scenarios
test-cases.json                               stage: test_cases
test-cases.csv, traceability.csv              export
```

Stages and dependencies (the `STAGES` list in `qa_state.py` is the source of truth):

| Stage | Depends on | Submit-time checks |
|---|---|---|
| `understanding` | `brd` | Requirement schema, unique `REQ-` IDs, untestable items have a reason |
| `test_plan` | `understanding` | Every template `## ` heading present, no `{{placeholders}}` left |
| `scenarios` | `understanding`, `test_plan` | Schema; every testable requirement has a scenario |
| `test_cases` | `scenarios` | Schema; every scenario has a case; every step has `action` and `expected` |

Statuses: `pending` -> `in_review` -> `approved`, with `changes_requested` (reviewer rejected) and `stale`.

```
pending --submit--> in_review --approve--> approved
                        |                     |
                     reject            input or file changed
                        v                     v
               changes_requested            stale
                        \_______ submit ______/
```

### Staleness is derived, never set by hand

On `submit`, a stage stores the hash of each dependency's approved content (`inputs`). `Run.refresh()` runs before every command and marks a stage `stale` when:

- its approved output files no longer match `approved_hash` (`edited_after_approval`), or
- a dependency is no longer approved, or its hash differs from the stored `inputs` (`upstream_changed`).

Because stages are checked in order, staleness cascades downstream on its own. `update-brd` only changes the BRD hash; `refresh()` does the rest.

On `submit`, a stage also stores per-item fingerprints of requirements and scenarios (`built_from`). For a stale stage, `next` diffs these against the current files and returns `upstream_changes` (added / changed / removed IDs) so rework is targeted.

### Invariants

Do not weaken these. Each has a test.

1. A stage cannot be submitted unless all its dependencies are approved.
2. Only an `in_review` stage can be approved or rejected.
3. Approval is refused if output files changed after `submit`.
4. `submit` runs validation; a failing stage never reaches `in_review`.
5. `export` is refused unless every stage is approved.
6. IDs (`REQ-`, `SC-`, `TC-`) are permanent: never renumbered or reused.
7. Approval is a human decision. Nothing in the script or the skill may auto-approve.

### Script interface

```
python3 qa_state.py <command> --run-dir DIR [args]
init | status | next | validate <stage> | submit <stage> | approve <stage> --by NAME
reject <stage> --feedback TEXT | update-brd --brd-file F | export
```

Every command prints JSON. Exit code 0 means ok; 1 means refused or invalid, with the reason in `refused` or `errors`. The model reads this output, so keep messages specific and actionable, and treat the JSON keys used in `SKILL.md` (`action`, `stage`, `guide`, `inputs`, `outputs`, `feedback`, `upstream_changes`) as a contract.

## Commands

```
python3 -m unittest discover tests -v     # run the tests (about 5 seconds)
claude plugin validate .                  # validate the marketplace and plugin manifests
./build.sh                                # package dist/qa-lifecycle.plugin
```

Run the tests after any change to `qa_state.py`. Run the validator after any change to a manifest or to `SKILL.md` frontmatter.

## Making changes

**Change a quality rule or wording for an artifact**: edit the matching `references/stage-*.md`. No code change.

**Change a schema field**: update the validator in `Run.validate()`, the example and field table in the stage guide, `export()` if the field is exported, and the fixtures in `tests/test_state.py`. Keep all four in step.

**Add a mechanical check** (for example "every high-priority requirement needs a negative scenario"): add it to `Run.validate()` as an error (blocks submit) or a warning (shown to the reviewer), and add a test.

**Add a stage**: add an entry to `STAGES` with `deps`, `outputs` and `guide`; add a branch in `Run.validate()`; write `references/stage-<name>.md`; list it in `SKILL.md`; extend the tests. Ordering, gating and staleness need no other code.

**Change the test plan template**: replace `assets/test-plan-template.md`. Top-level sections must be `## ` headings; the validator reads them from the template copy in the run folder.

**Add a push to a test management tool**: do it after `export` in `SKILL.md`, reading from `test-cases.json`. Keep the CSV export working.

**Release**: bump `version` in both `plugins/qa-lifecycle/.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`, and in `SKILL.md` metadata.

## Conventions

- `qa_state.py` stays a single file with no third-party imports, so it runs anywhere Python 3 does.
- Skill and guide files are instructions to a model: imperative voice, short, no user-facing chatter. Keep `SKILL.md` lean and push detail into `references/`.
- `SKILL.md` frontmatter `description` controls when the skill triggers. Change it only on purpose.
- Refer to script and reference paths relative to the skill's base directory, never with absolute paths.
- Kebab-case for file and directory names.

## Do not

- Put ordering, gating or coverage logic in markdown.
- Add a command or flag that skips validation or approval.
- Commit `qa-runs/` or any real BRD content (it is git-ignored for that reason).
- Rename the plugin or the skill; installed copies are keyed on those names.
