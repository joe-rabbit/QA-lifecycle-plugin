# Stage: Test Scenarios

Inputs: `understanding.md`, `requirements.json`, `test-plan.md`. Output: `scenarios.json`.

A scenario is one situation worth testing, stated in a sentence or two: *what* to verify, not the steps.

```json
[
  {
    "id": "SC-001",
    "title": "Account locks after five failed logins",
    "description": "A user who enters the wrong password five times in a row is locked out for 15 minutes.",
    "requirement_ids": ["REQ-001"],
    "type": "negative",
    "priority": "high"
  }
]
```

| Field | Rules |
|---|---|
| `id` | `SC-` + 3 digits. Permanent. |
| `requirement_ids` | At least one. Must exist in `requirements.json`. |
| `type` | `positive`, `negative`, `edge`, `integration`, `non_functional` |
| `priority` | `high`, `medium`, `low`. Normally inherits the highest priority among its requirements. |

## Coverage (enforced on submit)

- Every requirement with `testable: true` needs at least one scenario. Submit fails otherwise.
- Functional requirements with only positive scenarios raise a warning. Add negative and edge scenarios wherever a rule, limit, validation, permission or state change exists: boundaries (at, just below, just above), invalid and missing input, wrong role, wrong state, repeated or concurrent action.
- Add `integration` scenarios for end-to-end flows that span several requirements, and list all of them in `requirement_ids`.
- Stay within the test plan's scope. Do not write scenarios for out-of-scope items or for `testable: false` requirements.

Avoid duplicates: two scenarios that would be verified by the same steps and data are one scenario.

On **revise** with `upstream_changes`: update scenarios linked to changed requirements, add scenarios for added requirements, delete scenarios whose every requirement was removed. Leave the rest untouched.
