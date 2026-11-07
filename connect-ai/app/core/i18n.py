"""Localisation helpers. Pure: strings come from i18n_text, formats are computed here."""

from __future__ import annotations

import logging
from datetime import date as _date

from app.core.i18n_text import TEXT, WEEKDAY, WEEKDAY_SHORT

__all__ = [
    "COUNTRY_LANG",
    "HOLIDAY_NAMES",
    "SUPPORTED_LANGS",
    "TEXT",
    "WEEKDAY",
    "WEEKDAY_SHORT",
    "eta_text",
    "fmt_date",
    "fmt_hours",
    "fmt_number",
    "holiday_name",
    "publisher_name",
    "t",
    "weekday_name",
    "weekday_short",
]

log = logging.getLogger("connect.i18n")

SUPPORTED_LANGS = ("fi", "sv", "nb", "en")
COUNTRY_LANG = {"FI": "fi", "SE": "sv", "NO": "nb"}


def t(lang: str, key: str, **kw: object) -> str:
    """Look up TEXT[lang][key] and format it."""
    s = TEXT[lang][key]
    return s.format(**kw) if kw else s


def _d(d: str | _date) -> _date:
    return d if isinstance(d, _date) else _date.fromisoformat(d)


def weekday_name(d: str | _date, lang: str) -> str:
    return WEEKDAY[lang][_d(d).weekday()]


def weekday_short(d: str | _date, lang: str) -> str:
    return WEEKDAY_SHORT[lang][_d(d).weekday()]


_MONTHS_EN = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def fmt_date(d: str | _date, lang: str) -> str:
    dd = _d(d)
    if lang in ("fi", "nb"):
        return f"{dd.day}.{dd.month}."
    if lang == "sv":
        return f"{dd.day}/{dd.month}"
    return f"{dd.day} {_MONTHS_EN[dd.month - 1]}"


def _clock(x: str) -> str:
    hh, mm = x.split(":")
    return str(int(hh)) + ("" if mm == "00" else "." + mm)


def fmt_hours(h: str, lang: str) -> str:
    """Kit hours string -> '10–14', '10.30–14, 17–22', localized 'closed' / 'open 24 hours'."""
    h = (h or "").strip().lower()
    if h in ("", "closed"):
        return TEXT[lang]["closed"]
    if h == "00:00-23:59":
        return TEXT[lang]["open_24h"]
    return ", ".join("–".join(_clock(x) for x in iv.split("-")) for iv in h.split(","))


def fmt_number(n: int, lang: str) -> str:
    if lang == "en":
        return f"{n:,}"
    return f"{n:,}".replace(",", " ")


def eta_text(seconds: int, lang: str) -> str:
    """Same rule as quickstart's eta(): <1 h minutes, <1 day hours, else days."""
    if seconds < 3600:
        return TEXT[lang]["eta_minutes"].format(n=max(1, seconds // 60))
    if seconds < 86400:
        return TEXT[lang]["eta_hours"].format(n=seconds // 3600)
    return TEXT[lang]["eta_days"].format(n=seconds // 86400)


# DECISION: Finland-Swedish names, to be checked by a native speaker.
_FI_SV = {
    "ALL_SAINTS": "Alla helgons dag",
    "FATHERS_DAY": "Farsdag",
    "BLACK_FRIDAY": "Black Friday",
    "INDEPENDENCE_DAY": "Självständighetsdagen",
    "DEC23": "Dagen före julafton",
    "XMAS_EVE": "Julafton",
    "XMAS_DAY": "Juldagen",
    "BOXING_DAY": "Annandag jul",
    "INTERDAY": "Mellandag",
    "NYE": "Nyårsafton",
    "NEW_YEARS_DAY": "Nyårsdagen",
    "MIDSUMMER_EVE": "Midsommarafton",
    "MOTHERS_DAY": "Mors dag",
    "EPIPHANY_EVE": "Trettondagsafton",
    "EPIPHANY": "Trettondagen",
    "MAUNDY_THURSDAY": "Skärtorsdagen",
    "GOOD_FRIDAY": "Långfredagen",
    "EASTER_SATURDAY": "Påskafton",
    "EASTER_SUNDAY": "Påskdagen",
    "EASTER_MONDAY": "Annandag påsk",
    "MAY_EVE": "Valborgsmässoafton",
    "MAY_DAY": "Första maj",
    "ASCENSION": "Kristi himmelsfärdsdag",
    "PENTECOST_EVE": "Pingstafton",
    "PENTECOST": "Pingstdagen",
    "MIDSUMMER_DAY": "Midsommardagen",
    "LUCIA": "Luciadagen",
}
HOLIDAY_NAMES: dict[tuple[str, str], dict[str, str]] = {("FI", k): {"sv": v} for k, v in _FI_SV.items()}


def holiday_name(
    country: str,
    day_key: str,
    date: str,
    lang: str,
    calendar_row: dict | None = None,
    event: dict | None = None,
) -> str:
    """Name of a special day in the owner's language."""
    if day_key == "EVENT" and event:
        names = event.get("name") or {}
        if isinstance(names, dict):
            return names.get(lang) or names.get("en") or next(iter(names.values()), "")
        return str(names)
    row = calendar_row or {}
    if lang == COUNTRY_LANG.get(country) and row.get("name_local"):
        return row["name_local"]
    if lang == "en" and row.get("name_en"):
        return row["name_en"]
    name = HOLIDAY_NAMES.get((country, day_key), {}).get(lang)
    if name:
        return name
    log.warning("holiday name missing: %s/%s/%s", country, day_key, lang)
    return row.get("name_en") or row.get("name_local") or day_key


# publisherId -> {lang: name}; brands stay, descriptive parts are translated.
_BRANDS = {
    "BING": "Bing",
    "FACEBOOK": "Facebook",
    "TRIPADVISOR": "Tripadvisor",
    "FOURSQUARE": "Foursquare",
    "FONECTA_CALLER": "Fonecta Caller",
    "HITTA": "Hitta.se",
    "ENIRO": "Eniro",
    "GULESIDER": "Gule Sider",
    "1881": "1881.no",
    "WAZE": "Waze",
    "FONECTA_FINDER": "Finder.fi / Fonecta.fi",
}
_PUBLISHERS: dict[str, dict[str, str]] = {
    "GOOGLEMYBUSINESS": {
        "en": "Google Search and Maps",
        "fi": "Google-haku ja Google Maps",
        "sv": "Google Sök och Maps",
        "nb": "Google Søk og Maps",
    },
    "APPLE": {"en": "Apple Maps", "fi": "Apple Maps", "sv": "Apple Kartor", "nb": "Apple Kart"},
    "CHATGPT_SEARCH": {
        "en": "AI assistants",
        "fi": "Tekoälyavustajat",
        "sv": "AI-assistenter",
        "nb": "KI-assistenter",
    },
}


def publisher_name(publisher_id: str, lang: str) -> str:
    if publisher_id in _PUBLISHERS:
        return _PUBLISHERS[publisher_id][lang]
    return _BRANDS.get(publisher_id, publisher_id)
