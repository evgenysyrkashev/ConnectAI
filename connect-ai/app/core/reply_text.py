"""Body extraction and quote stripping for inbound replies. Pure."""

from __future__ import annotations

import re
from email.message import EmailMessage

from bs4 import BeautifulSoup

_ON_WROTE = re.compile(r"^On .+wrote:\s*$")
_WROTE_END = re.compile(r"wrote:\s*$")
# DECISION: also accept "skrev X <x@y>:" (Swedish clients put the sender between the verb and the colon)
_LOCAL_WROTE = re.compile(r"^.{0,200}\b(kirjoitti|skrev)\b.{0,200}:\s*$")
_ORIGINAL = re.compile(
    r"^-{2,}\s*(Original Message|Alkuperäinen viesti|Ursprungligt meddelande|Opprinnelig melding)\s*-{2,}",
    re.IGNORECASE,
)
_UNDERSCORES = re.compile(r"^_{10,}\s*$")
_FROM = re.compile(r"^(From|Lähettäjä|Från|Fra):\s")
_SIG = re.compile(r"^-- ?$")

STOP_WORDS = {"STOP", "UNSUBSCRIBE", "LOPETA", "SLUTA", "STOPP"}
_MANUAL = {"MANUAL", "MANUAALINEN", "MANUELL", "MANUELT"}
_AUTO = {"AUTO", "AUTOMAATTINEN", "AUTOMATISK"}
# Quick words (no LLM): SMS and permission answers
_SMS_YES = {"ok", "kyllä", "joo", "ja", "yes", "okej"}
_SMS_NO = {"no", "ei", "nej", "nei"}
_PERM_YES = {"yes", "kyllä", "joo", "ok", "ja", "okej", "sure"}
_PERM_NO = {"no", "ei", "nej", "nei", "no thanks", "ei kiitos", "nej tack", "nei takk"}


def extract_text(msg: EmailMessage) -> str:
    body = msg.get_body(preferencelist=("plain", "html"))
    if body is None:
        return ""
    content = body.get_content()
    if body.get_content_type() == "text/html":
        return BeautifulSoup(content, "html.parser").get_text("\n")
    return content


def strip_quoted(text: str) -> str:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    cut = len(lines)
    for i, line in enumerate(lines):
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        prev_blank = i > 0 and not lines[i - 1].strip()
        if (
            _ON_WROTE.match(line)
            or (line.startswith("On ") and _WROTE_END.search(nxt))
            or _LOCAL_WROTE.match(line)
            or _ORIGINAL.match(line)
            or _UNDERSCORES.match(line)
            or (prev_blank and _FROM.match(line))
            or _SIG.match(line)
        ):
            cut = i
            break
    kept = [ln for ln in lines[:cut] if not ln.lstrip().startswith(">")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept).strip())


# DECISION: conservative keyword screen (no LLM, no I/O). A hit never blocks anything; it only forces human review.
_SUSPICIOUS = re.compile(
    r"ignore (all |any )?(the )?(previous|prior|above) (instructions|prompts?)"
    r"|disregard (all |any )?(the )?(previous|prior|above)"
    r"|system prompt|developer message|you are now|jailbreak"
    r"|\b(kill|murder) (you|yourself)\b|\bi will (find|hurt|kill) you\b"
    r"|\bfuck\b|\bfucking\b|\bshit\b|\basshole\b|\bbastard\b"
    r"|\bvittu\b|\bperkele\b|\bsaatana\b|\bjävla\b|\bhelvete\b|\bfitte\b|\bhore\b",
    re.IGNORECASE,
)


def flag_suspicious(text: str) -> bool:
    """True if the reply looks abusive, threatening or like a prompt-injection attempt."""
    return bool(_SUSPICIOUS.search(text))


def truncate(text: str, n: int = 4000) -> str:
    return text if len(text) <= n else text[:n]


def first_line(text: str) -> str:
    for line in text.strip().splitlines():
        if line.strip():
            return line.strip()
    return ""


def _first_word_upper(text: str) -> str:
    return first_line(text).upper().rstrip("!.")


def is_stop(text: str) -> bool:
    return _first_word_upper(text) in STOP_WORDS


def is_manual(text: str) -> bool:
    return _first_word_upper(text) in _MANUAL


def is_auto(text: str) -> bool:
    return _first_word_upper(text) in _AUTO


def quick_intent(text: str, *, permission: bool = False) -> str | None:
    """'approve' / 'decline' for one-word answers (no LLM), else None."""
    w = first_line(text).lower().rstrip("!.")
    if permission:
        return "approve" if w in _PERM_YES else "decline" if w in _PERM_NO else None
    t = text.strip().lower().rstrip("!.")
    return "approve" if t in _SMS_YES else "decline" if t in _SMS_NO else None
