"""Owner simulator (dev / demo tool)."""

from __future__ import annotations

import uuid
from email.message import EmailMessage

from app.core import compose
from app.core.i18n import fmt_date, fmt_hours
from app.core.models import Reply
from app.core.prompts import SimReplyInput
from app.server.ports import SimUnavailable
from app.server.services import sync
from app.server.services.common import Deps, effective_contact, tokenized_reply_to


def build_reply_email(deps: Deps, message, text: str, *, from_email: str | None = None) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = from_email or message.to_email or message.contact_email
    msg["To"] = tokenized_reply_to(deps.cfg, message.id)
    msg["Subject"] = "Re: " + message.subject
    msg["Message-ID"] = f"<{uuid.uuid4().hex}@sim.local>"
    msg.set_content(
        text + "\n\nOn Fri, 6 Nov 2026 at 10:00, Connect <connect@example.com> wrote:\n> " + message.subject
    )
    return msg


def simulate_owner(deps: Deps, message_id: str, use_llm: bool) -> Reply | None:
    message = deps.store.get_message(message_id)
    if message is None or message.kind != "dates":
        raise ValueError("The simulator works for dates messages only")
    contact = effective_contact(deps, message.entity_id)
    lang = message.language
    truth: dict[str, dict] = {}
    sim: list[dict] = []
    for it in message.items:
        try:
            r = deps.owner_sim.respond(message.entity_id, it.date, it.suggested_hours or it.shown_hours)
        except SimUnavailable:
            raise ValueError("Simulator answers only for dev/demo businesses") from None
        if r["decision"] == "NO_RESPONSE":
            continue
        sim.append(
            {
                "date": it.date,
                "decision": r["decision"],
                "final_hours": r.get("final_hours") or it.shown_hours,
                "shown_hours": it.shown_hours,
            }
        )
        truth[it.date] = {"decision": r["decision"], "final_hours": r.get("final_hours")}
    if not sim:
        return None
    if use_llm:
        parts = []
        for d in sim:
            ds = fmt_date(d["date"], "en")
            parts.append(
                f"approve {ds}"
                if d["decision"] == "ACCEPTED"
                else f"change {ds} to {fmt_hours(d['final_hours'], 'en')}"
                if d["decision"] == "EDITED"
                else f"keep {ds} as it is"
            )
        text = deps.llm.write_sim_reply(
            SimReplyInput(
                language=lang, first_name=contact.first_name if contact else "", intent_description="; ".join(parts)
            )
        )
    else:
        text = compose.compose_sim_reply(sim, lang)
    rid = f"sim-{uuid.uuid4().hex[:12]}"
    deps.store.set_state(f"simtruth-{rid}", {"dates": truth})
    return sync.process_raw(deps, rid, build_reply_email(deps, message, text), source="simulator")
