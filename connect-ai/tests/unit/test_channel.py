import pytest

from app.core.channel import (
    SMS_LIMIT,
    channel_for,
    day_list,
    digits,
    phone_allowed,
    sms_text,
    summarize_week,
    wa_param,
)
from tests.conftest import make_contact, make_item, make_message

LANGS = ("fi", "sv", "nb", "en")


def test_channel_for():
    allowed = {"email", "whatsapp", "sms"}
    for pref, expect in (
        ("EMAIL", "email"),
        ("WHATSAPP", "whatsapp"),
        ("SMS", "sms"),
        ("APP_PUSH", "email"),
        ("???", "email"),
    ):
        assert channel_for(make_contact(channel=pref), allowed) == expect
    assert channel_for(make_contact(channel="WHATSAPP"), {"email", "sms"}) == "email"


def test_day_list_and_week():
    items = [make_item("2026-12-24", "closed"), make_item("2026-12-31", "10:00-14:00")]
    assert day_list(items, "fi", "shown") == "to 24.12. 8–20; to 31.12. 8–20"
    assert day_list(items, "fi", "suggested") == "to 24.12. kiinni; to 31.12. 10–14"
    assert day_list(items, "sv", "suggested") == "tors 24/12 stängt; tors 31/12 10–14".replace("tors", "tor")
    assert day_list(items, "en", "shown") == "Thu 24 Dec 8–20; Thu 31 Dec 8–20"
    assert day_list(items, "nb", "suggested").startswith("tor 24.12. stengt")
    week = {d: "08:00-20:00" for d in ("monday", "tuesday", "wednesday", "thursday", "friday")} | {
        "saturday": "10:00-16:00",
        "sunday": "10:00-16:00",
    }
    assert summarize_week(week, "fi") == "ma–pe 8–20, la–su 10–16"
    assert summarize_week(week, "sv") == "mån–fre 8–20, lör–sön 10–16"
    assert summarize_week(week, "nb") == "man–fre 8–20, lør–søn 10–16"
    assert summarize_week(week, "en") == "Mon–Fri 8–20, Sat–Sun 10–16"
    assert summarize_week({d: "closed" for d in week}, "en") == "Mon–Sun closed"
    assert summarize_week(week | {"wednesday": "closed"}, "en").count(",") == 3


def test_wa_param():
    assert wa_param("a\nb\tc   d") == "a b c d"
    assert "\n" not in wa_param("x\n\n\ny")
    long = wa_param("x" * 400)
    assert len(long) == 300 and long.endswith("…")
    assert wa_param("  hi  ") == "hi"


def test_phones():
    assert digits("+358 40-111 1111") == "358401111111"
    assert phone_allowed("+358401111111", ["*"])
    assert phone_allowed("358401111111", ["+358401111111"])
    assert not phone_allowed("358402222222", ["+358401111111"])
    assert not phone_allowed("358401111111", [])


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("tpl_kind", ["suggestion", "question", "inform", "weekly"])
def test_sms_text_limits(lang, tpl_kind):
    items = [
        make_item(
            f"2026-12-{20 + i}",
            "10:00-14:00" if tpl_kind != "question" else None,
            priority=float(i * 10),
            basis=None if tpl_kind == "question" else "LAST_YEAR",
        )
        for i in range(6)
    ]
    kw = {"entity_name": "Kahvila Testi " + "X" * 40, "short": "Lyhyt viesti tässä. " * 4}
    if tpl_kind == "weekly":
        m = make_message(kind="weekly", lang=lang, **kw)
    else:
        m = make_message(items, mode="inform" if tpl_kind == "inform" else "ask", lang=lang, **kw)
    text, dropped = sms_text(m, make_contact(lang), lang)
    assert len(text) <= SMS_LIMIT
    if tpl_kind in ("suggestion", "question", "inform"):
        assert dropped == 6 - len(text.split(";")) or dropped >= 0


def test_sms_drops_lowest_priority_first():
    items = [make_item(f"2026-12-{20 + i}", "closed", priority=float(p)) for i, p in enumerate([5, 90, 50, 70, 60, 80])]
    m = make_message(items, entity_name="Kahvila " + "Y" * 120, short="z" * 150)
    text, dropped = sms_text(m, make_contact("en"), "en")
    assert dropped >= 1 and len(text) <= SMS_LIMIT
    assert "20 Dec" not in text  # priority 5 is dropped first
    assert "21 Dec" in text  # priority 90 survives


def test_sms_short_message_untouched():
    m = make_message(entity_name="Kahvila Testi", short="Hei.")
    text, dropped = sms_text(m, make_contact("fi"), "fi")
    assert dropped == 0 and text.startswith("Kahvila Testi: Hei. Google näyttää") and "STOP" in text
