#!/usr/bin/env python3
"""eval_sweep.py — Coverage guarantor for the RCA evaluation pipeline
(spec IN-1 / criteria M-70, automated).

Scans the machine for RCA state files, extracts every eval record that is
missing from the outbox (including aborted runs and stale abandoned runs),
lists runs still waiting for a judge score, writes a machine coverage report,
and optionally syncs the outbox to a shared folder for the aggregation
machine.

Designed for the ClineSR (Samsung Cline fork) + VS Code on Windows setup:
stdlib-only, no network, safe to run repeatedly (idempotent), scans %TEMP%
by default. Trigger it from a ClineSR task-completion hook, a VS Code
folderOpen task (.vscode/tasks.json), or Windows Task Scheduler — any or all;
extra runs are harmless.

Usage:
    python eval_sweep.py [--state-dir DIR ...] [--outbox DIR] [--scores DIR]
                         [--coverage DIR] [--sync-dir DIR] [--make-prompts]
                         [--stale-hours N] [--salt SALT] [--quiet]

Defaults:
    state dirs   system temp dir (%TEMP% / /tmp) + $RCA_STATE_DIRS
                 (os.pathsep-separated list)
    --outbox     <cwd>/.rca/eval/outbox
    --scores     <cwd>/.rca/eval/scores
    --coverage   <cwd>/.rca/eval/coverage
    --sync-dir   $RCA_EVAL_SYNC_DIR if set (UNC path works: \\\\server\\share)
    --stale-hours  24 — non-terminal state files older than this are
                 extracted as outcome=incomplete so abandoned runs still count

Exit codes: 0 full coverage, 4 coverage gaps remain (extraction errors).
"""

import argparse
import glob
import json
import os
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eval_extract import extract, _sha12  # noqa: E402

STATE_GLOB = "rca_state_*.json"


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def find_state_files(state_dirs):
    seen, out = set(), []
    for d in state_dirs:
        for path in glob.glob(os.path.join(d, STATE_GLOB)):
            real = os.path.realpath(path)
            if real not in seen:
                seen.add(real)
                out.append(path)
    return sorted(out)


def sweep_one(path, outbox, salt, stale_hours):
    """Extract the record for one state file if missing. Returns a status dict."""
    try:
        with open(path, encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        return {"state_file": path, "status": "unreadable", "error": str(e)}

    phase = (state.get("meta") or {}).get("current_phase", "")
    terminal = phase == "complete"
    if not terminal:
        age_h = (time.time() - os.path.getmtime(path)) / 3600
        if age_h < stale_hours:
            return {"state_file": path, "status": "in_progress", "phase": phase}

    try:
        record = extract(state, salt, None, state_path=path)
    except Exception as e:  # never let one bad state file stop the sweep
        return {"state_file": path, "status": "extract_error", "error": str(e)}

    out = os.path.join(outbox, f"eval_{record['run_id']}.json")
    if os.path.exists(out):
        return {"state_file": path, "status": "already_extracted",
                "run_id": record["run_id"], "outcome": record["outcome"]}

    os.makedirs(outbox, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)
    return {"state_file": path, "status": "extracted",
            "run_id": record["run_id"], "outcome": record["outcome"],
            "record": out}


def pending_judge(outbox, scores_dir):
    """Complete runs whose record exists but no scores_<run_id>.json yet."""
    pending = []
    for path in sorted(glob.glob(os.path.join(outbox, "eval_*.json"))):
        try:
            with open(path, encoding="utf-8") as f:
                rec = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        if rec.get("outcome") != "complete":
            continue
        run_id = rec.get("run_id")
        if not os.path.exists(os.path.join(scores_dir, f"scores_{run_id}.json")):
            pending.append({"run_id": run_id, "record": path,
                            "report_path": rec.get("report_path")})
    return pending


def make_prompts(pending, scores_dir):
    """Write self-contained judge prompts for pending runs (agent-as-judge
    flow on Gauss — see eval_judge.py). Skips runs whose report is missing."""
    from eval_judge import build_prompt  # local import: same directory
    made = []
    prompt_dir = os.path.join(scores_dir, "pending_prompts")
    for p in pending:
        report_path = p.get("report_path")
        if not (report_path and os.path.exists(report_path)):
            continue
        with open(p["record"], encoding="utf-8") as f:
            record = json.load(f)
        with open(report_path, encoding="utf-8") as f:
            report_text = f.read()
        os.makedirs(prompt_dir, exist_ok=True)
        out = os.path.join(prompt_dir, f"judge_prompt_{p['run_id']}.md")
        if not os.path.exists(out):
            with open(out, "w", encoding="utf-8") as f:
                f.write(build_prompt(report_text, record))
            made.append(out)
    return made


def sync_to(sync_dir, outbox, scores_dir, coverage_dir):
    """Copy records/scores/coverage to the shared sync folder. Copy-if-absent:
    records are idempotent by run_id, so this is safe to repeat."""
    copied = 0
    for src_dir, sub in ((outbox, "outbox"), (scores_dir, "scores"),
                         (coverage_dir, "coverage")):
        dst_dir = os.path.join(sync_dir, sub)
        for src in glob.glob(os.path.join(src_dir, "*.json")):
            dst = os.path.join(dst_dir, os.path.basename(src))
            if not os.path.exists(dst):
                os.makedirs(dst_dir, exist_ok=True)
                shutil.copy2(src, dst)
                copied += 1
    return copied


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--state-dir", action="append", default=[])
    ap.add_argument("--outbox", default=os.path.join(os.getcwd(), ".rca", "eval", "outbox"))
    ap.add_argument("--scores", default=os.path.join(os.getcwd(), ".rca", "eval", "scores"))
    ap.add_argument("--coverage", default=os.path.join(os.getcwd(), ".rca", "eval", "coverage"))
    ap.add_argument("--sync-dir", default=os.environ.get("RCA_EVAL_SYNC_DIR"))
    ap.add_argument("--make-prompts", action="store_true")
    ap.add_argument("--stale-hours", type=float, default=24.0)
    ap.add_argument("--salt", default=os.environ.get("RCA_EVAL_SALT", "rca-eval"))
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    state_dirs = list(args.state_dir) or []
    if not state_dirs:
        state_dirs = [tempfile.gettempdir()]
        env_dirs = os.environ.get("RCA_STATE_DIRS", "")
        state_dirs += [d for d in env_dirs.split(os.pathsep) if d.strip()]

    results = [sweep_one(p, args.outbox, args.salt, args.stale_hours)
               for p in find_state_files(state_dirs)]
    pending = pending_judge(args.outbox, args.scores)
    prompts = make_prompts(pending, args.scores) if args.make_prompts else []

    import socket
    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    covered = counts.get("extracted", 0) + counts.get("already_extracted", 0)
    gaps = counts.get("extract_error", 0) + counts.get("unreadable", 0)
    coverage_rate = covered / (covered + gaps) if (covered + gaps) else 1.0

    report = {
        "sweep_at": _now(),
        "machine_id": _sha12(socket.gethostname(), args.salt),
        "state_dirs": state_dirs,
        "counts": counts,
        "coverage_rate": round(coverage_rate, 3),
        "pending_judge": pending,
        "prompts_written": prompts,
        "results": results,
    }
    os.makedirs(args.coverage, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    cov_path = os.path.join(args.coverage,
                            f"coverage_{report['machine_id']}_{stamp}.json")
    with open(cov_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    latest = os.path.join(args.coverage, "coverage_latest.json")
    shutil.copy2(cov_path, latest)

    synced = 0
    if args.sync_dir:
        try:
            synced = sync_to(args.sync_dir, args.outbox, args.scores, args.coverage)
        except OSError as e:
            print(f"WARN: sync to {args.sync_dir} failed ({e}); "
                  f"records stay in the outbox for the next sweep", file=sys.stderr)

    if not args.quiet:
        print(f"Sweep done: {counts or 'no state files found'} · "
              f"coverage {coverage_rate:.0%} · pending judge: {len(pending)} · "
              f"synced: {synced} · report: {cov_path}")
        if gaps:
            for r in results:
                if r["status"] in ("extract_error", "unreadable"):
                    print(f"  GAP {r['state_file']}: {r.get('error')}", file=sys.stderr)
    return 4 if gaps else 0


if __name__ == "__main__":
    sys.exit(main())
