"""Does an owner's own 2025 pilot decision predict the 2026 truth? (brief 04 "Learning"). Offline only: reads labels.

python -m scripts.eval_learning
"""

from __future__ import annotations

import csv

from app import kit
from app.server.services.learning import pilot_history


def main() -> None:
    hist = pilot_history()
    n = {"approved": 0, "edited": 0, "declined": 0}
    hit = {"approved": 0, "edited": 0, "declined": 0}  # declined: the declined hours were NOT the truth
    shown_ok = {"approved": 0, "edited": 0}
    with open(kit.data_path("labels", "dev_labels_2026.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            prior = [h for h in hist.get(r["entity_id"], []) if h["day_key"] == r["day_key"]]
            if not prior:
                continue
            h = max(prior, key=lambda x: x["date"])
            o = h["outcome"]
            n[o] += 1
            if o == "declined":
                hit[o] += h["hours"] != r["truth_hours"]
            else:
                hit[o] += h["hours"] == r["truth_hours"]
                shown_ok[o] += r["displayed_hours_at_snapshot"] == r["truth_hours"]
    print("outcome in 2025 pilot -> 2026 dev labels for the same owner and day")
    for o, count in n.items():
        if count:
            extra = f"; what Google shows is right {shown_ok[o] / count:.0%}" if o in shown_ok else ""
            what = "declined hours were not the truth" if o == "declined" else "owner's hours = 2026 truth"
            print(f"  {o:9s} n={count:4d}  {what}: {hit[o] / count:.0%}{extra}")


if __name__ == "__main__":
    main()
