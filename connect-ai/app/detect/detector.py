"""DetectorV2. `decide` is pure; `DetectorV2` plugs into the Suggestions port."""

from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path

from app.detect.signals import Signals
from app.server.adapters.suggestions_baseline import BaselineSuggestions
from app.server.ports import Detection, TargetRow

MODEL_PATH = Path(__file__).with_name("model.json")
COPY_SOURCES = (  # in priority order; LAST_EVENT stays in the baseline (EVENT rows are not decided here)
    ("mall_hours", "SHOPPING_CENTRE"),
    ("last_year_exception", "LAST_YEAR"),
    ("last_year_user_edit", "USER_EDIT"),
)
DEFAULT_THRESHOLDS = {"closed_min_p": 0.7, "special_min_p": 1.01, "min_source_reliability": 0.6}


def load_model(path: Path = MODEL_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def prior_for(model: dict, f: dict) -> dict | None:
    pri = model["priors"]
    for key in (
        f"{f['country']}|{f['segment']}|{f['day_key']}",
        f"{f['country']}|*|{f['day_key']}",
        f"*|*|{f['day_key']}",
    ):
        p = pri.get(key)
        if p and (p["n"] >= 20 or key.startswith("*|*")):
            return p
    return None


def reliability(model: dict, f: dict, feat: str) -> float:
    rel = model["source_reliability"]
    if feat == "last_year_user_edit":
        return rel.get(f"last_year_user_edit|{f['last_year_user_edit_status']}", 0.0)
    return rel.get(feat, 0.0)


def closed_probability(model: dict, f: dict, prior: dict) -> tuple[float, list[str]]:
    lr, used = model["lr"], []
    p = min(max(prior["p_closed"], 1e-4), 1 - 1e-4)
    z = math.log(p / (1 - p))
    for name, val in (
        ("review_closed", "true" if f["review_closed"] else "false"),
        ("peer_bucket", f["peer_bucket"]),
        ("no_history", "true" if f["no_history"] else "false"),
    ):
        ratio = lr.get(name, {}).get(val)
        if ratio:
            z += math.log(ratio)
            used.append(name)
    return 1 / (1 + math.exp(-z)), used


def decide(f: dict, model: dict) -> dict:
    """Returns {action, hours, basis, confidence, signals, evidence}. The order is fixed."""
    th = {**DEFAULT_THRESHOLDS, **model.get("thresholds", {})}
    shown = f["shown"]
    out = {"action": "NO_ACTION", "hours": None, "basis": None, "confidence": None, "signals": [], "evidence": {}}
    if f["flag"]:
        return {**out, "action": "FLAG", "basis": "CLOSED_SIGNALS"}
    if f["already_entered"]:
        return {**out, "basis": "ALREADY_ENTERED", "evidence": {"entered": f["shown"]}}
    for feat, basis in COPY_SOURCES:
        cand = f.get(feat)
        if cand is None:
            continue
        rel = reliability(model, f, feat)
        if rel < th["min_source_reliability"]:
            continue
        ev = (
            {"mall": f["mall"]}
            if basis == "SHOPPING_CENTRE"
            else {"last_year_date": f["last_year_date"], "last_year_hours": cand}
        )
        sig = [f"{basis}: {cand} (source exact {rel:.0%} of the time in training)"]
        if cand == shown:
            return {**out, "basis": basis, "confidence": rel, "signals": sig, "evidence": ev}
        return {
            **out,
            "action": "SUGGEST",
            "hours": cand,
            "basis": basis,
            "confidence": rel,
            "signals": sig,
            "evidence": ev,
        }
    prior = prior_for(model, f)
    if prior is None:
        return out
    sig: list[str] = []
    pc, _used = closed_probability(model, f, prior)
    # DECISION: like the kit baseline, a peer-driven "closed" needs a real share of peers that entered closed
    # (>= 0.15 of all peer days). Without it, INTERDAY-style cells with few entries gave 136 harmful suggestions.
    peer_ok = f["review_closed"] or (f["peer_entered_closed"] or 0) >= th.get("peer_entered_closed_min", 0.15)
    if shown != "closed" and pc >= th["closed_min_p"] and peer_ok:
        if f["peer_closed"] is not None:
            sig.append(f"{f['peer_closed']:.0%} of similar businesses were closed (n={f['peer_n']})")
        if f["review_closed"]:
            sig.append("A review mentions being closed on this holiday")
        sig.append(f"Closed probability {pc:.0%} (prior {prior['p_closed']:.0%} for this segment and day)")
        basis = "PEERS" if f["peer_bucket"] != "none" else "PATTERN"
        ev = {"share": f["peer_closed"], "review_closed": f["review_closed"], "pc": round(pc, 3)}
        return {
            **out,
            "action": "SUGGEST",
            "hours": "closed",
            "basis": basis,
            "confidence": pc,
            "signals": sig,
            "evidence": ev,
        }
    if shown != "closed" and prior["p_special"] >= th["special_min_p"]:
        h = prior.get("special_hours") or f.get("peer_special")
        if h and h != shown:
            sig = [f"{prior['p_special']:.0%} of similar businesses use special hours (usually {h})"]
            return {
                **out,
                "action": "SUGGEST",
                "hours": h,
                "basis": "PATTERN_HOURS",
                "confidence": prior["p_special"],
                "signals": sig,
                "evidence": {"hours": h},
            }
    return out


class DetectorV2(BaselineSuggestions):
    """Subclass of the baseline adapter that overrides `detect()` only. EVENT rows keep the baseline logic."""

    def __init__(self, snapshot: date = date(2026, 11, 6), stale_days: int = 180, model: dict | None = None):
        super().__init__(snapshot, stale_days)
        self.model = model or load_model()
        self._signals: Signals | None = None

    def signals(self) -> Signals:
        if self._signals is None:
            self._signals = Signals(self, self.snapshot)
        return self._signals

    def detect(self, row: TargetRow) -> Detection:
        if row.day_key in ("EVENT", "SCHOOL_BREAK"):
            return super().detect(row)
        self._load()
        f = self.signals().features_for_row(row)
        r = decide(f, self.model)
        return Detection(
            action=r["action"],
            suggested_hours=r["hours"] if r["action"] == "SUGGEST" else None,
            shown_hours=f["shown"],
            shown_source=f["shown_source"],
            basis=r["basis"],
            evidence=r["evidence"],
            confidence=r["confidence"],
            signals=r["signals"],
        )
