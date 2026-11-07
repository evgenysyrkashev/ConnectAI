import re

import pytest

from app.core.token import reply_address
from app.server.services import campaigns, send, sync
from app.server.services.common import tokenized_reply_to
from tests.world import World


@pytest.fixture
def world():
    return World()


def make_world(env=None, **kw):
    return World(env, **kw)


def draft(world: World, tpl="holidays", eids=("FI-T1",)):
    c = campaigns.create_campaign(world.deps, tpl, {}, list(eids), "op@example.com")
    return c, world.store.list_messages(c.id)


def sent_message(world: World, tpl="holidays", eid="FI-T1"):
    _c, msgs = draft(world, tpl, (eid,))
    msg = next(m for m in msgs if m.entity_id == eid)
    assert msg.status == "draft", msg.skip_reason
    res = send.send_message(world.deps, msg.id)
    assert res["status"] == "sent", res
    return world.store.get_message(msg.id)


def email_reply(world: World, msg, text: str, *, from_email="tester@test.example", token=True, thread=None, **kw):
    to = tokenized_reply_to(world.cfg, msg.id) if token else world.cfg.gmail_address
    pid = world.mail.inject_reply(
        to=to,
        from_email=from_email,
        text=text,
        subject="Re: " + msg.subject,
        thread_id=thread if thread is not None else msg.thread_id,
        **kw,
    )
    sync.sync_inbox(world.deps)
    return world.store.get_reply(pid)


def reply_to_regex():
    return re.compile(r"\+[0-9a-f]{32}@")


_ = reply_address
