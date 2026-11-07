"""Message template definitions."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel

from app.core.models import Kind, TemplateId


class NoParams(BaseModel):
    pass


class DateRangeParams(BaseModel):
    date_from: date = date(2026, 11, 7)
    date_to: date = date(2027, 1, 6)


class TemplateDef(BaseModel):
    id: TemplateId
    label: str
    description: str
    kind: Kind
    tone: str
    goal: str  # English instructions to the LLM
    params_model: type[BaseModel]
    selectable: bool = True


TEMPLATES: dict[str, TemplateDef] = {
    "holidays": TemplateDef(
        id="holidays",
        label="Holiday hours",
        description="Suggested opening hours for upcoming holidays.",
        kind="dates",
        tone="warm, helpful, brief; festive but professional",
        goal=(
            "Tell the owner we prepared suggested opening hours for the upcoming holidays so customers find correct "
            "hours on Google, and ask them to approve or correct them."
        ),
        params_model=DateRangeParams,
    ),
    "event": TemplateDef(
        id="event",
        label="Event nearby",
        description="A large event near the business may change its hours.",
        kind="dates",
        tone="friendly, helpful, slightly urgent because the event is soon",
        goal="Tell the owner a large event takes place near their business and ask whether their opening hours change on that day.",
        params_model=DateRangeParams,
    ),
    "stale_hours": TemplateDef(
        id="stale_hours",
        label="Regular-hours check-up",
        description="Ask the owner to check the regular weekly hours (only with evidence they are stale).",
        kind="weekly",
        tone="polite, low-pressure",
        goal="Ask the owner to check that the regular weekly opening hours shown on Google are still correct.",
        params_model=NoParams,
    ),
    "permission": TemplateDef(
        id="permission",
        label="Permission request",
        description="Ask whether we may update holiday hours automatically. Created only by the escalation chain.",
        kind="permission",
        tone="warm, appreciative, benefit-focused; never pushy, salesy or guilt-tripping",
        goal=(
            "Explain that we could keep the business's holiday hours correct automatically and ask for permission, "
            "emphasising that the owner stays in control"
        ),
        params_model=NoParams,
        selectable=False,
    ),
}


def selectable_templates() -> list[TemplateDef]:
    return [t for t in TEMPLATES.values() if t.selectable]
