# Stage: Understanding

Inputs: `brd.md`. Outputs: `understanding.md`, `requirements.json`.

Read the whole BRD before writing anything.

## requirements.json

A JSON array. One object per atomic, individually verifiable requirement. Split compound statements ("the user can create and export reports" is two requirements).

```json
[
  {
    "id": "REQ-001",
    "title": "Lock account after failed logins",
    "description": "After 5 consecutive failed login attempts the account is locked for 15 minutes.",
    "type": "functional",
    "priority": "high",
    "source_ref": "Section 3.2, Login security",
    "testable": true,
    "acceptance_criteria": ["Sixth attempt within the window is refused even with the right password"],
    "open_questions": []
  }
]
```

| Field | Rules |
|---|---|
| `id` | `REQ-` + 3 digits. Permanent. |
| `type` | `functional` or `non_functional` |
| `priority` | `high`, `medium`, `low`. Use the BRD's priority when given; otherwise judge by business impact and say so in the understanding doc. |
| `source_ref` | Where in the BRD this comes from. Required. |
| `testable` | `false` only when no observable check exists as written (for example "the system should be user-friendly"). Then add `untestable_reason` and an open question asking for a measurable criterion. |
| `acceptance_criteria` | Only what the BRD states or directly implies. Optional. |
| `open_questions` | Ambiguities, missing limits, conflicts with other requirements. |

Include non-functional requirements (performance, security, accessibility, compatibility) and business rules buried in tables, footnotes and appendices.

## understanding.md

For the reviewer to confirm the BRD was read correctly. Sections:

1. **Summary** - what is being built and why, in a short paragraph.
2. **Users and roles** - who uses it and what each role can do.
3. **In scope / Out of scope** - as the BRD states it.
4. **Key flows** - the main end-to-end journeys, numbered steps.
5. **Business rules** - validations, calculations, limits, with REQ IDs.
6. **Integrations and dependencies** - external systems, data sources.
7. **Non-functional expectations** - with REQ IDs.
8. **Assumptions** - anything assumed where the BRD is silent. Each one must be easy to confirm or reject.
9. **Open questions** - numbered, each naming the REQ ID it blocks.
10. **Requirement register** - table: ID | Title | Type | Priority | Testable.

Flag contradictions inside the BRD explicitly rather than choosing a side.
