"""Train DetectorV2: writes app/detect/model.json (aggregates only, no entity ids).

    python -m scripts.train_detector [--as-of-train 2026-11-06] [--train-entities all|foldA|foldB] [--out PATH]

`--as-of-train` is the snapshot the model will be used at. Priors use truth before it; the likelihood ratios, source
reliabilities and thresholds are fitted on the previous season (truth dated in the 61 days after `as_of_train - 1 year`,
features computed as of that earlier snapshot), so nothing leaks into the season being predicted.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

from app import kit
from app.detect.detector import decide
from app.detect.signals import Signals
from app.server.adapters.suggestions_baseline import BaselineSuggestions

OUT = Path(__file__).resolve().parents[1] / "app" / "detect" / "model.json"
SKIP_KEYS = {"EVENT", "SCHOOL_BREAK"}
CLOSED_MIN = [0.5 + 0.05 * i for i in range(10)]
SPECIAL_MIN = [
    0.9,
    1.01,
]  # DECISION: lower values gave PATTERN_HOURS only 11-12% exact (measured): "very sure" or never
RELIABILITY_MIN = [0.5, 0.6, 0.7, 0.8]


def fold_of(eid: str) -> int:
    return int(hashlib.sha256(eid.encode()).hexdigest()[:8], 16) % 2


def entity_filter(which: str):
    if which == "all":
        return lambda eid: True
    want = 0 if which == "foldA" else 1
    return lambda eid: fold_of(eid) == want


def minus_year(d: date) -> date:
    return d.replace(year=d.year - 1, day=28) if (d.month, d.day) == (2, 29) else d.replace(year=d.year - 1)


def read_truth(keep) -> list[dict]:
    with open(kit.data_path("labels", "dev_truth_history.csv"), encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r["day_key"] not in SKIP_KEYS and keep(r["entity_id"])]


def _mins(t: str) -> int:
    return int(t[:2]) * 60 + int(t[3:5])


def _fmt(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def classify(truth: str, regular: str) -> str:
    return "closed" if truth == "closed" else "regular" if truth == regular else "special"


def build_priors(sg: BaselineSuggestions, truth: list[dict], before: date) -> dict:
    sig = Signals(sg, before)
    cells: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for r in truth:
        if r["date"] >= before.isoformat():
            continue
        eid, d = r["entity_id"], date.fromisoformat(r["date"])
        ent = sg.bl.ents.get(eid)
        if ent is None:
            continue
        country, seg = ent["meta"]["countryCode"], ent.get("c_segment")
        cls = classify(r["truth_hours"], sig.regular(eid, d))
        item = (cls, r["truth_hours"])
        for key in (f"{country}|{seg}|{r['day_key']}", f"{country}|*|{r['day_key']}", f"*|*|{r['day_key']}"):
            cells[key].append(item)
    out = {}
    for key, items in cells.items():
        n = len(items)
        cnt = Counter(c for c, _ in items)
        denom = n + 3  # Laplace +1 per class
        special = [h for c, h in items if c == "special" and "-" in h and "," not in h]
        sh = None
        if special:
            o = statistics.median_low(_mins(h.split("-")[0]) for h in special)
            c_ = statistics.median_low(_mins(h.split("-")[1]) for h in special)
            sh = f"{_fmt(o)}-{_fmt(c_)}"
        out[key] = {
            "n": n,
            "p_closed": round((cnt["closed"] + 1) / denom, 4),
            "p_regular": round((cnt["regular"] + 1) / denom, 4),
            "p_special": round((cnt["special"] + 1) / denom, 4),
            "special_hours": sh,
        }
    return out


def _near(a: str, b: str) -> bool:
    if "," in a or "," in b or a == "closed" or b == "closed":
        return False
    try:
        return abs(_mins(a[:5]) - _mins(b[:5])) <= 30 and abs(_mins(a[6:11]) - _mins(b[6:11])) <= 30
    except ValueError:
        return False


HARM_EXTRA = 2.0  # DECISION: a wrong open/closed state costs 3 instead of 1 in the grid search


def row_points(action: str, hours: str | None, truth: str, shown: str) -> float:
    """The kit scorer's points for one row (without FLAG rules)."""
    if action != "SUGGEST":
        return 0.0
    if truth != shown:
        if hours == truth:
            return 1.0
        if (hours == "closed") != (truth == "closed"):
            return -1.0
        return 0.6 if _near(hours or "", truth) else 0.2
    if hours == shown:
        return -0.1
    return -1.0 if (hours == "closed") != (shown == "closed") else -0.5


def fit(sg: BaselineSuggestions, as_of_train: date, keep) -> tuple[dict, dict]:
    """Returns (model, report). Fitted on the season before `as_of_train`."""
    as_of_s = minus_year(as_of_train)
    truth_all = read_truth(keep)
    lo, hi = as_of_s.isoformat(), (as_of_s + timedelta(days=61)).isoformat()
    season = [r for r in truth_all if lo < r["date"] <= hi]
    priors_fit = build_priors(sg, truth_all, as_of_s)
    sig = Signals(sg, as_of_s)
    rows = []
    for r in season:
        eid = r["entity_id"]
        if eid not in sg.bl.ents:
            continue
        f = sig.features(eid, date.fromisoformat(r["date"]), r["day_key"])
        if f["flag"] or f["already_entered"]:
            continue
        rows.append((f, r["truth_hours"]))
    # source reliability: exact-match rate of each copy candidate
    hit: Counter = Counter()
    tot: Counter = Counter()
    for f, truth in rows:
        for feat in ("mall_hours", "last_year_exception"):
            if f[feat] is not None:
                tot[feat] += 1
                hit[feat] += f[feat] == truth
        if f["last_year_user_edit"] is not None:
            k = f"last_year_user_edit|{f['last_year_user_edit_status']}"
            tot[k] += 1
            hit[k] += f["last_year_user_edit"] == truth
    reliability = {k: round((hit[k]) / tot[k], 4) for k in tot if tot[k] >= 10}
    # likelihood ratios for "truth is closed"
    n_closed = sum(t == "closed" for _, t in rows)
    n_other = len(rows) - n_closed
    lr: dict[str, dict[str, float]] = {}
    for name, getter, values in (
        ("review_closed", lambda f: "true" if f["review_closed"] else "false", ["true", "false"]),
        ("peer_bucket", lambda f: f["peer_bucket"], ["none", "<0.2", "0.2-0.5", "0.5-0.8", ">=0.8"]),
        ("no_history", lambda f: "true" if f["no_history"] else "false", ["true", "false"]),
    ):
        k = len(values)
        lr[name] = {}
        for v in values:
            c = sum(1 for f, t in rows if t == "closed" and getter(f) == v)
            o = sum(1 for f, t in rows if t != "closed" and getter(f) == v)
            lr[name][v] = round(((c + 1) / (n_closed + k)) / ((o + 1) / (n_other + k)), 4)
    model = {"priors": priors_fit, "source_reliability": reliability, "lr": lr, "thresholds": {}}
    # grid-search thresholds on the kit's scoring rules
    best = None
    needed = max(1, sum(1 for f, t in rows if t != f["shown"]))
    for rmin in RELIABILITY_MIN:
        for cmin in CLOSED_MIN:
            for smin in SPECIAL_MIN:
                model["thresholds"] = {"closed_min_p": cmin, "special_min_p": smin, "min_source_reliability": rmin}
                pts = 0.0
                for f, t in rows:
                    d = decide(f, model)
                    p = row_points(d["action"], d["hours"], t, f["shown"])
                    pts += p - HARM_EXTRA if p == -1.0 else p
                key = (round(100 * pts / needed, 3), rmin, cmin, -smin)
                if best is None or key > best[0]:
                    best = (key, dict(model["thresholds"]))
    assert best is not None
    model["thresholds"] = best[1]
    report = {"fit_rows": len(rows), "fit_points_pct": best[0][0], "thresholds": best[1]}
    return model, report


def train(as_of_train: date, entities: str = "all", sg: BaselineSuggestions | None = None) -> tuple[dict, dict]:
    keep = entity_filter(entities)
    sg = sg or BaselineSuggestions(as_of_train)
    sg._load()
    model, report = fit(sg, as_of_train, keep)
    model["priors"] = build_priors(sg, read_truth(keep), as_of_train)
    model["trained"] = {"as_of_train": as_of_train.isoformat(), "entities": entities, **report}
    return model, report


def main() -> None:  # pragma: no cover
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of-train", default="2026-11-06")
    ap.add_argument("--train-entities", default="all", choices=["all", "foldA", "foldB"])
    ap.add_argument("--out", default=str(OUT))
    a = ap.parse_args()
    model, report = train(date.fromisoformat(a.as_of_train), a.train_entities)
    Path(a.out).write_text(json.dumps(model, indent=1, sort_keys=True), encoding="utf-8")
    print(json.dumps(report), "->", a.out)


if __name__ == "__main__":
    main()
