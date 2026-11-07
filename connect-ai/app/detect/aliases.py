"""Holiday-name stems per day_key (fi, sv, nb, en), lowercase. Used to find reviews that mention a specific holiday."""

from __future__ import annotations

import csv
from functools import lru_cache

from app import kit

# Hand-written forms on top of the stems cut from calendar_special_days.csv.
EXTRA: dict[str, list[str]] = {
    "XMAS_EVE": ["jouluaat", "julafton", "julaft", "christmas eve"],
    "XMAS_DAY": ["joulupäiv", "juldag", "første juledag", "christmas day"],
    "BOXING_DAY": ["tapaninpäiv", "annandag jul", "andre juledag", "boxing day"],
    "NYE": ["uudenvuodenaat", "nyårsafton", "nyttårsaft", "new year's eve"],
    "NEW_YEARS_DAY": ["uudenvuodenpäiv", "nyårsdag", "nyttårsdag", "new year's day"],
    "MIDSUMMER_EVE": ["juhannusaat", "midsommarafton", "sankthans", "midsummer eve"],
    "MIDSUMMER_DAY": ["juhannuspäiv", "midsommardag", "midsummer day"],
    "EPIPHANY": ["loppiai", "trettondag", "helligtrekonger", "epiphany"],
    "INDEPENDENCE_DAY": ["itsenäisyyspäiv", "independence day"],
    "LUCIA": ["lucia", "lussekatt"],
    "MAY_DAY": ["vappu", "första maj", "1. mai", "may day"],
    "MAY_EVE": ["vappuaat", "valborg", "may eve"],
    "NATIONAL_DAY": ["nasjonaldag", "17. mai", "nationaldag", "sixth of june", "6 juni"],
    "GOOD_FRIDAY": ["pitkäperjantai", "långfredag", "langfredag", "good friday"],
    "EASTER_SUNDAY": ["pääsiäispäiv", "påskdag", "påskedag", "easter sunday"],
    "EASTER_MONDAY": ["toinen pääsiäispäiv", "annandag påsk", "andre påskedag", "easter monday"],
    "EASTER_SATURDAY": ["pääsiäislauantai", "påskafton", "påskeaften", "easter saturday"],
    "MAUNDY_THURSDAY": ["kiirastorstai", "skärtorsdag", "skjærtorsdag", "maundy thursday"],
    "ASCENSION": ["helatorstai", "kristi himmelsfärd", "kristi himmelfart", "ascension"],
    "PENTECOST": ["helluntai", "pingst", "pinse", "pentecost"],
    "PENTECOST_EVE": ["helluntaiaat", "pingstafton", "pinseaften", "pentecost eve"],
    "WHIT_MONDAY": ["annandag pingst", "andre pinsedag", "whit monday"],
    "ALL_SAINTS": ["pyhäinpäiv", "alla helgons", "allehelgen", "all saints"],
    "BLACK_FRIDAY": ["black friday", "mustaperjantai"],
    "FATHERS_DAY": ["isänpäiv", "fars dag", "farsdag", "father's day"],
    "MOTHERS_DAY": ["äitienpäiv", "mors dag", "morsdag", "mother's day"],
    "DEC23": ["23. joulukuu", "23 december", "23. desember"],
    "EPIPHANY_EVE": ["loppiaisaat", "trettondagsafton", "helligtrekongersaften"],
}


@lru_cache(maxsize=1)
def aliases() -> dict[str, list[str]]:
    out: dict[str, set[str]] = {}
    with open(kit.data_path("data", "calendar_special_days.csv"), encoding="utf-8") as f:
        for r in csv.DictReader(f):
            for name in (r["name_local"], r["name_en"]):
                n = name.strip().lower()
                if n:
                    out.setdefault(r["day_key"], set()).add(n[: max(5, len(n) - 3)])
    for k, v in EXTRA.items():
        out.setdefault(k, set()).update(v)
    return {k: sorted(v) for k, v in out.items()}


CLOSED_WORDS = ("kiinni", "suljettu", "closed", "stängt", "stengt")


def mentions_closed_on(text: str, day_key: str) -> bool:
    t = text.lower()
    return any(a in t for a in aliases().get(day_key, ())) and any(w in t for w in CLOSED_WORDS)
