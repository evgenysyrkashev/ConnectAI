from app.server.services import review
from tests.services.conftest import email_reply, make_world, sent_message
from tests.world import FakeYext, entity

ENV = {
    "YEXT_SANDBOX_MIRROR": "true",
    "YEXT_SANDBOX_API_KEY": "sbx-key",
    "YEXT_SANDBOX_ENTITY_MAP": "FI-T1=SBX-1;FI-X=SBX-2",
}


def sandbox_world():
    w = make_world(ENV)
    sbx = FakeYext()
    ent = entity("SBX-1")
    ent["hours"]["holidayHours"] = [{"date": "2026-12-06", "isClosed": True}]
    sbx.add(ent)
    w.deps.extras["sandbox"] = sbx
    return w, sbx


def test_mapped_entity_gets_full_hours_with_new_dates():
    w, sbx = sandbox_world()
    m = sent_message(w)
    r = email_reply(w, m, "OK")
    assert r.status == "applied"
    h = sbx.get_entity("SBX-1")["hours"]
    assert [x["date"] for x in h["holidayHours"]] == [
        "2026-12-06",
        "2026-12-24",
        "2026-12-31",
    ]  # own entry kept, ours added
    assert set(h) >= {"monday", "sunday", "holidayHours"}  # a full hours object, not a fragment
    ch = w.store.get_change(r.change_id)
    assert (
        ch.sandbox["ok"] is True
        and ch.sandbox["error"] is None
        and ch.sandbox["listings"][0]["publisherId"] == "GOOGLEMYBUSINESS"
    )


def test_sandbox_failure_does_not_fail_the_real_flow():
    w, sbx = sandbox_world()
    sbx.fail_put = "401 invalid key"
    m = sent_message(w)
    r = email_reply(w, m, "OK")
    assert r.status == "applied" and w.yext.holiday("FI-T1", "2026-12-24")["isClosed"] is True
    ch = w.store.get_change(r.change_id)
    assert ch.sandbox["ok"] is False and "invalid key" in ch.sandbox["error"]


def test_unmapped_or_disabled_is_a_no_op():
    w, sbx = sandbox_world()
    w.deps.cfg = w.cfg.model_copy(update={"yext_sandbox_entity_map": "FI-X=SBX-2"})
    m = sent_message(w)
    r = email_reply(w, m, "OK")
    assert w.store.get_change(r.change_id).sandbox is None and sbx.puts == []
    w2 = make_world()  # mirror off
    r2 = email_reply(w2, sent_message(w2), "OK")
    assert w2.store.get_change(r2.change_id).sandbox is None


def test_revert_is_mirrored():
    w, sbx = sandbox_world()
    r = email_reply(w, sent_message(w), "OK")
    rev = review.revert(w.deps, r.change_id, "op")
    assert [x["date"] for x in sbx.get_entity("SBX-1")["hours"]["holidayHours"]] == ["2026-12-06"]
    assert w.store.get_change(rev.id).sandbox["ok"] is True
