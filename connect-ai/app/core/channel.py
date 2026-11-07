"""Channel choice and one-line text helpers for WhatsApp / SMS. Pure."""

from __future__ import annotations

import re
from typing import Literal

from app.core.i18n import TEXT, WEEKDAY_SHORT, fmt_date, fmt_hours, weekday_short
from app.core.models import WEEKDAYS, Channel, Contact, DateItem, OutboundMessage

PREF = {"EMAIL": "email", "WHATSAPP": "whatsapp", "SMS": "sms", "APP_PUSH": "email"}
WA_BODY_LIMIT = 1024
SMS_LIMIT = 480


def channel_for(contact: Contact, enabled: set[str]) -> Channel:
    ch = PREF.get(contact.preferred_channel, "email")
    return ch if ch in enabled else "email"  # type: ignore[return-value]


def day_list(items: list[DateItem], lang: str, which: Literal["shown", "suggested"]) -> str:
    """'to 24.12. 8–20; to 31.12. 8–20'"""
    parts = []
    for it in items:
        hours = it.shown_hours if which == "shown" else (it.suggested_hours or it.shown_hours)
        parts.append(f"{weekday_short(it.date, lang)} {fmt_date(it.date, lang)} {fmt_hours(hours, lang)}")
    return "; ".join(parts)


def why_line(items: list[DateItem], lang: str) -> str:
    """Short, deduplicated reasons for the suggested items, e.g. 'same as last year; similar businesses are closed'."""
    out: list[str] = []
    for it in items:
        if it.suggested_hours is None or not it.basis:
            continue
        text = TEXT[lang].get(f"why_{it.basis}")
        if text and text not in out:
            out.append(text)
    return "; ".join(out)


def suggestion_list(items: list[DateItem], lang: str) -> str:
    """The suggested hours plus the reason, for the one-line WhatsApp and SMS formats."""
    base, why = day_list(items, lang, "suggested"), why_line(items, lang)
    return f"{base} ({TEXT[lang]['why_label']}: {why})" if why else base


def summarize_week(weekly: dict[str, str], lang: str) -> str:
    """Merge consecutive days with identical hours: 'ma–pe 8–20, la–su 10–16'."""
    groups: list[tuple[int, int, str]] = []
    for i, day in enumerate(WEEKDAYS):
        h = weekly.get(day, "closed")
        if groups and groups[-1][2] == h and groups[-1][1] == i - 1:
            groups[-1] = (groups[-1][0], i, h)
        else:
            groups.append((i, i, h))
    out = []
    for a, b, h in groups:
        names = WEEKDAY_SHORT[lang][a] if a == b else f"{WEEKDAY_SHORT[lang][a]}–{WEEKDAY_SHORT[lang][b]}"
        out.append(f"{names} {fmt_hours(h, lang)}")
    return ", ".join(out)


def wa_param(s: str) -> str:
    """Meta rejects newlines, tabs and runs of spaces in template parameters."""
    s = re.sub(r" {2,}", " ", s.replace("\n", " ").replace("\t", " ")).strip()
    return s if len(s) <= 300 else s[:299] + "…"


def digits(phone: str) -> str:
    return re.sub(r"\D", "", phone or "")


def phone_allowed(phone: str, entries: list[str]) -> bool:
    for e in entries:
        e = e.strip()
        if e == "*":
            return True
        if e and digits(e) == digits(phone):
            return True
    return False


def drop_lowest_priority(items: list[DateItem]) -> list[DateItem]:
    """Remove the lowest-priority item (ties: the latest date)."""
    worst = min(items, key=lambda i: (i.priority, [-ord(c) for c in i.date]))
    return [i for i in items if i is not worst]


def sms_text(message: OutboundMessage, contact: Contact, lang: str) -> tuple[str, int]:
    """(text, dropped_items). Drops the lowest-priority items until it is <= 480 characters."""
    T = TEXT[lang]
    items = sorted(message.items, key=lambda i: i.date)
    dropped = 0

    def render(its: list[DateItem]) -> str:
        if message.kind == "weekly":
            return T["sms_check"].format(
                business=message.entity_name, week=summarize_week(message.weekly_shown or {}, lang)
            )
        if message.mode == "inform":
            return T["sms_updated"].format(business=message.entity_name, applied=day_list(its, lang, "suggested"))
        short = message.short or T[f"fallback_short_{message.template_id}"]
        if any(i.suggested_hours is not None for i in its):
            return T["sms_suggestion"].format(
                business=message.entity_name,
                short=short,
                shown=day_list(its, lang, "shown"),
                suggested=suggestion_list(its, lang),
            )
        return T["sms_question"].format(business=message.entity_name, short=short, shown=day_list(its, lang, "shown"))

    text = render(items)
    while len(text) > SMS_LIMIT and len(items) > 1 and message.kind == "dates":
        items = drop_lowest_priority(items)
        dropped += 1
        text = render(items)
    return text, dropped
