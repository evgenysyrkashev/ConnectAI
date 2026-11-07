"""Owner-facing text in fi/sv/nb must contain no English strings."""

import csv

import pytest

from app import kit
from app.core import compose, i18n
from app.core.channel import day_list, sms_text, summarize_week
from app.core.i18n import TEXT
from app.core.models import Contact
from app.core.wa_templates import render_body, wa_content
from tests.conftest import make_contact, make_item, make_message

SENDER = "ConnectAI (demo)"
CONTACTS = {("FI", "sv"): "sv", ("SE", "sv"): "sv", ("NO", "nb"): "nb", ("FI", "fi"): "fi"}
LISTINGS = [
    {"status": "LIVE", "publisherId": p, "typicalUpdateSpeedSeconds": s}
    for p, s in [("GOOGLEMYBUSINESS", 120), ("APPLE", 172800), ("WAZE", 3600), ("CHATGPT_SEARCH", 604800)]
]
PUBLISHER_EN = ["Google Search and Maps", "AI assistants"]  # Apple Maps is a brand, identical in fi/en


def _en_values():
    return {v for v in TEXT["en"].values() if len(v) > 12}


def _calendar_en():
    with open(kit.data_path("data", "calendar_special_days.csv"), encoding="utf-8") as f:
        names = {r["name_en"] for r in csv.DictReader(f)}
    return names


def _renders(lang: str, contact: Contact) -> list[str]:
    out: list[str] = []
    items = [
        make_item("2026-12-24", "closed", reason=compose.reason_for("LAST_YEAR", {"last_year_hours": "closed"}, lang)),
        make_item("2026-12-31", "10:00-14:00", reason=compose.reason_for("PEERS", None, lang)),
        make_item("2027-01-01", None, basis=None),
    ]
    for kind, mode in (("dates", "ask"), ("dates", "inform"), ("weekly", "ask")):
        m = make_message(
            items if kind == "dates" else None,
            kind=kind,
            mode=mode,
            lang=lang,
            intro=i18n.TEXT[lang]["fallback_intro_holidays"],
        )
        views = compose.views_line(items[0], 340, lang, 20)
        out.append(compose.compose_body(m, contact, lang, SENDER, views=views))
        out.append(sms_text(m, contact, lang)[0])
        name, params, _ = wa_content(m, contact, lang)
        out.append(render_body(name, lang, params))
    out.append(day_list(items, lang, "shown") + summarize_week({"monday": "closed"}, lang))
    perm = make_message(items, template_id="permission", kind="permission", lang=lang)
    out.append(compose.compose_permission_body(perm, contact, lang, SENDER, {"views": 1234, "calls": 3, "actions": 4}))
    applied = [("2026-12-24", "closed")]
    out.append(compose.compose_followup_applied(contact, lang, applied, LISTINGS, None, offer_permission=True))
    out.append(compose.compose_followup_applied(contact, lang, [("monday", "closed")], LISTINGS, None, weekly=True))
    out.append(compose.compose_followup_declined(contact, lang))
    out.append(compose.compose_followup_stopped(lang))
    out.append(compose.compose_followup_permission_granted(contact, lang, applied, LISTINGS))
    out.append(compose.compose_followup_permission_declined(lang))
    out.append(compose.compose_followup_revoked(lang))
    out.append(
        compose.compose_sim_reply(
            [{"date": "2026-12-24", "decision": "EDITED", "final_hours": "closed", "shown_hours": "closed"}], lang
        )
    )
    for tpl in ("holidays", "event", "stale_hours", "permission"):
        out += [
            compose.fallback_subject(tpl, lang),
            compose.fallback_intro(tpl, lang),
            compose.fallback_short(tpl, lang),
        ]
    for k in (
        "wa_prompt_edit",
        "wa_prompt_edit_weekly",
        "wa_unsupported",
        "wa_visibility_fallback",
        "sms_declined",
        "sms_stopped",
    ):
        out.append(TEXT[lang][k])
    return out


@pytest.mark.parametrize("combo", list(CONTACTS))
def test_no_english_leak(combo):
    country, lang = combo
    contact = make_contact(lang, entity_id=f"{country}-T1")
    texts = _renders(lang, contact)
    assert texts
    en_vals = _en_values()
    cal = {n for n in _calendar_en() if len(n) > 5}
    for text in texts:
        for v in en_vals:
            assert v not in text, f"English string leaked: {v!r}"
        for n in PUBLISHER_EN:
            assert n not in text
        for n in cal:
            # names identical in both languages (Black Friday) are allowed
            localized = {
                i18n.holiday_name(c, k, "x", lang, {"name_en": n, "name_local": n}, None)
                for c, k in [(country, "NONE")]
            }
            assert n not in text or n in localized


def test_holiday_names_localized_for_swedish_finland():
    row = {"name_local": "Jouluaatto", "name_en": "Christmas Eve"}
    assert i18n.holiday_name("FI", "XMAS_EVE", "2026-12-24", "sv", row, None) == "Julafton"
    assert not any("Christmas Eve" in t for t in _renders("sv", make_contact("sv")))
