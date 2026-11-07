"""WhatsApp template definitions: the single source for sending and creating templates. Pure."""

from __future__ import annotations

from app.core.channel import WA_BODY_LIMIT, day_list, drop_lowest_priority, suggestion_list, summarize_week, wa_param
from app.core.i18n import TEXT
from app.core.models import Contact, OutboundMessage

LANGS = ("fi", "sv", "nb", "en")

# name -> payload codes in button order
CODES = {
    "connect_hours_suggestion": ["A", "E", "D"],
    "connect_hours_question": ["R", "E"],
    "connect_hours_check": ["C", "X"],
    "connect_hours_updated": ["W"],
}

BODY: dict[str, dict[str, str]] = {
    "connect_hours_suggestion": {
        "en": "Hi {{1}}! {{2}}\n\nGoogle now shows for {{3}}: {{4}}\nWe suggest: {{5}}\n\nTap a button or reply with your own hours.",
        "fi": "Hei {{1}}! {{2}}\n\nGoogle näyttää nyt kohteelle {{3}}: {{4}}\nEhdotamme: {{5}}\n\nPainakaa painiketta tai vastatkaa omilla aukioloajoillanne.",
        "sv": "Hej {{1}}! {{2}}\n\nGoogle visar nu för {{3}}: {{4}}\nVi föreslår: {{5}}\n\nTryck på en knapp eller svara med era egna tider.",
        "nb": "Hei {{1}}! {{2}}\n\nGoogle viser nå for {{3}}: {{4}}\nVi foreslår: {{5}}\n\nTrykk på en knapp eller svar med deres egne tider.",
    },
    "connect_hours_question": {
        "en": "Hi {{1}}! {{2}}\n\nGoogle now shows for {{3}}: {{4}}\n\nWhat are your hours on these days?",
        "fi": "Hei {{1}}! {{2}}\n\nGoogle näyttää nyt kohteelle {{3}}: {{4}}\n\nMitkä ovat aukioloaikanne näinä päivinä?",
        "sv": "Hej {{1}}! {{2}}\n\nGoogle visar nu för {{3}}: {{4}}\n\nVilka är era öppettider de här dagarna?",
        "nb": "Hei {{1}}! {{2}}\n\nGoogle viser nå for {{3}}: {{4}}\n\nHva er åpningstidene deres disse dagene?",
    },
    "connect_hours_check": {
        "en": "Hi {{1}}! {{2}}\n\nGoogle shows these regular hours for {{3}}: {{4}}\n\nAre they still correct?",
        "fi": "Hei {{1}}! {{2}}\n\nGoogle näyttää kohteelle {{3}} nämä säännölliset aukioloajat: {{4}}\n\nOvatko ne edelleen oikein?",
        "sv": "Hej {{1}}! {{2}}\n\nGoogle visar dessa ordinarie öppettider för {{3}}: {{4}}\n\nStämmer de fortfarande?",
        "nb": "Hei {{1}}! {{2}}\n\nGoogle viser disse vanlige åpningstidene for {{3}}: {{4}}\n\nStemmer de fortsatt?",
    },
    "connect_hours_updated": {
        "en": "Hi {{1}}! We updated the opening hours of {{2}} on Google: {{3}}. {{4}} Thank you!",
        "fi": "Hei {{1}}! Olemme päivittäneet kohteen {{2}} aukioloajat Googleen: {{3}}. {{4}} Kiitos!",
        "sv": "Hej {{1}}! Vi har uppdaterat öppettiderna för {{2}} på Google: {{3}}. {{4}} Tack!",
        "nb": "Hei {{1}}! Vi har oppdatert åpningstidene for {{2}} på Google: {{3}}. {{4}} Takk!",
    },
}

BUTTONS: dict[str, dict[str, list[str]]] = {
    "connect_hours_suggestion": {
        "fi": ["Hyväksy", "Muokkaa", "Ei kiitos"],
        "sv": ["Godkänn", "Ändra", "Nej tack"],
        "nb": ["Godkjenn", "Endre", "Nei takk"],
        "en": ["Approve", "Edit", "No thanks"],
    },
    "connect_hours_question": {
        "fi": ["Kuten yleensä", "Eri ajat"],
        "sv": ["Som vanligt", "Andra tider"],
        "nb": ["Som vanlig", "Andre tider"],
        "en": ["As usual", "Different hours"],
    },
    "connect_hours_check": {
        "fi": ["Oikein", "Muuttunut"],
        "sv": ["Stämmer", "Ändrat"],
        "nb": ["Stemmer", "Endret"],
        "en": ["Correct", "Changed"],
    },
    "connect_hours_updated": {
        "fi": ["Jotain on väärin"],
        "sv": ["Något är fel"],
        "nb": ["Noe er feil"],
        "en": ["Something is wrong"],
    },
}


def param_count(name: str) -> int:
    return max(int(n) for n in range(1, 10) if f"{{{{{n}}}}}" in BODY[name]["en"])


def footer(lang: str) -> str:
    return TEXT[lang]["fallback_footer"]


def template_for(message: OutboundMessage) -> str:
    if message.mode == "inform":
        return "connect_hours_updated"
    if message.kind == "weekly":
        return "connect_hours_check"
    if any(i.suggested_hours is not None for i in message.items):
        return "connect_hours_suggestion"
    return "connect_hours_question"


def render_body(name: str, lang: str, params: list[str]) -> str:
    body = BODY[name][lang]
    for n, p in enumerate(params, start=1):
        body = body.replace(f"{{{{{n}}}}}", p)
    return body


def updated_params(first_name: str, business: str, applied: str, lang: str) -> list[str]:
    """Params for connect_hours_updated, also used when the 24 h window has closed."""
    return [wa_param(p) for p in (first_name, business, applied, TEXT[lang]["wa_visibility_fallback"])]


def wa_content_fitted(message: OutboundMessage, contact: Contact, lang: str) -> tuple[str, list[str], list[str], int]:
    """(template name, params, button codes, dropped_items). Drops lowest-priority items until the body fits."""
    name = template_for(message)
    short = message.short or TEXT[lang][f"fallback_short_{message.template_id}"]
    items = sorted(message.items, key=lambda i: i.date)
    dropped = 0

    def build(its: list) -> list[str]:
        if name == "connect_hours_updated":
            return updated_params(contact.first_name, message.entity_name, day_list(its, lang, "suggested"), lang)
        if name == "connect_hours_check":
            raw = [contact.first_name, short, message.entity_name, summarize_week(message.weekly_shown or {}, lang)]
        elif name == "connect_hours_question":
            raw = [contact.first_name, short, message.entity_name, day_list(its, lang, "shown")]
        else:
            raw = [
                contact.first_name,
                short,
                message.entity_name,
                day_list(its, lang, "shown"),
                suggestion_list(its, lang),
            ]
        return [wa_param(p) for p in raw]

    params = build(items)
    while len(render_body(name, lang, params)) > WA_BODY_LIMIT and len(items) > 1 and message.kind == "dates":
        items = drop_lowest_priority(items)
        dropped += 1
        params = build(items)
    return name, params, list(CODES[name]), dropped


def wa_content(message: OutboundMessage, contact: Contact, lang: str) -> tuple[str, list[str], list[str]]:
    name, params, codes, _ = wa_content_fitted(message, contact, lang)
    return name, params, codes


SAMPLE_PARAMS = ["Maria", "Check the details below.", "Kahvila Testi", "Thu 24 Dec 8–20", "Thu 24 Dec closed"]


def graph_definition(name: str, lang: str) -> dict:
    """Body for POST /{waba}/message_templates. UTILITY category, quick-reply buttons."""
    n = param_count(name)
    return {
        "name": name,
        "language": lang,
        "category": "UTILITY",
        "components": [
            {"type": "BODY", "text": BODY[name][lang], "example": {"body_text": [SAMPLE_PARAMS[:n]]}},
            {"type": "FOOTER", "text": footer(lang)},
            {"type": "BUTTONS", "buttons": [{"type": "QUICK_REPLY", "text": t} for t in BUTTONS[name][lang]]},
        ],
    }


def all_definitions() -> list[dict]:
    return [graph_definition(name, lang) for name in BODY for lang in LANGS]
