# Stage: Test Cases

Inputs: `scenarios.json`, `requirements.json`, `understanding.md`. Output: `test-cases.json`.

A test case is an executable procedure for one scenario. A tester who has never seen the BRD must be able to run it and decide pass or fail without asking anyone.

```json
[
  {
    "id": "TC-001",
    "scenario_id": "SC-001",
    "title": "Sixth login attempt is refused after five failures",
    "preconditions": ["Active user account exists", "Account is not currently locked"],
    "steps": [
      {"action": "Open the login page and enter the valid username with a wrong password. Repeat 5 times.",
       "data": "username: qa.user1 / password: Wrong#1",
       "expected": "Each attempt shows 'Invalid username or password'."},
      {"action": "Enter the valid username and the correct password.",
       "data": "password: <valid>",
       "expected": "Login is refused and a lockout message states the account is locked for 15 minutes."}
    ],
    "priority": "high"
  }
]
```

| Field | Rules |
|---|---|
| `id` | `TC-` + 3 digits. Permanent. |
| `scenario_id` | Exactly one existing scenario. |
| `preconditions` | Array or string. State, data and access needed before step 1. |
| `steps` | Array. Every step needs `action` and `expected`; `data` when a specific value matters. |
| `priority` | `high`, `medium`, `low` |

## Rules

- Every scenario needs at least one test case (submit fails otherwise). Use several when a scenario has distinct data variations, for example each boundary value.
- One objective per test case. Keep to about 3-8 steps; split longer ones.
- Expected results must be observable and specific: the message, the state, the value. Never "works correctly" or "as expected".
- Use concrete test data. Take limits and values from the requirement text. If the BRD gives no value, use a clearly marked placeholder such as `<valid amount>` rather than inventing a business rule.
- Make cases independent: each sets up its own preconditions and does not rely on another case having run.
- Do not restate the scenario as a single step.

On **revise** with `upstream_changes`: rework cases for changed scenarios, add cases for added scenarios, delete cases for removed scenarios. Leave the rest untouched.
