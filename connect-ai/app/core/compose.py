"""Deterministic email text. The LLM writes subject + intro only; everything else is here."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from app.core.i18n import (
    TEXT,
    eta_text,
    fmt_date,
    fmt_hours,
    fmt_number,
    publisher_name,
    weekday_name,
)
from app.core.models import WEEKDAYS, Contact, DateItem, OutboundMessage


def reason_for(basis: str | None, evidence: dict[str, Any] | None, lang: str) -> str:
    """Fill the matching reason_* key; '' for other or no basis."""
    ev = evidence or {}
    if basis == "LAST_YEAR":
        last = ev.get("last_year_hours") or ev.get("hours") or "closed"
        return TEXT[lang]["reason_LAST_YEAR"].format(last=fmt_hours(last, lang))
    if basis == "SHOPPING_CENTRE":
        return TEXT[lang]["reason_SHOPPING_CENTRE"].format(mall=ev.get("mall", ""))
    if basis in ("PEERS", "PATTERN"):
        text = TEXT[lang]["reason_PEERS" if basis == "PEERS" else "reason_PATTERN"]
        if ev.get("review_closed"):  # appended when the review signal contributed; never quote the review
            text += " " + TEXT[lang]["reason_REVIEWS"]
        return text
    if basis == "USER_EDIT":
        return TEXT[lang]["reason_USER_EDIT"]
    if basis in ("OWN_EDIT", "OWN_APPROVED"):
        return TEXT[lang]["reason_" + basis]
    if basis == "PATTERN_HOURS":
        return TEXT[lang]["reason_PATTERN_HOURS"]
    if basis == "LAST_EVENT":
        return TEXT[lang]["reason_LAST_EVENT"].format(last=fmt_hours(ev.get("hours") or "closed", lang))
    return ""


def round_2sf(n: int) -> int:
    """Round down to 2 significant figures (views_line)."""
    if n < 100:
        return n
    mag = 10 ** (len(str(n)) - 2)
    return (n // mag) * mag


def views_line(item: DateItem, last_year_views: int | None, lang: str, min_views: int) -> str | None:
    if last_year_views is None or last_year_views < min_views:
        return None
    return TEXT[lang]["views_line"].format(day_name=item.day_name, n=fmt_number(round_2sf(last_year_views), lang))


def _example(items: list[DateItem], lang: str) -> str:
    first = items[0].date if items else "2026-12-24"
    return f"{fmt_date(first, lang)} {fmt_hours('10:00-14:00', lang)}"


def _label(it: DateItem, lang: str) -> str:
    return f"{it.day_name} {weekday_name(it.date, lang)} {fmt_date(it.date, lang)}"


def group_items(items: list[DateItem], key: Callable[[DateItem], Any]) -> list[list[DateItem]]:
    """Group items that can share one line (same key). Groups and their members are ordered by date."""
    groups: dict[Any, list[DateItem]] = {}
    for it in sorted(items, key=lambda i: i.date):
        groups.setdefault(key(it), []).append(it)
    return list(groups.values())


def _tail(lang: str, sender_name: str) -> list[str]:
    return ["", TEXT[lang]["thanks"], sender_name, "", TEXT[lang]["footer"]]


def compose_body(
    msg: OutboundMessage,
    contact: Contact,
    lang: str,
    sender_name: str,
    *,
    views: str | None = None,
) -> str:
    """Full email body. `views` is the optional pre-built views_line (email only)."""
    T = TEXT[lang]
    lines = [T["greeting"].format(first_name=contact.first_name), "", msg.intro, ""]
    if msg.kind == "dates" and msg.mode == "ask":
        for grp in group_items(msg.items, lambda i: (i.shown_hours, i.suggested_hours, i.reason)):
            it = grp[0]
            shown = fmt_hours(it.shown_hours, lang)
            if len(grp) == 1:
                lines.append(
                    T["item_line"].format(
                        day_name=it.day_name,
                        weekday=weekday_name(it.date, lang),
                        date=fmt_date(it.date, lang),
                        shown=shown,
                    )
                )
            else:
                lines.append(T["item_line_group"].format(labels="; ".join(_label(g, lang) for g in grp), shown=shown))
            if it.suggested_hours is not None:
                lines.append(
                    T["suggest_line"].format(suggested=fmt_hours(it.suggested_hours, lang), reason=it.reason).rstrip()
                )
            else:
                lines.append(T["ask_line"])
        if views:
            lines += ["", views]
        lines.append("")
        has_suggestion = any(i.suggested_hours is not None for i in msg.items)
        key = "instructions_dates" if has_suggestion else "instructions_ask"
        lines.append(T[key].format(example=_example(msg.items, lang)))
    elif msg.kind == "dates":  # inform
        lines.append(T["inform_header"])
        for grp in group_items(msg.items, lambda i: i.suggested_hours or i.shown_hours):
            it = grp[0]
            hours = fmt_hours(it.suggested_hours or it.shown_hours, lang)
            if len(grp) == 1:
                lines.append(
                    T["inform_line"].format(
                        day_name=it.day_name,
                        weekday=weekday_name(it.date, lang),
                        date=fmt_date(it.date, lang),
                        hours=hours,
                    )
                )
            else:
                lines.append(T["inform_line_group"].format(labels="; ".join(_label(g, lang) for g in grp), hours=hours))
        lines += ["", T["instructions_inform"], T["inform_revoke"]]
    else:  # weekly
        lines.append(T["weekly_header"])
        weekly = msg.weekly_shown or {}
        for i, day in enumerate(WEEKDAYS):
            lines.append(
                T["weekly_line"].format(weekday=TEXT_WEEKDAY(lang, i), hours=fmt_hours(weekly.get(day, "closed"), lang))
            )
        lines += ["", T["instructions_weekly"]]
    lines += _tail(lang, sender_name)
    return "\n".join(lines)


def TEXT_WEEKDAY(lang: str, i: int) -> str:
    from app.core.i18n import WEEKDAY

    return WEEKDAY[lang][i]


def compose_permission_body(
    msg: OutboundMessage, contact: Contact, lang: str, sender_name: str, stats: dict | None = None
) -> str:
    """The permission request. `stats` = {"views","calls","actions"}; omitted below 50 views."""
    T = TEXT[lang]
    lines = [T["greeting"].format(first_name=contact.first_name), "", msg.intro, "", T["perm_pending_header"]]
    for it in msg.items:
        key = "perm_pending_line" if it.suggested_hours is not None else "perm_pending_line_ask"
        lines.append(
            T[key].format(
                day_name=it.day_name,
                weekday=weekday_name(it.date, lang),
                date=fmt_date(it.date, lang),
                shown=fmt_hours(it.shown_hours, lang),
                suggested=fmt_hours(it.suggested_hours or "closed", lang),
            )
        )
    lines += ["", T["perm_what_header"]]
    lines += [f"• {T[f'perm_what_{n}']}" for n in (1, 2, 3)]
    lines += ["", T["perm_benefits_header"]]
    lines += [f"• {T[f'perm_benefit_{n}']}" for n in (1, 2, 3)]
    if stats and stats.get("views", 0) >= 50:
        lines.append("")
        lines.append(
            T["perm_stats"].format(
                views=fmt_number(stats["views"], lang),
                calls=fmt_number(stats.get("calls", 0), lang),
                actions=fmt_number(stats.get("actions", 0), lang),
            )
        )
    lines += ["", T["perm_instructions"]]
    lines += _tail(lang, sender_name)
    return "\n".join(lines)


def _visible_lines(listings: list[dict], lang: str) -> list[str]:
    live = [x for x in listings if x.get("status") == "LIVE"]
    live.sort(key=lambda x: x.get("typicalUpdateSpeedSeconds", 0))
    if not live:
        return []
    out = [TEXT[lang]["fu_visible_header"]]
    for x in live[:5]:
        out.append(
            TEXT[lang]["fu_visible_line"].format(
                publisher=publisher_name(x.get("publisherId", ""), lang),
                eta=eta_text(int(x.get("typicalUpdateSpeedSeconds", 0)), lang),
            )
        )
    return out


def _applied_line(label: str, hours: str, lang: str, weekly: bool) -> str:
    if weekly:
        wd = TEXT_WEEKDAY(lang, WEEKDAYS.index(label))
        date = ""
    else:
        wd, date = weekday_name(label, lang), fmt_date(label, lang)
    line = TEXT[lang]["fu_applied_line"].format(weekday=wd, date=date, hours=fmt_hours(hours, lang))
    return line.replace(" :", ":").replace("  ", " ")


def compose_followup_applied(
    contact: Contact,
    lang: str,
    applied: list[tuple[str, str]],
    listings: list[dict],
    now: datetime | None = None,
    *,
    weekly: bool = False,
    offer_permission: bool = False,
    sender_name: str = "",
) -> str:
    """applied = [(date, hours)] or, for weekly updates, [(weekday, hours)]."""
    T = TEXT[lang]
    lines = [T["fu_applied_header"].format(first_name=contact.first_name)]
    lines += [_applied_line(a, h, lang, weekly) for a, h in applied]
    vis = _visible_lines(listings, lang)
    if vis:
        lines += [""] + vis
    if offer_permission:
        lines += ["", T["fu_offer_permission"]]
    lines += _tail(lang, sender_name) if sender_name else ["", T["footer"]]
    return "\n".join(lines)


def compose_followup_declined(contact: Contact, lang: str) -> str:
    return "\n".join([TEXT[lang]["fu_declined"].format(first_name=contact.first_name), "", TEXT[lang]["footer"]])


def compose_followup_stopped(lang: str) -> str:
    return TEXT[lang]["fu_stopped"]


def compose_followup_permission_granted(
    contact: Contact, lang: str, applied: list[tuple[str, str]], listings: list[dict]
) -> str:
    T = TEXT[lang]
    lines = [T["fu_perm_granted"]]
    lines += [_applied_line(a, h, lang, False) for a, h in applied]
    vis = _visible_lines(listings, lang)
    if vis:
        lines += [""] + vis
    lines += ["", T["fu_perm_granted_end"]]
    return "\n".join(lines)


def compose_followup_permission_declined(lang: str) -> str:
    return TEXT[lang]["fu_perm_declined"]


def compose_followup_revoked(lang: str) -> str:
    return TEXT[lang]["fu_revoked"]


def compose_sim_reply(decisions: list[dict], lang: str) -> str:
    """Owner-simulator reply in `template` mode. Each decision: {date, decision, final_hours, shown_hours}."""
    T = TEXT[lang]
    if decisions and all(d["decision"] == "ACCEPTED" for d in decisions):
        return T["sim_ok"]
    if decisions and all(d["decision"] == "REJECTED" for d in decisions):
        return T["sim_no"]
    parts = []
    for d in decisions:
        date = fmt_date(d["date"], lang)
        if d["decision"] == "ACCEPTED":
            parts.append(T["sim_date_ok"].format(date=date))
        elif d["decision"] == "EDITED":
            parts.append(T["sim_date_hours"].format(date=date, hours=fmt_hours(d["final_hours"], lang)))
        else:  # REJECTED: keep what Google shows
            parts.append(T["sim_date_hours"].format(date=date, hours=fmt_hours(d["shown_hours"], lang)))
    return ", ".join(parts)


def fallback_subject(template_id: str, lang: str) -> str:
    return TEXT[lang][f"fallback_subject_{template_id}"]


def fallback_intro(template_id: str, lang: str) -> str:
    return TEXT[lang][f"fallback_intro_{template_id}"]


def fallback_short(template_id: str, lang: str) -> str:
    return TEXT[lang][f"fallback_short_{template_id}"]
