"""Usual answering time per channel, from data/pilot_decision_log_2025.csv (kit data)."""

from __future__ import annotations

import csv
from datetime import datetime
from statistics import median

from app import kit
from app.core.timeutil import parse_iso

FALLBACK = {"WHATSAPP": 0.4, "SMS": 1.1, "EMAIL": 9.4, "APP_PUSH": 5.2}


def channel_medians(path: str | None = None) -> dict[str, float]:
    try:
        with open(path or kit.data_path("data", "pilot_decision_log_2025.csv"), encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except FileNotFoundError:
        return dict(FALLBACK)
    best: dict[str, tuple[str, float]] = {}  # message_id -> (channel, latency h)
    for r in rows:
        if not r["decided_at"] or not r["sent_at"]:
            continue
        h = (datetime.fromisoformat(r["decided_at"]) - datetime.fromisoformat(r["sent_at"])).total_seconds() / 3600
        prev = best.get(r["message_id"])
        if prev is None or h < prev[1]:  # earliest decision
            best[r["message_id"]] = (r["channel"], h)
    per: dict[str, list[float]] = {}
    for ch, h in best.values():
        per.setdefault(ch, []).append(h)
    out = dict(FALLBACK)
    out.update({ch: round(median(v), 2) for ch, v in per.items() if v})
    return out


class ResponseStats:
    def __init__(self, store, medians: dict[str, float] | None = None):
        self.store = store
        self.medians = medians if medians is not None else channel_medians()

    def usual_hours(self, eid: str, channel: str) -> tuple[float, str]:
        key = channel.upper()
        lat: list[float] = []
        for m in self.store.list_messages_for_entity(eid, 200):
            if m.channel != channel or not m.sent_at:
                continue
            ans = [
                r
                for r in self.store.list_replies_for_message(m.id)
                if r.status in ("applied", "needs_review", "rejected")
            ]
            if ans:
                first = parse_iso(min(r.received_at for r in ans))
                lat.append((first - parse_iso(m.sent_at)).total_seconds() / 3600)
        if len(lat) >= 2:
            return float(median(lat)), "owner"
        return self.medians.get(key, FALLBACK.get(key, 9.4)), "channel"
