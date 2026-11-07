"""Scheduled first send: held until the contact window, driven by the demo clock."""

from fastapi.testclient import TestClient

from app.core.escalation import next_window_start
from app.server.adapters.clock import OffsetClock
from app.server.main import create_app
from app.server.services import scheduler
from tests.services.conftest import make_world
from tests.world import NOW

HX = {"HX-Request": "true"}


def world_at(utc_hour: int, window="10-18"):
    w = make_world(eids=())
    w.clock.at = NOW.replace(hour=utc_hour)  # Helsinki is UTC+2 in November
    w.add_entity("FI-T1", best_contact_window=window)
    return w


def test_next_window_start():
    tz = "Europe/Helsinki"
    inside = NOW.replace(hour=9)  # 11:00 local
    assert next_window_start(inside, "10-18", tz) == inside
    assert next_window_start(NOW.replace(hour=4), "10-18", tz).hour == 8  # 06:00 local -> 10:00 local today
    nxt = next_window_start(NOW.replace(hour=17), "10-18", tz)  # 19:00 local -> 10:00 tomorrow
    assert (nxt.day, nxt.hour) == (NOW.day + 1, 8)
    assert next_window_start(inside, "garbage", tz) == inside


def test_outside_window_is_held_then_sent_when_the_clock_reaches_it():
    w = world_at(4)  # 06:00 local, window opens at 10:00 local = 08:00 UTC
    camp = scheduler.schedule_for(w.deps, ["FI-T1"], "op@example.com")
    (m,) = w.store.list_messages(camp.id)
    assert m.status == "draft" and m.scheduled_at == "2026-11-06T08:00:00Z"
    assert scheduler.run_scheduled(w.deps) == {"sent": 0, "deferred": 0} and w.mail.outbox == []
    w.clock.advance(3)  # 07:00 UTC, still before
    assert scheduler.run_scheduled(w.deps)["sent"] == 0
    w.clock.advance(1)  # 08:00 UTC
    assert scheduler.run_scheduled(w.deps)["sent"] == 1
    assert w.store.get_message(m.id).status == "sent" and len(w.mail.outbox) == 1


def test_inside_window_is_scheduled_for_now():
    w = world_at(9)
    camp = scheduler.schedule_for(w.deps, ["FI-T1"], "op@example.com")
    (m,) = w.store.list_messages(camp.id)
    assert m.scheduled_at == "2026-11-06T09:00:00Z"
    assert scheduler.run_scheduled(w.deps)["sent"] == 1


def test_window_missed_is_replanned_not_sent():
    w = world_at(4)
    camp = scheduler.schedule_for(w.deps, ["FI-T1"], "op@example.com")
    (m,) = w.store.list_messages(camp.id)
    w.clock.advance(15)  # 19:00 UTC = 21:00 local, the window has closed
    assert scheduler.run_scheduled(w.deps) == {"sent": 0, "deferred": 1}
    assert w.mail.outbox == []
    assert w.store.get_message(m.id).scheduled_at == "2026-11-07T08:00:00Z"
    w.clock.advance(13)  # next day 08:00 UTC
    assert scheduler.run_scheduled(w.deps)["sent"] == 1


def test_no_double_scheduling():
    w = world_at(4)
    assert scheduler.schedule_for(w.deps, ["FI-T1"], "op") is not None
    assert scheduler.schedule_for(w.deps, ["FI-T1"], "op") is None


def test_auto_schedules_everyone_and_simulates_the_owner_after_sending():
    w = world_at(4)
    assert scheduler.run_scheduled(w.deps)["sent"] == 0  # first tick drafts + schedules, nothing due yet
    (m,) = w.store.messages.values()
    assert m.status == "draft" and m.scheduled_at == "2026-11-06T08:00:00Z"
    assert scheduler.run_scheduled(w.deps)["sent"] == 0 and len(w.store.messages) == 1  # no duplicates
    w.clock.advance(4)
    assert scheduler.run_scheduled(w.deps)["sent"] == 1
    assert len(w.store.replies) == 1
    assert len(w.store.messages) == 1  # sent messages are not scheduled again


def test_no_simulation_when_simulator_is_off():
    w = world_at(9)
    w.deps.cfg = w.cfg.model_copy(update={"enable_simulator": False})
    assert scheduler.run_scheduled(w.deps)["sent"] == 1  # inside the window: scheduled and sent in one tick
    assert not w.store.replies


def test_ui_column_and_demo_clock():
    w = world_at(4)
    w.deps.clock = OffsetClock(w.clock, w.store)
    c = TestClient(create_app(w.cfg, w.deps))
    page = c.get("/").text
    assert "<th>Scheduled</th>" in page and "10-18" in page and "Fri 06 Nov 10:00" in page and "not scheduled" in page
    scheduler.auto_schedule(w.deps)  # a tick schedules everyone
    page = c.get("/").text
    assert "sched-scheduled" in page and "not scheduled" not in page
    r = c.post("/dev/clock/advance", data={"hours": "4"}, headers=HX)  # 08:00 UTC: window opens, scheduler fires
    assert r.status_code == 204 and len(w.mail.outbox) == 1
    assert "sched-sent" not in c.get("/").text  # sent items drop off the table
