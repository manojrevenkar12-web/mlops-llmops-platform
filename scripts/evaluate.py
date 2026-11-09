"""Run the release scenarios through the platform and the baselines; score every decision against the truth.

python scripts/evaluate.py dev       # development seeds: what the gates were built and tuned on
python scripts/evaluate.py heldout   # once, after config/heldout.lock is written; refuses a second run
"""

from __future__ import annotations

import json
import subprocess
import sys
import time

from paved.settings import ROOT, settings
from paved_eval.harness import run, summarise


def main(which: str) -> None:
    ev = settings()["evaluation"]
    out = ROOT / "reports" / f"{which}.json"
    if which == "heldout":
        if out.exists():
            sys.exit("reports/heldout.json exists: the held-out set runs once. Publish it as it came out.")
        check = subprocess.run(["python3", str(ROOT / "scripts" / "lock.py"), "verify"], capture_output=True, text=True)
        if check.returncode != 0:
            sys.exit("config/heldout.lock does not verify:\n" + check.stdout + check.stderr)
        seeds, exclude = ev["heldout_seeds"], []
    else:
        seeds, exclude = ev["dev_seeds"], ev["heldout_only_kinds"]
    t0 = time.time()
    events_dir = ROOT / "runs" / which
    events_dir.mkdir(parents=True, exist_ok=True)
    rows = run(seeds, exclude, workers=2, events_dir=str(events_dir))
    report = {
        "set": which,
        "seeds": seeds,
        "excluded_kinds": exclude,
        "summary": summarise(rows),
        "summary_by_workload": {
            w: summarise([r for r in rows if r["workload"] == w]) for w in ("pricing-conversion", "cs-email-agent")
        },
        "minutes": round((time.time() - t0) / 60, 1),
        "rows": rows,
    }
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(report, indent=1, default=float))
    print(json.dumps(report["summary"], indent=1))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "dev")
