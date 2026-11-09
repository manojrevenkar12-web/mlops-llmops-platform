"""Cost by team and the savings the platform can see, from a month of (simulated) tagged usage.

python scripts/cost_report.py    # writes reports/cost.json
"""

from __future__ import annotations

import json

from paved import cost
from paved.settings import ROOT
from paved_world.org import month


def main() -> None:
    records = month()
    recs = [r for rec in records for r in cost.recommend(rec)]
    workloads = [
        {"team": r.team, "workload": r.workload, "kind": r.kind, "spend_usd_month": round(cost.spend(r), 2)}
        for r in records
    ]
    total = sum(w["spend_usd_month"] for w in workloads)
    report = {
        "note": "Volumes are simulated; prices are list prices from config/prices.toml. Savings are estimates.",
        "total_spend_usd_month": round(total, 2),
        "by_team": {
            t: {k: round(v, 2) if isinstance(v, float) else v for k, v in d.items()}
            for t, d in sorted(cost.by_team(records).items(), key=lambda kv: -kv[1]["spend_usd_month"])
        },
        "workloads": sorted(workloads, key=lambda w: -w["spend_usd_month"]),
        "recommendations": sorted((r.to_dict() for r in recs), key=lambda r: -r["saving_usd_month"]),
        "identified_saving_usd_month": round(sum(r.saving_usd_month for r in recs), 2),
    }
    (ROOT / "reports" / "cost.json").write_text(json.dumps(report, indent=1))
    print(f"spend ${total:,.0f}/month, identified saving ${report['identified_saving_usd_month']:,.0f}/month")
    for r in report["recommendations"]:
        print(f"  {r['team']:20s} {r['workload']:28s} {r['action']:40s} ${r['saving_usd_month']:>10,.0f}")


if __name__ == "__main__":
    main()
