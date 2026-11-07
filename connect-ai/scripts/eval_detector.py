"""Detection quality on the dev labels: kit score, and precision per evidence basis (feeds the README table).

    python -m scripts.eval_detector [--season 2025]

Offline only (reads labels). Compares the plain kit baseline with our detector (baseline + already-entered and
event-night overrides + the stay-quiet rules). There is no learned DetectorV2 in this build.
"""

from __future__ import annotations

import argparse
import csv
import importlib.util
from collections import Counter, defaultdict
from datetime import date

from app import kit
from app.server.adapters.suggestions_baseline import BaselineSuggestions
from scripts.export_predictions import predictions

SNAP = {2026: date(2026, 11, 6), 2025: date(2025, 11, 6)}


def _kit_scorer():
    spec = importlib.util.spec_from_file_location("kit_evaluate", kit.data_path("evaluation", "evaluate.py"))
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _read_preds(rows) -> dict:
    return {(e, d): (a, h or "", c) for e, d, a, h, c in rows}


def evaluate(season: int = 2026) -> dict:
    sg = BaselineSuggestions(SNAP[season])
    sg._load()
    name = "dev_labels_2026.csv" if season == 2026 else "dev_labels_2025_backtest.csv"
    labels_path = kit.data_path("labels", name)
    with open(labels_path, encoding="utf-8") as f:
        labels = {(r["entity_id"], r["date"]): r for r in csv.DictReader(f)}
    scorer = _kit_scorer()
    scores = {}
    for who, use_rules in (("baseline", False), ("ours", True)):
        preds = {k: v for k, v in _read_preds(predictions(sg, use_rules=use_rules)).items() if k in labels}
        res = scorer.score(preds, labels_path)
        scores[who] = {
            k: res[k]
            for k in (
                "score_0_100",
                "precision_exact",
                "recall_exact",
                "harmful_suggestions",
                "search_views_protected_pct",
                "closed_door_views_prevented_pct",
                "businesses_contacted",
            )
        }
    by_basis: dict[str, Counter] = defaultdict(Counter)
    for (eid, d), lab in labels.items():
        row = next((r for r in sg.rows_for(eid) if r.date == d), None)
        if row is None:
            continue
        det = sg.detect(row)
        key = det.basis or "none"
        if det.action == "SUGGEST":
            by_basis[key]["suggested"] += 1
            by_basis[key]["exact"] += det.suggested_hours == lab["truth_hours"]
            by_basis[key]["needed"] += lab["needs_action"] == "1"
        elif det.basis == "ALREADY_ENTERED":
            by_basis[key]["suppressed"] += 1
            by_basis[key]["correct_silence"] += lab["needs_action"] == "0"
    return {"season": season, "scores": scores, "by_basis": {k: dict(v) for k, v in by_basis.items()}}


def format_report(res: dict) -> str:
    L = [
        f"Season {res['season']} (dev labels)",
        "",
        f"{'':10}{'score':>7}{'prec':>7}{'recall':>8}{'harmful':>9}{'views prot.%':>14}{'closed-door %':>15}{'businesses':>12}",
    ]
    for who in ("baseline", "ours"):
        s = res["scores"][who]
        L.append(
            f"{who:10}{s['score_0_100']:>7}{s['precision_exact']:>7}{s['recall_exact']:>8}{s['harmful_suggestions']:>9}"
            f"{s['search_views_protected_pct']:>14}{s['closed_door_views_prevented_pct']:>15}{s['businesses_contacted']:>12}"
        )
    L += ["", f"{'basis':18}{'suggested':>10}{'exact':>7}{'exact %':>9}{'needed %':>10}"]
    for k, v in sorted(res["by_basis"].items(), key=lambda kv: -kv[1].get("suggested", 0)):
        if "suggested" in v:
            L.append(
                f"{k:18}{v['suggested']:>10}{v['exact']:>7}{100 * v['exact'] / v['suggested']:>9.0f}{100 * v['needed'] / v['suggested']:>10.0f}"
            )
        else:
            L.append(
                f"{k:18}{'-':>10}  suppressed {v['suppressed']}, correct to stay silent {v['correct_silence']} ({100 * v['correct_silence'] / v['suppressed']:.0f}%)"
            )
    return "\n".join(L)


KEYS = (
    "score_0_100",
    "precision_exact",
    "recall_exact",
    "harmful_suggestions",
    "search_views_protected_pct",
    "closed_door_views_prevented_pct",
    "businesses_contacted",
)


def _score_subset(scorer, preds: dict, labels: dict, labels_path: str, keep) -> dict:
    """Score only the labelled rows whose entity passes `keep` (writes a temporary labels file)."""
    import tempfile

    with open(labels_path, encoding="utf-8") as f:
        rd = csv.DictReader(f)
        header = rd.fieldnames or []
        rows = [r for r in rd if keep(r["entity_id"])]
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="", encoding="utf-8") as tf:
        w = csv.DictWriter(tf, fieldnames=header)
        w.writeheader()
        w.writerows(rows)
    sub = {k: v for k, v in preds.items() if keep(k[0]) and k in labels}
    res = scorer.score(sub, tf.name)
    return {k: res[k] for k in KEYS}


def _by_basis(sg, labels: dict, keep) -> dict[str, Counter]:
    out: dict[str, Counter] = defaultdict(Counter)
    for (eid, d), lab in labels.items():
        if not keep(eid):
            continue
        row = next((r for r in sg.rows_for(eid) if r.date == d), None)
        if row is None:
            continue
        det = sg.detect(row)
        if det.action == "SUGGEST":
            c = out[det.basis or "none"]
            c["suggested"] += 1
            c["exact"] += det.suggested_hours == lab["truth_hours"]
            c["needed"] += lab["needs_action"] == "1"
    return out


def evaluate_v2() -> dict:
    """entity folds on the 2026 season, and the 2025 back-test; always against the kit baseline."""
    from app.detect.detector import DetectorV2
    from scripts.train_detector import entity_filter, train

    scorer = _kit_scorer()
    out: dict = {"folds": [], "backtest": None}
    for season, snap_date in ((2026, SNAP[2026]), (2025, SNAP[2025])):
        name = "dev_labels_2026.csv" if season == 2026 else "dev_labels_2025_backtest.csv"
        labels_path = kit.data_path("labels", name)
        with open(labels_path, encoding="utf-8") as f:
            labels = {(r["entity_id"], r["date"]): r for r in csv.DictReader(f)}
        plan = [("foldA", "foldB"), ("foldB", "foldA")] if season == 2026 else [("all", "all")]
        for train_on, test_on in plan:
            model, _ = train(snap_date, train_on)
            v2 = DetectorV2(snap_date, model=model)
            keep = entity_filter(test_on)
            base = BaselineSuggestions(snap_date)
            res = {"season": season, "train": train_on, "test": test_on}
            for who, sg, rules in (("baseline", base, False), ("ours", base, True), ("v2", v2, True)):
                preds = _read_preds(predictions(sg, use_rules=rules))
                res[who] = _score_subset(scorer, preds, labels, labels_path, keep)
            res["by_basis"] = {k: dict(v) for k, v in _by_basis(v2, labels, keep).items()}
            if season == 2026:
                out["folds"].append(res)
            else:
                out["backtest"] = res
    return out


def format_v2(res: dict) -> str:
    L: list[str] = []
    runs = [("2026 fold mean", res["folds"]), ("2025 back-test", [res["backtest"]])]
    for title, rs in runs:
        L += [
            "",
            title,
            f"{'':10}{'score':>7}{'prec':>7}{'recall':>8}{'harmful':>9}{'views prot.%':>14}{'closed-door %':>15}{'businesses':>12}",
        ]
        for who in ("baseline", "ours", "v2"):
            m = {k: sum(r[who][k] for r in rs) / len(rs) for k in KEYS}
            L.append(
                f"{who:10}{m['score_0_100']:>7.2f}{m['precision_exact']:>7.3f}{m['recall_exact']:>8.3f}{m['harmful_suggestions']:>9.0f}"
                f"{m['search_views_protected_pct']:>14.1f}{m['closed_door_views_prevented_pct']:>15.1f}{m['businesses_contacted']:>12.0f}"
            )
        agg: dict[str, Counter] = defaultdict(Counter)
        for r in rs:
            for k, v in r["by_basis"].items():
                agg[k].update(v)
        L += ["", f"{'v2 basis':18}{'suggested':>10}{'exact':>7}{'exact %':>9}{'needed %':>10}"]
        for k, v in sorted(agg.items(), key=lambda kv: -kv[1]["suggested"]):
            L.append(
                f"{k:18}{v['suggested']:>10}{v['exact']:>7}{100 * v['exact'] / v['suggested']:>9.0f}{100 * v['needed'] / v['suggested']:>10.0f}"
            )
    return "\n".join(L)


def main() -> None:  # pragma: no cover
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=2026, choices=[2025, 2026])
    ap.add_argument("--v2", action="store_true", help="evaluate DetectorV2 (entity folds + 2025 back-test)")
    a = ap.parse_args()
    if a.v2:
        print(format_v2(evaluate_v2()))
    else:
        print(format_report(evaluate(a.season)))


if __name__ == "__main__":
    main()
