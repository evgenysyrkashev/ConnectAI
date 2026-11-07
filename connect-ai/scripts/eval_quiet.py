"""Who we contact vs the dev labels. Uses labels, so it is offline only.

    python -m scripts.eval_quiet               # 2026 season
    python -m scripts.eval_quiet --season 2025 # back-test; only data timestamped before 2025-11-06 is used

Items are built as the campaign builder would, from snapshot data only (no live Yext, no already-asked state).
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from types import SimpleNamespace

from app import kit
from app.server.adapters.suggestions_baseline import BaselineSuggestions
from app.server.config import Config
from app.server.services.campaigns import _is_ask_row

SNAP = {2026: date(2026, 11, 6), 2025: date(2025, 11, 6)}


def _labels(season: int) -> dict[tuple[str, str], int]:
    name = "dev_labels_2026.csv" if season == 2026 else "dev_labels_2025_backtest.csv"
    with open(kit.data_path("labels", name), encoding="utf-8") as f:
        return {(r["entity_id"], r["date"]): int(r["needs_action"]) for r in csv.DictReader(f)}


def _metrics(contacted: set, needed: set, universe: set) -> dict:
    c = contacted & universe
    n = needed & universe
    tp = len(c & n)
    return {
        "contacted": len(c),
        "needed": len(n),
        "precision": tp / len(c) if c else 0.0,
        "recall": tp / len(n) if n else 0.0,
        "needless_rate": (len(c) - tp) / len(c) if c else 0.0,
        "businesses_messaged": len({e for e, _ in c}),
        "businesses_needing": len({e for e, _ in n}),
    }


def evaluate(season: int = 2026) -> dict:
    sg = BaselineSuggestions(SNAP[season])
    sg._load()
    cfg = Config()
    ns = SimpleNamespace(suggestions=sg, cfg=cfg)
    labels = _labels(season)
    dev = {e for e, _ in labels}
    rows_by_tpl: dict[str, set] = {"holidays": set(), "event": set()}
    ours: dict[str, set] = {"holidays": set(), "event": set()}
    plain: dict[str, set] = {"holidays": set(), "event": set()}
    flagged_biz: set[str] = set()
    for eid in sorted(dev):
        rows = sg.rows_for(eid)
        ent = sg.bl.ents[eid]
        has_hist = sg.has_history(eid)
        dets = [(r, sg.detect(r)) for r in rows]
        flagged = any(d.action == "FLAG" for _, d in dets)
        if flagged:
            flagged_biz.add(eid)
        for r, d in dets:
            if (eid, r.date) not in labels:
                continue
            tpl = "event" if r.day_key == "EVENT" else ("holidays" if r.day_type != "LOCAL_EVENT" else None)
            if tpl is None:
                continue
            key = (eid, r.date)
            rows_by_tpl[tpl].add(key)
            base_act, _base_h, _, _ = sg.bl.explain(eid, date.fromisoformat(r.date), r.day_key)
            if base_act == "SUGGEST":
                plain[tpl].add(key)
            if flagged:
                continue
            if (
                d.action == "SUGGEST"
                and d.suggested_hours != d.shown_hours
                or tpl == "holidays"
                and d.action == "NO_ACTION"
                and _is_ask_row(ns, r, d, has_hist, ent)
            ):
                ours[tpl].add(key)
    needed = {k for k, v in labels.items() if v == 1}
    out: dict = {"season": season, "dev_entities": len(dev)}
    for tpl in ("holidays", "event"):
        out[tpl] = {
            "ours": _metrics(ours[tpl], needed, rows_by_tpl[tpl]),
            "baseline": _metrics(plain[tpl], needed, rows_by_tpl[tpl]),
        }
    # stale hours (2026 only: the regular-hours truth is a 2026 file)
    if season == 2026:
        truth: dict[str, int] = {}
        with open(kit.data_path("labels", "dev_regular_hours_truth.csv"), encoding="utf-8") as f:
            for r in csv.DictReader(f):
                truth[r["entity_id"]] = int(r["listing_is_outdated"])
        flagged_set = {e for e in truth if sg.stale_evidence(e)}
        outdated = {e for e, v in truth.items() if v}
        tp = len(flagged_set & outdated)
        out["stale"] = {
            "flagged": len(flagged_set),
            "outdated": len(outdated),
            "precision": tp / len(flagged_set) if flagged_set else 0.0,
            "recall": tp / len(outdated) if outdated else 0.0,
        }
    out["flagged_businesses"] = len(flagged_biz)
    return out


def targets_met(res: dict) -> dict[str, bool]:
    t = {
        "event precision >= 0.5": res["event"]["ours"]["precision"] >= 0.5,
        "holidays needless-row rate <= baseline": res["holidays"]["ours"]["needless_rate"]
        <= res["holidays"]["baseline"]["needless_rate"],
    }
    if "stale" in res:
        t["stale precision >= 0.5"] = res["stale"]["precision"] >= 0.5
    return t


def format_report(res: dict) -> str:
    L = [f"Season {res['season']}: {res['dev_entities']} dev businesses, {res['flagged_businesses']} flagged (skipped)"]
    for tpl in ("holidays", "event"):
        L.append(f"\n{tpl}:")
        L.append(
            f"  {'':10}{'contacted':>10}{'needed':>8}{'precision':>10}{'recall':>8}{'needless':>9}{'biz msg':>9}{'biz need':>9}"
        )
        for who in ("ours", "baseline"):
            m = res[tpl][who]
            L.append(
                f"  {who:10}{m['contacted']:>10}{m['needed']:>8}{m['precision']:>10.2f}{m['recall']:>8.2f}{m['needless_rate']:>9.2f}"
                f"{m['businesses_messaged']:>9}{m['businesses_needing']:>9}"
            )
    if "stale" in res:
        s = res["stale"]
        L.append(
            f"\nstale_hours: flagged {s['flagged']} businesses, {s['outdated']} outdated; precision {s['precision']:.2f}, recall {s['recall']:.2f}"
        )
    L.append("")
    L += [f"{'OK  ' if ok else 'MISS'} {name}" for name, ok in targets_met(res).items()]
    return "\n".join(L)


def main() -> None:  # pragma: no cover
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2026, choices=[2025, 2026])
    res = evaluate(ap.parse_args().season)
    print(format_report(res))
    sys.exit(0 if all(targets_met(res).values()) else 1)


if __name__ == "__main__":
    main()
