#!/usr/bin/env python3
"""rca_eval_hook.py — ClineSR/VS Code hook entry point for the RCA
evaluation pipeline. Fire-and-forget wrapper around eval_sweep.py.

Wire this script to ANY automation point available on the user machine —
each one is optional, together they guarantee coverage (criteria M-70):

  * ClineSR task-completion hook (if your ClineSR build exposes Cline-style
    hooks in Settings -> Features): command = python <this file>
  * VS Code task with "runOn": "folderOpen"  (see .vscode/tasks.json)
  * Windows Task Scheduler (see evaluation/clinesr-windows-setup.md)

Contract: NEVER blocks or fails the calling task. Reads and discards stdin
(hook payloads vary between ClineSR builds), runs a quiet sweep with judge
prompt generation and outbox sync, always exits 0. All real logic lives in
eval_sweep.py; this file only provides the safe entry point.
"""

import os
import subprocess
import sys

WORKSPACE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SWEEP = os.path.join(WORKSPACE, "evaluation", "scripts", "eval_sweep.py")
LOG = os.path.join(WORKSPACE, ".rca", "eval", "hook.log")


def main():
    try:
        try:
            sys.stdin.read()  # drain hook payload, content not needed
        except Exception:
            pass
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as log:
            subprocess.run(
                [sys.executable, SWEEP, "--make-prompts", "--quiet"],
                cwd=WORKSPACE, stdout=log, stderr=log, timeout=120,
            )
    except Exception as e:  # a broken hook must never break the RCA task
        try:
            with open(LOG, "a", encoding="utf-8") as log:
                log.write(f"hook error: {e}\n")
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
