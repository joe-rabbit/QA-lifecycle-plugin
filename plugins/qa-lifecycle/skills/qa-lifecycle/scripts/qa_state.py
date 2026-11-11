#!/usr/bin/env python3
"""QA lifecycle state engine.

Owns every state transition for a QA run so the model never decides what
comes next. State lives on artifacts: each stage has a status and records
the hashes of the inputs it was built from, so staleness is derived, not
guessed.

Usage: qa_state.py <command> --run-dir DIR [options]
Commands: init, status, next, validate, submit, approve, reject,
          update-brd, export
All commands print JSON to stdout. Exit code 0 = ok, 1 = refused/invalid.
"""
import argparse
import csv
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_TEMPLATE = HERE.parent / "assets" / "test-plan-template.md"

# Ordered stages. deps = upstream artifacts whose approved content this stage consumes.
STAGES = [
    {"name": "understanding", "deps": ["brd"],
     "outputs": ["understanding.md", "requirements.json"],
     "guide": "references/stage-understanding.md"},
    {"name": "test_plan", "deps": ["understanding"],
     "outputs": ["test-plan.md"],
     "guide": "references/stage-test-plan.md"},
    {"name": "scenarios", "deps": ["understanding", "test_plan"],
     "outputs": ["scenarios.json"],
     "guide": "references/stage-scenarios.md"},
    {"name": "test_cases", "deps": ["scenarios"],
     "outputs": ["test-cases.json"],
     "guide": "references/stage-test-cases.md"},
]
STAGE = {s["name"]: s for s in STAGES}
ID_PATTERNS = {"REQ": re.compile(r"^REQ-\d{3,}$"),
               "SC": re.compile(r"^SC-\d{3,}$"),
               "TC": re.compile(r"^TC-\d{3,}$")}
PRIORITIES = {"high", "medium", "low"}
REQ_TYPES = {"functional", "non_functional"}
SC_TYPES = {"positive", "negative", "edge", "integration", "non_functional"}


class Refused(Exception):
    pass


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha(data):
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()[:16]


def file_hash(path):
    return sha(path.read_bytes()) if path.exists() else None


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise Refused(f"missing file: {path.name}")
    except json.JSONDecodeError as e:
        raise Refused(f"{path.name} is not valid JSON: {e}")


class Run:
    def __init__(self, run_dir):
        self.dir = Path(run_dir)
        self.path = self.dir / "state.json"
        if not self.path.exists():
            raise Refused(f"no run found at {self.dir} (run init first)")
        self.state = json.loads(self.path.read_text(encoding="utf-8"))
        self.refresh()

    # ---- persistence -------------------------------------------------
    def save(self):
        self.path.write_text(json.dumps(self.state, indent=2), encoding="utf-8")

    def log(self, event, **kw):
        self.state["history"].append({"at": now(), "event": event, **kw})

    # ---- hashing -----------------------------------------------------
    def outputs_hash(self, stage):
        parts = []
        for name in STAGE[stage]["outputs"]:
            h = file_hash(self.dir / name)
            if h is None:
                return None
            parts.append(f"{name}:{h}")
        return sha("|".join(parts))

    def dep_hash(self, dep):
        """Hash of a dependency's approved content, or None if not approved."""
        if dep == "brd":
            return self.state["brd"]["hash"]
        st = self.state["stages"][dep]
        return st.get("approved_hash") if st["status"] == "approved" else None

    def current_inputs(self, stage):
        return {d: self.dep_hash(d) for d in STAGE[stage]["deps"]}

    def fingerprints(self):
        """Per-item fingerprints used to tell a stale stage exactly what changed."""
        out = {}
        for key, fname, fields in (
            ("requirements", "requirements.json", ("title", "description", "testable")),
            ("scenarios", "scenarios.json", ("title", "description", "requirement_ids")),
        ):
            p = self.dir / fname
            if not p.exists():
                continue
            try:
                items = json.loads(p.read_text(encoding="utf-8"))
                out[key] = {i["id"]: sha(json.dumps([i.get(f) for f in fields], sort_keys=True))
                            for i in items if isinstance(i, dict) and "id" in i}
            except (json.JSONDecodeError, TypeError):
                continue
        return out

    # ---- derived staleness -------------------------------------------
    def refresh(self):
        """Re-derive staleness from hashes. Runs before every command."""
        changed = False
        for s in STAGES:
            name = s["name"]
            st = self.state["stages"][name]
            if st["status"] == "pending":
                continue
            reason = None
            if st["status"] == "approved" and self.outputs_hash(name) != st.get("approved_hash"):
                reason = "edited_after_approval"
            elif st["status"] in ("approved", "in_review", "changes_requested"):
                if self.current_inputs(name) != st.get("inputs"):
                    reason = "upstream_changed"
            if reason:
                st["status"] = "stale"
                st["stale_reason"] = reason
                for k in ("approved_hash", "approved_by", "approved_at"):
                    st.pop(k, None)
                self.log("stale", stage=name, reason=reason)
                changed = True
        if changed:
            self.state.pop("exported", None)
            self.save()

    # ---- validation --------------------------------------------------
    def validate(self, stage):
        errors, warnings, stats = [], [], {}
        d = self.dir

        def check_items(fname, prefix, required):
            items = load_json(d / fname)
            if not isinstance(items, list) or not items:
                errors.append(f"{fname} must be a non-empty JSON array")
                return []
            seen = set()
            good = []
            for n, it in enumerate(items):
                if not isinstance(it, dict):
                    errors.append(f"{fname}[{n}] is not an object")
                    continue
                iid = it.get("id", "")
                if not ID_PATTERNS[prefix].match(str(iid)):
                    errors.append(f"{fname}[{n}] id '{iid}' must look like {prefix}-001")
                if iid in seen:
                    errors.append(f"duplicate id {iid}")
                seen.add(iid)
                for f in required:
                    v = it.get(f)
                    if v is None or v == "" or v == []:
                        errors.append(f"{iid or fname + '[' + str(n) + ']'}: missing '{f}'")
                if "priority" in required and it.get("priority") not in PRIORITIES:
                    errors.append(f"{iid}: priority must be one of {sorted(PRIORITIES)}")
                good.append(it)
            return good

        if stage == "understanding":
            p = d / "understanding.md"
            if not p.exists() or len(p.read_text(encoding="utf-8").strip()) < 200:
                errors.append("understanding.md is missing or too short")
            reqs = check_items("requirements.json", "REQ",
                               ("title", "description", "type", "priority", "source_ref"))
            for r in reqs:
                if r.get("type") not in REQ_TYPES:
                    errors.append(f"{r.get('id')}: type must be one of {sorted(REQ_TYPES)}")
                if not isinstance(r.get("testable"), bool):
                    errors.append(f"{r.get('id')}: 'testable' must be true or false")
                elif not r["testable"] and not r.get("untestable_reason"):
                    errors.append(f"{r.get('id')}: untestable requirements need 'untestable_reason'")
            # IDs are permanent: nothing approved earlier may silently disappear.
            prior = self.state.get("known_ids", {}).get("requirements", [])
            gone = sorted(set(prior) - {r.get("id") for r in reqs})
            if gone:
                warnings.append(f"requirements removed since last approval: {gone}")
            stats = {"requirements": len(reqs),
                     "testable": sum(1 for r in reqs if r.get("testable") is True),
                     "open_questions": sum(len(r.get("open_questions") or []) for r in reqs)}

        elif stage == "test_plan":
            p = d / "test-plan.md"
            if not p.exists():
                errors.append("test-plan.md is missing")
            else:
                text = p.read_text(encoding="utf-8")
                tpl = d / "test-plan-template.md"
                if not tpl.exists():
                    tpl = DEFAULT_TEMPLATE
                heads = [h.strip() for h in re.findall(r"^##\s+(.+)$", tpl.read_text(encoding="utf-8"), re.M)]
                have = {h.strip().lower() for h in re.findall(r"^##\s+(.+)$", text, re.M)}
                missing = [h for h in heads if h.lower() not in have]
                if missing:
                    errors.append(f"test plan is missing template sections: {missing}")
                if re.search(r"\{\{.*?\}\}", text):
                    errors.append("test plan still contains {{placeholder}} text")
                reqs = load_json(d / "requirements.json")
                unref = [r["id"] for r in reqs if r.get("testable") and r["id"] not in text]
                if unref:
                    warnings.append(f"testable requirements not referenced in the plan: {unref}")
                stats = {"sections": len(have), "words": len(text.split())}

        elif stage == "scenarios":
            reqs = {r["id"]: r for r in load_json(d / "requirements.json")}
            scs = check_items("scenarios.json", "SC",
                              ("title", "description", "requirement_ids", "type", "priority"))
            covered = set()
            for s in scs:
                if s.get("type") not in SC_TYPES:
                    errors.append(f"{s.get('id')}: type must be one of {sorted(SC_TYPES)}")
                for rid in s.get("requirement_ids") or []:
                    if rid not in reqs:
                        errors.append(f"{s.get('id')}: unknown requirement {rid}")
                    covered.add(rid)
            uncovered = sorted(r for r, v in reqs.items() if v.get("testable") and r not in covered)
            if uncovered:
                errors.append(f"testable requirements with no scenario: {uncovered}")
            only_pos = sorted(r for r, v in reqs.items() if v.get("testable") and v.get("type") == "functional"
                              and r in covered and not any(
                                  r in (s.get("requirement_ids") or []) and s.get("type") in ("negative", "edge")
                                  for s in scs))
            if only_pos:
                warnings.append(f"functional requirements with no negative or edge scenario: {only_pos}")
            testable = [r for r, v in reqs.items() if v.get("testable")]
            stats = {"scenarios": len(scs),
                     "requirement_coverage": f"{len(testable) - len(uncovered)}/{len(testable)}"}

        elif stage == "test_cases":
            scs = {s["id"]: s for s in load_json(d / "scenarios.json")}
            tcs = check_items("test-cases.json", "TC",
                              ("scenario_id", "title", "preconditions", "steps", "priority"))
            covered = set()
            for t in tcs:
                sid = t.get("scenario_id")
                if sid not in scs:
                    errors.append(f"{t.get('id')}: unknown scenario {sid}")
                covered.add(sid)
                steps = t.get("steps") or []
                if not isinstance(steps, list):
                    errors.append(f"{t.get('id')}: steps must be an array")
                    continue
                for n, step in enumerate(steps, 1):
                    if not isinstance(step, dict) or not step.get("action") or not step.get("expected"):
                        errors.append(f"{t.get('id')} step {n}: needs both 'action' and 'expected'")
            uncovered = sorted(set(scs) - covered)
            if uncovered:
                errors.append(f"scenarios with no test case: {uncovered}")
            stats = {"test_cases": len(tcs),
                     "steps": sum(len(t.get("steps") or []) for t in tcs if isinstance(t.get("steps"), list)),
                     "scenario_coverage": f"{len(scs) - len(uncovered)}/{len(scs)}"}

        return {"stage": stage, "valid": not errors, "errors": errors,
                "warnings": warnings, "stats": stats}

    # ---- transitions -------------------------------------------------
    def require_deps(self, stage):
        blocked = [d for d, h in self.current_inputs(stage).items() if h is None]
        if blocked:
            raise Refused(f"cannot work on {stage}: upstream not approved: {blocked}")

    def submit(self, stage):
        st = self.state["stages"][stage]
        self.require_deps(stage)
        missing = [o for o in STAGE[stage]["outputs"] if not (self.dir / o).exists()]
        if missing:
            raise Refused(f"missing output files: {missing}")
        result = self.validate(stage)
        if not result["valid"]:
            return {"ok": False, "submitted": False, **result}
        st.update(status="in_review", inputs=self.current_inputs(stage),
                  submitted_hash=self.outputs_hash(stage), submitted_at=now(),
                  version=st.get("version", 0) + 1, built_from=self.fingerprints())
        st.pop("feedback", None)
        st.pop("stale_reason", None)
        self.log("submitted", stage=stage, version=st["version"])
        self.save()
        return {"ok": True, "submitted": True, "version": st["version"], **result,
                "next": "Present this artifact to the reviewer. Do not approve on their behalf."}

    def approve(self, stage, by):
        st = self.state["stages"][stage]
        if st["status"] != "in_review":
            raise Refused(f"{stage} is '{st['status']}', only in_review stages can be approved")
        if self.outputs_hash(stage) != st.get("submitted_hash"):
            raise Refused(f"{stage} files changed after submit; run submit again before approval")
        st.update(status="approved", approved_hash=st["submitted_hash"],
                  approved_by=by, approved_at=now())
        if stage == "understanding":
            ids = [r["id"] for r in load_json(self.dir / "requirements.json")]
            known = self.state.setdefault("known_ids", {})
            known["requirements"] = sorted(set(known.get("requirements", [])) | set(ids))
        self.log("approved", stage=stage, by=by, version=st["version"])
        self.save()
        return {"ok": True, "approved": stage, "by": by, "next_action": self.next()}

    def reject(self, stage, feedback, by):
        st = self.state["stages"][stage]
        if st["status"] != "in_review":
            raise Refused(f"{stage} is '{st['status']}', only in_review stages can be rejected")
        st.update(status="changes_requested", feedback=feedback)
        self.log("changes_requested", stage=stage, by=by, feedback=feedback)
        self.save()
        return {"ok": True, "changes_requested": stage, "next_action": self.next()}

    def changes_since_build(self, stage):
        """What changed upstream since this stage was last built (for targeted rework)."""
        old = self.state["stages"][stage].get("built_from") or {}
        new = self.fingerprints()
        out = {}
        for key in ("requirements", "scenarios"):
            if key not in old:
                continue
            o, n = old.get(key, {}), new.get(key, {})
            diff = {"added": sorted(set(n) - set(o)),
                    "removed": sorted(set(o) - set(n)),
                    "changed": sorted(k for k in set(o) & set(n) if o[k] != n[k])}
            if any(diff.values()):
                out[key] = diff
        return out

    def next(self):
        for s in STAGES:
            name = s["name"]
            st = self.state["stages"][name]
            status = st["status"]
            if status == "approved":
                continue
            base = {"stage": name, "status": status, "guide": s["guide"],
                    "outputs": s["outputs"],
                    "inputs": ["brd.md"] if name == "understanding" else
                              sorted({o for d in s["deps"] for o in STAGE[d]["outputs"]} | {"requirements.json"})}
            if status == "in_review":
                return {"action": "await_approval", **base,
                        "instruction": "Wait for the reviewer. Approve or reject only on their explicit word."}
            if status == "pending":
                return {"action": "generate", **base}
            if status == "changes_requested":
                return {"action": "revise", **base, "feedback": st.get("feedback")}
            if status == "stale":
                reason = st.get("stale_reason")
                if reason == "edited_after_approval":
                    return {"action": "revise", **base, "reason": reason,
                            "instruction": "Files were edited after approval. Keep the edits, "
                                           "submit again and ask for re-approval."}
                if name == "understanding":
                    return {"action": "revise", **base, "reason": "brd_changed",
                            "inputs": ["brd.md", "brd.previous.md"],
                            "instruction": "The BRD changed. Compare brd.md with brd.previous.md and update "
                                           "both outputs to match. Keep existing IDs; add new ones for new "
                                           "requirements."}
                return {"action": "revise", **base, "reason": reason,
                        "upstream_changes": self.changes_since_build(name),
                        "instruction": ("Keep existing IDs. Rework only items touched by upstream_changes; "
                                        "if nothing relevant changed, resubmit as is.")}
        if self.state.get("exported"):
            return {"action": "done", "exports": self.state["exported"]["files"]}
        return {"action": "export"}

    def status(self):
        return {"run": self.state["title"], "run_dir": str(self.dir),
                "brd": {"source": self.state["brd"]["source"], "hash": self.state["brd"]["hash"],
                        "captured_at": self.state["brd"]["captured_at"]},
                "stages": [{"stage": s["name"],
                            **{k: v for k, v in self.state["stages"][s["name"]].items()
                               if k in ("status", "version", "approved_by", "approved_at",
                                        "stale_reason", "feedback")}} for s in STAGES],
                "next_action": self.next()}

    def update_brd(self, brd_file):
        new = Path(brd_file).read_text(encoding="utf-8")
        h = sha(new)
        if h == self.state["brd"]["hash"]:
            return {"ok": True, "changed": False, "next_action": self.next()}
        shutil.copyfile(self.dir / "brd.md", self.dir / "brd.previous.md")
        (self.dir / "brd.md").write_text(new, encoding="utf-8")
        self.state["brd"].update(hash=h, captured_at=now())
        self.log("brd_changed", hash=h)
        self.refresh()
        self.save()
        return {"ok": True, "changed": True,
                "stale": [s["name"] for s in STAGES if self.state["stages"][s["name"]]["status"] == "stale"],
                "next_action": self.next()}

    def export(self):
        pending = [s["name"] for s in STAGES if self.state["stages"][s["name"]]["status"] != "approved"]
        if pending:
            raise Refused(f"cannot export: stages not approved: {pending}")
        reqs = load_json(self.dir / "requirements.json")
        scs = {s["id"]: s for s in load_json(self.dir / "scenarios.json")}
        tcs = load_json(self.dir / "test-cases.json")
        cases = self.dir / "test-cases.csv"
        with cases.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["Test Case ID", "Title", "Scenario ID", "Requirement IDs", "Priority", "Type",
                        "Preconditions", "Step", "Action", "Test Data", "Expected Result"])
            for t in tcs:
                sc = scs[t["scenario_id"]]
                pre = t["preconditions"]
                pre = "\n".join(pre) if isinstance(pre, list) else pre
                for n, step in enumerate(t["steps"], 1):
                    w.writerow([t["id"], t["title"], t["scenario_id"], ", ".join(sc["requirement_ids"]),
                                t["priority"], sc["type"], pre, n, step["action"],
                                step.get("data", ""), step["expected"]])
        trace = self.dir / "traceability.csv"
        with trace.open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["Requirement ID", "Requirement", "Testable", "Scenario IDs", "Test Case IDs"])
            for r in reqs:
                sids = [s for s, v in scs.items() if r["id"] in v["requirement_ids"]]
                tids = [t["id"] for t in tcs if t["scenario_id"] in sids]
                w.writerow([r["id"], r["title"], "yes" if r.get("testable") else "no",
                            ", ".join(sids), ", ".join(tids)])
        self.state["exported"] = {"at": now(), "files": [cases.name, trace.name]}
        self.log("exported")
        self.save()
        return {"ok": True, "files": [str(cases), str(trace)],
                "test_cases": len(tcs), "requirements": len(reqs)}


def init(run_dir, brd_file, source, title, template):
    d = Path(run_dir)
    if (d / "state.json").exists():
        raise Refused(f"a run already exists at {d}; use status/next to resume it")
    brd = Path(brd_file)
    if not brd.exists():
        raise Refused(f"BRD file not found: {brd}")
    text = brd.read_text(encoding="utf-8")
    if len(text.strip()) < 100:
        raise Refused("BRD content is empty or too short to work from")
    d.mkdir(parents=True, exist_ok=True)
    (d / "brd.md").write_text(text, encoding="utf-8")
    tpl_dst = d / "test-plan-template.md"
    shutil.copyfile(template or DEFAULT_TEMPLATE, tpl_dst)
    state = {"schema": 1, "title": title, "created_at": now(),
             "brd": {"source": source, "hash": sha(text), "captured_at": now()},
             "stages": {s["name"]: {"status": "pending"} for s in STAGES},
             "history": [{"at": now(), "event": "init", "source": source}]}
    (d / "state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
    return {"ok": True, "run_dir": str(d), "next_action": Run(d).next()}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def cmd(name, stage=False):
        p = sub.add_parser(name)
        p.add_argument("--run-dir", required=True)
        if stage:
            p.add_argument("stage", choices=list(STAGE))
        return p

    p = cmd("init")
    p.add_argument("--brd-file", required=True)
    p.add_argument("--source", required=True, help="URL or description of where the BRD came from")
    p.add_argument("--title", required=True)
    p.add_argument("--template", help="custom test plan template (markdown with ## sections)")
    cmd("status")
    cmd("next")
    cmd("validate", stage=True)
    cmd("submit", stage=True)
    p = cmd("approve", stage=True)
    p.add_argument("--by", required=True, help="name of the human who approved")
    p = cmd("reject", stage=True)
    p.add_argument("--feedback", required=True)
    p.add_argument("--by", default="reviewer")
    p = cmd("update-brd")
    p.add_argument("--brd-file", required=True)
    cmd("export")
    a = ap.parse_args()

    try:
        if a.cmd == "init":
            out = init(a.run_dir, a.brd_file, a.source, a.title, a.template)
        else:
            run = Run(a.run_dir)
            if a.cmd == "status":
                out = run.status()
            elif a.cmd == "next":
                out = run.next()
            elif a.cmd == "validate":
                out = run.validate(a.stage)
            elif a.cmd == "submit":
                out = run.submit(a.stage)
            elif a.cmd == "approve":
                out = run.approve(a.stage, a.by)
            elif a.cmd == "reject":
                out = run.reject(a.stage, a.feedback, a.by)
            elif a.cmd == "update-brd":
                out = run.update_brd(a.brd_file)
            elif a.cmd == "export":
                out = run.export()
    except Refused as e:
        print(json.dumps({"ok": False, "refused": str(e)}, indent=2))
        return 1
    print(json.dumps(out, indent=2))
    return 0 if out.get("ok", out.get("valid", True)) else 1


if __name__ == "__main__":
    sys.exit(main())
