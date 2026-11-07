"""Validation of LLM-written subject / intro / short. Pure."""

from __future__ import annotations

import re

from pydantic import BaseModel

STOPWORDS: dict[str, list[str]] = {
    "fi": [
        "ja",
        "on",
        "että",
        "ei",
        "se",
        "olla",
        "kanssa",
        "teidän",
        "myös",
        "voi",
        "tai",
        "kun",
        "mutta",
        "tämä",
        "niin",
    ],
    "sv": ["och", "är", "att", "det", "som", "för", "med", "inte", "har", "ni", "er", "kan", "också", "på", "en"],
    "nb": ["og", "er", "at", "det", "som", "for", "med", "ikke", "har", "dere", "deres", "kan", "også", "på", "en"],
    "en": ["and", "is", "that", "the", "for", "with", "not", "have", "you", "your", "can", "also", "on", "a", "to"],
}
# sv and nb share many words: compare them only on the words that differ.
_SV_ONLY = {"och", "inte", "ni", "er", "också"}
_NB_ONLY = {"og", "ikke", "dere", "deres", "også"}


class IntroOut(BaseModel):
    subject: str
    intro: str
    short: str = ""


def _count(words: list[str], lang: str) -> int:
    sw = set(STOPWORDS[lang])
    return sum(1 for w in words if w in sw)


def check_language(text: str, lang: str) -> bool:
    words = re.findall(r"[\wåäöæøÅÄÖÆØ]+", text.lower())
    own = _count(words, lang)
    if own < 2:
        return False
    for other in STOPWORDS:
        if other == lang:
            continue
        if {lang, other} == {"sv", "nb"}:
            mine = sum(1 for w in words if w in (_SV_ONLY if lang == "sv" else _NB_ONLY))
            theirs = sum(1 for w in words if w in (_NB_ONLY if lang == "sv" else _SV_ONLY))
            if mine <= theirs:
                return False
        elif _count(words, other) >= own:
            return False
    return True


_LINK = re.compile(r"https?:|www\.|@")
_TIME_RES = (
    re.compile(r"\b\d{1,2}[:.]\d{2}\b"),
    re.compile(r"\b\d{1,2}\s?(am|pm)\b", re.IGNORECASE),
    re.compile(r"\b\d{1,2}\.\d{1,2}\.\B|\b\d{1,2}\.\d{1,2}\.\b"),
)
_GREETING = re.compile(r"^(hi|hello|dear|hei|moi|hej|hallo)\b", re.IGNORECASE)


def check_intro(o: IntroOut, lang: str, template_id: str | None = None) -> list[str]:
    problems: list[str] = []
    short = o.short
    if len(short) < 20 or len(short) > 160 or "\n" in short or "\t" in short:
        problems.append("short must be 20-160 characters on one line")
    if not check_language(o.intro + " " + short, lang):
        problems.append("Wrong language")
    letters = [c for c in o.subject if c.isalpha()]
    if len(o.subject) < 5 or len(o.subject) > 70 or (len(letters) > 3 and o.subject.isupper()):
        problems.append("subject must be 5-70 characters and not all caps")
    if len(o.intro) < 40 or len(o.intro) > 500:
        problems.append("intro must be 40-500 characters")
    for name, text in (("subject", o.subject), ("intro", o.intro), ("short", short)):
        if _LINK.search(text):
            problems.append(f"{name} contains a link or address")
        if any(r.search(text) for r in _TIME_RES):
            problems.append(f"{name} contains a time or date")
        if template_id == "permission" and re.search(r"\d", text):
            problems.append(f"{name} contains digits")
    if _GREETING.match(o.intro.strip()) or (short and _GREETING.match(short.strip())):
        problems.append("text starts with a greeting")
    return problems
