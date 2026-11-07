"""Dev / demo routes: owner simulator, fake mail and WhatsApp helpers, SMS phone, demo clock."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import Response

from app.core.channel import digits
from app.server.security import csrf_guard, operator_identity
from app.server.services import escalation, scheduler, simulate, sms_inbound, sync, whatsapp_inbound
from app.server.services.common import Deps, token_for, tokenized_reply_to


def _refresh() -> Response:
    return Response(status_code=204, headers={"HX-Refresh": "true"})


def make_router(deps: Deps) -> APIRouter:
    cfg = deps.cfg
    r = APIRouter(dependencies=[Depends(operator_identity)])
    post = Depends(csrf_guard)

    def msg_or_404(mid: str):
        m = deps.store.get_message(mid)
        if m is None:
            raise HTTPException(status_code=404, detail="Unknown message")
        return m

    if cfg.enable_simulator:

        @r.post("/dev/messages/{mid}/simulate", dependencies=[post])
        def simulate_owner(mid: str, llm: int = 0) -> Response:
            try:
                reply = simulate.simulate_owner(deps, mid, use_llm=bool(llm))
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e)) from None
            if reply is None:
                deps.store.set_state(f"sim-noanswer-{mid}", {"at": deps.now_iso()})
            return _refresh()

        @r.post("/dev/escalate", dependencies=[post])
        def dev_escalate() -> Response:
            escalation.run_escalations(deps)
            return _refresh()

        @r.post("/dev/clock/advance", dependencies=[post])
        def clock_advance(hours: float = Form(..., ge=-720, le=720)) -> Response:
            # Step in <=1 h slices and tick the scheduler each time: a single big jump would land
            # outside the contact windows that opened and closed on the way, and re-plan them to the next day.
            left = hours
            while left > 0:
                step = min(1.0, left)
                deps.clock.advance(step)
                scheduler.run_scheduled(deps)
                left -= step
            if hours <= 0:
                deps.clock.advance(hours)
                scheduler.run_scheduled(deps)
            escalation.run_escalations(deps)
            return _refresh()

        @r.post("/dev/clock/reset", dependencies=[post])
        def clock_reset() -> Response:
            deps.clock.reset()
            return _refresh()

    if cfg.enable_simulator:  # process_sms skips sender and auth checks, so it is a simulator-only route

        @r.post("/dev/sms/{phone}/reply", dependencies=[post])
        def sms_reply(phone: str, text: str = Form(...)) -> Response:
            sms_inbound.process_sms(deps, phone, text)
            return _refresh()

    if cfg.mail_mode == "fake":

        @r.post("/dev/messages/{mid}/reply", dependencies=[post])
        def write_reply(
            mid: str,
            text: str = Form(...),
            from_email: str = Form(""),
            auth_pass: str = Form("1"),
            auto_reply: str = Form("0"),
            include_token: str = Form("1"),
        ) -> Response:
            m = msg_or_404(mid)
            to = tokenized_reply_to(cfg, m.id) if include_token == "1" else cfg.gmail_address
            deps.mail.inject_reply(
                to=to,
                from_email=from_email or m.to_email or m.contact_email,
                text=text,
                subject="Re: " + m.subject,
                thread_id=m.thread_id,
                auth_pass=auth_pass == "1",
                auto_reply=auto_reply == "1",
            )
            sync.sync_inbox(deps)
            return _refresh()

        @r.get("/dev/outbox")
        def outbox_json() -> dict:
            return {"mail": deps.mail.outbox, "whatsapp": getattr(deps.whatsapp, "calls", [])}

    if cfg.wa_mode == "fake":

        @r.post("/dev/messages/{mid}/wa-tap", dependencies=[post])
        def wa_tap(mid: str, code: str) -> Response:
            m = msg_or_404(mid)
            if code not in "AEDRCXW" or len(code) != 1:
                raise HTTPException(status_code=400, detail="Unknown button code")
            msg = {
                "from": m.to_phone_digits or digits(m.to_phone or ""),
                "id": f"wamid.DEV{uuid.uuid4().hex[:10]}",
                "type": "button",
                "button": {"payload": f"{code}:{token_for(cfg, m.id)}", "text": f"[{code}]"},
            }
            whatsapp_inbound.process_payload(deps, _payload([msg]))
            return _refresh()

        @r.post("/dev/messages/{mid}/wa-text", dependencies=[post])
        def wa_text(mid: str, text: str = Form(...), with_context: str = Form("0")) -> Response:
            m = msg_or_404(mid)
            msg: dict = {
                "from": m.to_phone_digits or digits(m.to_phone or ""),
                "id": f"wamid.DEV{uuid.uuid4().hex[:10]}",
                "type": "text",
                "text": {"body": text},
            }
            if with_context == "1" and m.provider_message_id:
                msg["context"] = {"id": m.provider_message_id}
            whatsapp_inbound.process_payload(deps, _payload([msg]))
            return _refresh()

    # ---- demo sidebar: the message comes from the picker as form field `mid`
    def panel_msg(mid: str, channel: str | None = None):
        if not mid:
            raise HTTPException(status_code=400, detail="Pick a message first")
        m = msg_or_404(mid)
        if channel and m.channel != channel:
            raise HTTPException(status_code=400, detail=f"That message went out by {m.channel}, not {channel}")
        return m

    if cfg.enable_simulator:

        @r.post("/dev/panel/simulate", dependencies=[post])
        def panel_simulate(mid: str = Form(""), llm: int = Form(0)) -> Response:
            return simulate_owner(panel_msg(mid).id, llm)

    if cfg.mail_mode == "fake":

        @r.post("/dev/panel/reply", dependencies=[post])
        def panel_reply(
            mid: str = Form(""),
            text: str = Form(...),
            from_email: str = Form(""),
            auth_pass: str = Form("1"),
            auto_reply: str = Form("0"),
            include_token: str = Form("1"),
        ) -> Response:
            return write_reply(panel_msg(mid, "email").id, text, from_email, auth_pass, auto_reply, include_token)

    if cfg.wa_mode == "fake":

        @r.post("/dev/panel/wa-tap", dependencies=[post])
        def panel_wa_tap(mid: str = Form(""), code: str = Form(...)) -> Response:
            return wa_tap(panel_msg(mid, "whatsapp").id, code)

        @r.post("/dev/panel/wa-text", dependencies=[post])
        def panel_wa_text(mid: str = Form(""), text: str = Form(...), with_context: str = Form("0")) -> Response:
            return wa_text(panel_msg(mid, "whatsapp").id, text, with_context)

    return r


def _payload(messages: list[dict]) -> dict:
    return {"entry": [{"changes": [{"field": "messages", "value": {"messages": messages}}]}]}
