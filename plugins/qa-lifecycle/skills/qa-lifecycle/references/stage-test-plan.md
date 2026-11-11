# Stage: Test Plan

Inputs: `understanding.md`, `requirements.json`, and `test-plan-template.md` in the run folder. Output: `test-plan.md`.

## Rules

- Follow the template in the run folder exactly: every `## ` heading must appear with the same text, in the same order. Add subsections under them freely. Do not add or rename top-level sections.
- Replace every `{{...}}` placeholder. None may remain. Remove the template's HTML comment.
- Reference requirement IDs. Every testable requirement must appear at least once (the coverage summary table is the natural place).
- Scope follows the approved understanding doc. Out-of-scope items need a reason.
- Derive the approach from the requirements: which test types each requirement group needs, and what is worth automating (stable, repetitive, high priority) versus manual (exploratory, visual, one-off).
- Exit criteria must be measurable (for example "all high-priority test cases executed, no open critical defects").
- Do not invent names, dates, environments or tools. Where the BRD and understanding doc do not supply them, write `TBD - owner: <role>` and list the item under assumptions and open questions.
- Risks: tie each to a requirement or dependency and give a mitigation. Carry over unresolved open questions from the understanding stage as risks.

Keep it a working document: tables over paragraphs where the content is tabular.
