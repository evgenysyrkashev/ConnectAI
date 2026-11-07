import csv
import json

import pytest

from app import kit
from app.core import i18n
from app.core.i18n import TEXT, fmt_date, fmt_hours, fmt_number, holiday_name, publisher_name
from app.core.i18n_text import WEEKDAY, WEEKDAY_SHORT

LANGS = ("fi", "sv", "nb", "en")


def test_fmt_date():
    assert fmt_date("2026-12-24", "fi") == "24.12."
    assert fmt_date("2026-12-24", "nb") == "24.12."
    assert fmt_date("2026-12-24", "sv") == "24/12"
    assert fmt_date("2026-12-24", "en") == "24 Dec"


def test_fmt_hours():
    assert fmt_hours("closed", "fi") == "kiinni"
    assert fmt_hours("closed", "sv") == "stängt"
    assert fmt_hours("10:00-14:00", "en") == "10–14"
    assert fmt_hours("10:30-14:00,17:00-22:00", "fi") == "10.30–14, 17–22"
    assert fmt_hours("00:00-23:59", "nb") == "åpent hele døgnet"
    assert fmt_hours("00:00-23:59", "en") == "open 24 hours"


def test_fmt_number():
    assert fmt_number(12345, "en") == "12,345"
    assert fmt_number(12345, "fi") == "12 345"


def test_eta():
    assert i18n.eta_text(120, "en") == "in about 2 min"
    assert i18n.eta_text(7200, "fi") == "noin 2 h kuluttua"
    assert i18n.eta_text(172800, "sv") == "om cirka 2 dygn"


@pytest.mark.parametrize("lang", LANGS)
def test_every_key_in_every_language(lang):
    assert set(TEXT[lang]) == set(TEXT["en"])
    assert all(v for v in TEXT[lang].values())
    assert len(WEEKDAY[lang]) == 7 and len(WEEKDAY_SHORT[lang]) == 7


def _calendar():
    with open(kit.data_path("data", "calendar_special_days.csv"), encoding="utf-8") as f:
        return list(csv.DictReader(f))


CRM_COMBOS = {"FI": ("fi", "sv", "en"), "SE": ("sv", "en"), "NO": ("nb", "en")}


def test_holiday_name_coverage(caplog):
    seen = {}
    for r in _calendar():
        seen[(r["country"], r["day_key"])] = r
    assert seen
    with caplog.at_level("WARNING", logger="connect.i18n"):
        for (country, key), row in seen.items():
            for lang in CRM_COMBOS[country]:
                name = holiday_name(country, key, row["date"], lang, row, None)
                assert name, (country, key, lang)
    assert "holiday name missing" not in caplog.text


def test_holiday_name_rules():
    row = {"name_local": "Jouluaatto", "name_en": "Christmas Eve"}
    assert holiday_name("FI", "XMAS_EVE", "2026-12-24", "fi", row, None) == "Jouluaatto"
    assert holiday_name("FI", "XMAS_EVE", "2026-12-24", "en", row, None) == "Christmas Eve"
    assert holiday_name("FI", "XMAS_EVE", "2026-12-24", "sv", row, None) == "Julafton"
    ev = {"name": {"fi": "Konsertti", "en": "Concert"}}
    assert holiday_name("FI", "EVENT", "2026-12-24", "fi", None, ev) == "Konsertti"
    assert holiday_name("FI", "EVENT", "2026-12-24", "sv", None, ev) == "Concert"


def test_publisher_names_clean():
    with open(kit.data_path("data", "listings.json"), encoding="utf-8") as f:
        ids = {x["publisherId"] for x in json.load(f)["listings"]}
    for pid in ids:
        for lang in LANGS:
            n = publisher_name(pid, lang)
            assert n and "via" not in n and "Search & Maps" not in n and "(" not in n
    assert publisher_name("APPLE", "sv") == "Apple Kartor"
    assert publisher_name("GOOGLEMYBUSINESS", "sv") == "Google Sök och Maps"
    assert publisher_name("UNKNOWN_X", "fi") == "UNKNOWN_X"
