"""Deterministic fake LLM used in tests and default local dev."""

from __future__ import annotations

import re

from app.core.models import WEEKDAYS
from app.core.prompts import FAKE_INTRO, FAKE_SHORT, IntroInput, ParseInput, SimReplyInput
from app.core.reply_text import flag_suspicious

_RANGE = re.compile(r"(\d{1,2})(?:[:.](\d{2}))?\s*[-–]\s*(\d{1,2})(?:[:.](\d{2}))?")
_CLOSED = re.compile(r"closed|kiinni|suljettu|stängt|stengt")
_DECLINE = re.compile(r"no thanks|ei kiitos|nej tack|nei takk|keep it")
_APPROVE = re.compile(r"\bok\b|okay|yes|kyllä|käy|okej|\bja\b|sounds good|godkänn|godkjenn")
_FOR_GOOD = re.compile(r"closed for good|lopettanut|pysyvästi|lopettaneet")


def _hours_from(m: re.Match) -> str:
    oh, om, ch, cm = int(m.group(1)), m.group(2) or "00", int(m.group(3)), m.group(4) or "00"
    if ch <= 12 and ch <= oh:
        ch += 12
    return f"{oh:02d}:{om}-{ch:02d}:{cm}"


def _dates_in(inp: ParseInput) -> list[str]:
    return re.findall(r"^(\d{4}-\d{2}-\d{2})", inp.items_text, flags=re.MULTILINE)


class FakeLlm:
    def __init__(self) -> None:
        self.intro_calls: list[IntroInput] = []
        self.parse_calls: list[ParseInput] = []
        self.translate_calls: list[tuple[str, str]] = []

    def write_intro(self, inp: IntroInput) -> object:
        self.intro_calls.append(inp)
        if "[bad-llm]" in inp.business_name:
            return {"subject": "x", "intro": "see http://x"}
        return {
            "subject": f"{inp.business_name}: {inp.template_id}",
            "intro": FAKE_INTRO[inp.language],
            "short": FAKE_SHORT[inp.language],
        }

    def parse_reply(self, inp: ParseInput) -> object:
        self.parse_calls.append(inp)
        t = inp.cleaned_text.lower()
        if "[llm-error]" in t:
            raise RuntimeError("fake llm error")
        out: dict = {"intent": "unclear", "dates": None, "weekly": None, "permanently_closed": False}
        m = _RANGE.search(t)
        if inp.kind == "permission":
            out.update(intent="unclear", confidence=0.3)
        elif m:
            hours = _hours_from(m)
            out["intent"], out["confidence"] = "edit", 0.9
            if inp.kind == "dates":
                out["dates"] = [{"date": d, "action": "set", "hours": hours} for d in _dates_in(inp)]
            else:
                out["weekly"] = {d: hours for d in WEEKDAYS[:5]}
        elif _CLOSED.search(t):
            out["intent"], out["confidence"] = "edit", 0.9
            if inp.kind == "dates":
                out["dates"] = [{"date": d, "action": "set", "hours": "closed"} for d in _dates_in(inp)]
            else:
                out["weekly"] = {d: "closed" for d in WEEKDAYS[:5]}
        elif _DECLINE.search(t):
            out.update(intent="decline", confidence=0.9)
        elif _APPROVE.search(t):
            out.update(intent="approve", confidence=0.95)
        elif _FOR_GOOD.search(t):
            out.update(intent="unclear", permanently_closed=True, confidence=0.9)
        else:
            out.update(intent="unclear", confidence=0.3)
        out["abusive"] = flag_suspicious(t)
        out["summary"] = "fake: " + out["intent"]
        return out

    def write_sim_reply(self, inp: SimReplyInput) -> str:
        return inp.intent_description

    def translate(self, text: str, target: str) -> str:
        self.translate_calls.append((text, target))
        return f"[{target}] {text}"
