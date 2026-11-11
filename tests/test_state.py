"""Smoke test for the state engine. Run: python3 -m unittest discover tests -v"""
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "plugins/qa-lifecycle/skills/qa-lifecycle/scripts/qa_state.py"

BRD = "# BRD: Login\n\n## 3.1 Login\nUsers log in with email and password.\n\n" \
      "## 3.2 Lockout\nAfter 5 failed attempts the account locks for 15 minutes.\n"
REQS = [
    {"id": "REQ-001", "title": "Login", "description": "Email and password login", "type": "functional",
     "priority": "high", "source_ref": "3.1", "testable": True},
    {"id": "REQ-002", "title": "Lockout", "description": "Lock after 5 failures", "type": "functional",
     "priority": "high", "source_ref": "3.2", "testable": True},
]
SCS = [
    {"id": "SC-001", "title": "Valid login", "description": "d", "requirement_ids": ["REQ-001"],
     "type": "positive", "priority": "high"},
    {"id": "SC-002", "title": "Lockout", "description": "d", "requirement_ids": ["REQ-002"],
     "type": "negative", "priority": "high"},
]
TCS = [
    {"id": "TC-001", "scenario_id": "SC-001", "title": "t", "preconditions": ["user exists"],
     "steps": [{"action": "log in", "expected": "home page shown"}], "priority": "high"},
    {"id": "TC-002", "scenario_id": "SC-002", "title": "t", "preconditions": "user exists",
     "steps": [{"action": "fail 5 times", "expected": "account locked message"}], "priority": "high"},
]


class Lifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.t = Path(self.tmp.name)
        self.run_dir = self.t / "run"
        (self.t / "brd.md").write_text(BRD)
        self.q("init", "--brd-file", str(self.t / "brd.md"), "--source", "test", "--title", "Login")

    def tearDown(self):
        self.tmp.cleanup()

    def q(self, *args):
        p = subprocess.run([sys.executable, str(SCRIPT), *args, "--run-dir", str(self.run_dir)],
                           capture_output=True, text=True)
        return json.loads(p.stdout)

    def write(self, name, data):
        (self.run_dir / name).write_text(data if isinstance(data, str) else json.dumps(data))

    def write_understanding(self, reqs=REQS):
        self.write("understanding.md", "# Understanding\n" + "Login feature summary. " * 20)
        self.write("requirements.json", reqs)

    def write_plan(self):
        t = (self.run_dir / "test-plan-template.md").read_text()
        t = re.sub(r"<!--.*?-->", "", t, flags=re.S)
        self.write("test-plan.md", re.sub(r"\{\{.*?\}\}", "Covers REQ-001 and REQ-002.", t))

    def pass_stage(self, stage):
        self.assertTrue(self.q("submit", stage)["submitted"])
        self.assertTrue(self.q("approve", stage, "--by", "tester")["ok"])

    def run_all(self):
        self.write_understanding(); self.pass_stage("understanding")
        self.write_plan(); self.pass_stage("test_plan")
        self.write("scenarios.json", SCS); self.pass_stage("scenarios")
        self.write("test-cases.json", TCS); self.pass_stage("test_cases")

    def statuses(self):
        return {s["stage"]: s["status"] for s in self.q("status")["stages"]}

    def test_happy_path_and_export(self):
        self.assertEqual(self.q("next")["action"], "generate")
        self.run_all()
        self.assertEqual(self.q("next")["action"], "export")
        self.assertTrue(self.q("export")["ok"])
        self.assertTrue((self.run_dir / "traceability.csv").exists())
        self.assertEqual(self.q("next")["action"], "done")

    def test_out_of_order_refused(self):
        self.assertIn("refused", self.q("submit", "scenarios"))
        self.assertIn("refused", self.q("export"))

    def test_approval_needs_review_and_unchanged_files(self):
        self.write_understanding()
        self.assertIn("refused", self.q("approve", "understanding", "--by", "x"))
        self.q("submit", "understanding")
        self.write_understanding(REQS[:1])
        self.assertIn("refused", self.q("approve", "understanding", "--by", "x"))

    def test_coverage_gates(self):
        self.write_understanding(); self.pass_stage("understanding")
        self.write_plan(); self.pass_stage("test_plan")
        self.write("scenarios.json", SCS[:1])
        r = self.q("submit", "scenarios")
        self.assertFalse(r["submitted"])
        self.assertIn("REQ-002", " ".join(r["errors"]))
        self.write("scenarios.json", SCS); self.pass_stage("scenarios")
        self.write("test-cases.json", TCS[:1])
        self.assertIn("SC-002", " ".join(self.q("submit", "test_cases")["errors"]))

    def test_reject_returns_feedback(self):
        self.write_understanding(); self.q("submit", "understanding")
        self.q("reject", "understanding", "--feedback", "split REQ-001")
        n = self.q("next")
        self.assertEqual((n["action"], n["feedback"]), ("revise", "split REQ-001"))

    def test_brd_change_cascades_and_reports_diff(self):
        self.run_all()
        (self.t / "brd2.md").write_text(BRD.replace("5 failed", "3 failed"))
        r = self.q("update-brd", "--brd-file", str(self.t / "brd2.md"))
        self.assertEqual(r["stale"], ["understanding", "test_plan", "scenarios", "test_cases"])
        self.assertEqual(r["next_action"]["reason"], "brd_changed")
        reqs = json.loads(json.dumps(REQS)); reqs[1]["description"] = "Lock after 3 failures"
        self.write_understanding(reqs); self.pass_stage("understanding")
        n = self.q("next")
        self.assertEqual(n["stage"], "test_plan")
        self.assertEqual(n["upstream_changes"]["requirements"]["changed"], ["REQ-002"])

    def test_edit_after_approval_goes_stale(self):
        self.run_all()
        with (self.run_dir / "scenarios.json").open("a") as f:
            f.write(" ")
        st = self.statuses()
        self.assertEqual((st["test_plan"], st["scenarios"], st["test_cases"]), ("approved", "stale", "stale"))


if __name__ == "__main__":
    unittest.main()
