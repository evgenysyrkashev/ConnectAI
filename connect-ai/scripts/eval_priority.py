"""Findability ranking vs the dev labels. Offline only: reads labels.

python -m scripts.eval_priority
"""

from __future__ import annotations

import csv
from collections import defaultdict

import pandas as pd

from app import kit
from app.server.adapters.findability import ParquetFindability
from app.server.adapters.suggestions_baseline import BaselineSuggestions


def spearman(a: list[float], b: list[float]) -> float:
    return float(pd.Series(a).rank().corr(pd.Series(b).rank()))


def capture(order: list[str], value: dict[str, float], frac: float) -> float:
    n = max(1, round(len(order) * frac))
    total = sum(value.values())
    return sum(value[b] for b in order[:n]) / total if total else 0.0


def daily_cap(order: list[str], value: dict[str, float], k: int, days: int) -> float:
    total = sum(value.values())
    return sum(value[b] for b in order[: k * days]) / total if total else 0.0


def evaluate() -> dict:
    sg, fd = BaselineSuggestions(), ParquetFindability()
    with open(kit.data_path("labels", "dev_labels_2026.csv"), encoding="utf-8") as f:
        labels = {(r["entity_id"], r["date"]): r for r in csv.DictReader(f)}
    est, true = [], []
    for (eid, d), r in labels.items():
        if r["needs_action"] == "1":
            row = next((x for x in sg.rows_for(eid) if x.date == d), None)
            if row:
                est.append(fd.est_views(eid, d, row.day_key))
                true.append(float(r["expected_search_views"] or 0))
    rho = spearman(est, true)
    ours: dict[str, float] = defaultdict(float)  # our priority per business
    value: dict[str, float] = defaultdict(float)  # true at-risk views per business
    for eid in sorted({e for e, _ in labels}):
        for row in sg.rows_for(eid):
            det = sg.detect(row)
            if det.action == "SUGGEST" and det.suggested_hours != det.shown_hours and (eid, row.date) in labels:
                ours[eid] += fd.est_views(eid, row.date, row.day_key)
                lab = labels[(eid, row.date)]
                if lab["needs_action"] == "1":
                    value[eid] += float(lab["expected_search_views"] or 0)
    pool = sorted(ours)
    by_ours = sorted(pool, key=lambda b: -ours[b])
    by_true = sorted(pool, key=lambda b: -value[b])
    file_order = pool  # the baseline writes rows in entity-id order
    val = {b: value[b] for b in pool}
    out = {"spearman": rho, "rows": len(est), "businesses": len(pool), "capture": {}, "cap": {}}
    for frac in (0.1, 0.2, 0.5):
        out["capture"][frac] = {
            "ours": capture(by_ours, val, frac),
            "oracle": capture(by_true, val, frac),
            "random": frac,
        }
    for k in (25, 50, 100):
        out["cap"][k] = {
            d: {"priority": daily_cap(by_ours, val, k, d), "file_order": daily_cap(file_order, val, k, d)}
            for d in (1, 3, 7)
        }
    return out


def format_report(r: dict) -> str:
    L = [
        f"Spearman(est_views, expected_search_views) over {r['rows']} rows needing action: {r['spearman']:.3f}  (target >= 0.9)",
        f"\nBusiness-level capture of at-risk views ({r['businesses']} businesses with a suggestion):",
        f"{'top':>6}{'ours':>8}{'oracle':>8}{'random':>8}",
    ]
    for frac, v in r["capture"].items():
        L.append(f"{frac:>6.0%}{v['ours']:>8.0%}{v['oracle']:>8.0%}{v['random']:>8.0%}")
    L.append("\nShare of at-risk views contacted after N days at K messages/day (priority order vs file order):")
    L.append(f"{'K':>5}" + "".join(f"{'day ' + str(d):>16}" for d in (1, 3, 7)))
    for k, by_day in r["cap"].items():
        L.append(
            f"{k:>5}" + "".join(f"{by_day[d]['priority']:>8.0%} vs {by_day[d]['file_order']:>4.0%}" for d in (1, 3, 7))
        )
    return "\n".join(L)


if __name__ == "__main__":
    print(format_report(evaluate()))
