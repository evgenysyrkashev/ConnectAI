"""Write predictions_2026.csv for the kit scorer. Same rules as the campaign builder.

    python -m scripts.export_predictions
    python ../evaluation/evaluate.py --predictions ../predictions_2026.csv

Covers every row of evaluation/targets_2026.csv in all splits: one SUGGEST row per kept suggestion, one FLAG row per
flagged business-date, everything else omitted (= NO_ACTION). Uses only data timestamped before the snapshot.
"""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from app.server.adapters.suggestions_baseline import BaselineSuggestions

OUT = Path(__file__).resolve().parents[2] / "predictions_2026.csv"  # kit repo root, not connect-ai/
CONFIDENCE = 0.6  # same as the kit baseline's file


def predictions(sg: BaselineSuggestions, *, use_rules: bool = True) -> list[tuple[str, str, str, str, float]]:
    sg._load()
    out = []
    for eid in sorted(sg.targets):
        for row in sg.rows_for(eid):
            if use_rules:
                det = sg.detect(row)
                act, hours, shown = det.action, det.suggested_hours or "", det.shown_hours
            else:  # plain kit baseline
                act, hours, _, _ = sg.bl.explain(eid, date.fromisoformat(row.date), row.day_key)
                shown = sg.bl.displayed(eid, date.fromisoformat(row.date))
            if act == "FLAG":
                out.append((eid, row.date, "FLAG", "", CONFIDENCE))
            elif act == "SUGGEST" and hours and hours != shown:
                out.append((eid, row.date, "SUGGEST", hours, CONFIDENCE))
    return out


def write(path: Path, rows) -> int:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["entity_id", "date", "action", "hours", "confidence"])
        w.writerows(rows)
    return len(rows)


def main() -> None:  # pragma: no cover
    import os

    if os.environ.get("SUGGESTIONS_MODE", "v2") == "baseline":
        sg: BaselineSuggestions = BaselineSuggestions()
    else:
        from app.detect.detector import DetectorV2

        sg = DetectorV2()
    n = write(OUT, predictions(sg))
    print(f"wrote {n} actions -> {OUT.name}")


if __name__ == "__main__":
    main()
