import copy

import pytest

from app import kit
from app.core.apply import compute_hours_update, holiday_item, resolve_decisions, revert_hours
from app.core.models import DateDecision, ParsedReply, YextChange
from tests.conftest import make_item, make_message


def P(intent, **kw):
    return ParsedReply(intent=intent, summary="s", confidence=0.9, **kw)


def dd(date, action, hours=None):
    return DateDecision(date=date, action=action, hours=hours)


HOURS = {
    **{d: {"openIntervals": [{"start": "09:00", "end": "17:00"}]} for d in kit.DAYS},
    "saturday": {"isClosed": True},
    "holidayHours": [
        {"date": "2026-12-06", "isClosed": True},
        {"date": "2026-12-31", "openIntervals": [{"start": "08:00", "end": "20:00"}]},
    ],
}


def test_resolve_decisions():
    m = make_message([make_item("2026-12-24", "closed"), make_item("2026-12-31", None, basis=None)])
    assert [d.action for d in resolve_decisions(P("approve"), m)] == ["accept", "regular"]
    assert [d.action for d in resolve_decisions(P("decline"), m)] == ["decline", "decline"]
    given = [dd("2026-12-24", "set", "10:00-14:00")]
    assert resolve_decisions(P("edit", dates=given), m) == given
    assert resolve_decisions(P("unclear"), m) == [] and resolve_decisions(None, m) == []
    assert resolve_decisions(P("approve"), make_message(kind="weekly")) == []


def test_holiday_item_every_action():
    it = make_item("2026-12-24", "closed")
    assert holiday_item("2026-12-24", dd("2026-12-24", "accept"), it) == {"date": "2026-12-24", "isClosed": True}
    nosug = make_item("2026-12-24", None, basis=None)
    assert holiday_item("2026-12-24", dd("2026-12-24", "accept"), nosug) == {
        "date": "2026-12-24",
        "isRegularHours": True,
    }
    assert holiday_item("2026-12-24", dd("2026-12-24", "regular"), it) == {"date": "2026-12-24", "isRegularHours": True}
    exc = make_item("2026-12-24", "closed", shown_source="exception")
    assert holiday_item("2026-12-24", dd("2026-12-24", "regular"), exc) == {
        "date": "2026-12-24",
        "isRegularHours": True,
    }
    assert holiday_item("2026-12-24", dd("2026-12-24", "set", "10:00-14:00,17:00-22:00"), it) == {
        "date": "2026-12-24",
        "openIntervals": [{"start": "10:00", "end": "14:00"}, {"start": "17:00", "end": "22:00"}],
    }
    assert holiday_item("2026-12-24", dd("2026-12-24", "decline"), it) is None


def test_compute_hours_update_dates():
    m = make_message([make_item("2026-12-24", "closed"), make_item("2026-12-31", "10:00-14:00")])
    decisions = resolve_decisions(P("approve"), m)
    orig = copy.deepcopy(HOURS)
    new, before, after = compute_hours_update(HOURS, m, decisions, P("approve"))
    assert HOURS == orig  # deep copy
    assert [h["date"] for h in new["holidayHours"]] == [
        "2026-12-06",
        "2026-12-24",
        "2026-12-31",
    ]  # sorted, 12-06 untouched
    assert new["holidayHours"][0] == {"date": "2026-12-06", "isClosed": True}
    assert new["monday"] == HOURS["monday"]
    assert set(before) == set(after) == {"holidayHours"}
    assert set(before["holidayHours"]) == {"2026-12-24", "2026-12-31"}
    assert before["holidayHours"]["2026-12-24"] is None and before["holidayHours"]["2026-12-31"]["openIntervals"]
    assert after["holidayHours"]["2026-12-31"]["openIntervals"] == [{"start": "10:00", "end": "14:00"}]


def test_decline_writes_nothing():
    m = make_message()
    new, before, after = compute_hours_update(HOURS, m, resolve_decisions(P("decline"), m), P("decline"))
    assert new == HOURS and before == {} and after == {}


def test_compute_hours_update_weekly():
    m = make_message(kind="weekly")
    p = P("edit", weekly={"monday": "10:00-18:00", "sunday": "closed"})
    new, before, after = compute_hours_update(HOURS, m, [], p)
    assert set(before) == set(after) == {"monday", "sunday"}
    assert new["monday"] == {"openIntervals": [{"start": "10:00", "end": "18:00"}]} and new["sunday"] == {
        "isClosed": True
    }
    assert new["tuesday"] == HOURS["tuesday"] and new["holidayHours"] == HOURS["holidayHours"]
    assert compute_hours_update(HOURS, m, [], P("approve"))[2] == {}


@pytest.fixture(scope="module")
def validate_hours():
    return kit.mock_server_module().validate_hours


def test_output_passes_kit_validation(validate_hours):
    m = make_message([make_item("2026-12-24", "closed"), make_item("2026-12-31", "18:00-02:00")])
    p = P("edit", dates=[dd("2026-12-24", "set", "10:00-14:00,17:00-22:00"), dd("2026-12-31", "regular")])
    new, _, _ = compute_hours_update(HOURS, m, resolve_decisions(p, m), p)
    result = validate_hours(new)
    assert not result  # kit returns an error string / falsy when valid


def test_revert_restores_exactly():
    m = make_message([make_item("2026-12-24", "closed"), make_item("2026-12-31", "10:00-14:00")])
    d = resolve_decisions(P("approve"), m)
    new, before, after = compute_hours_update(HOURS, m, d, P("approve"))
    change = YextChange(
        id="c", entity_id="e", message_id=None, reply_id=None, actor="auto", before=before, after=after, created_at="x"
    )
    assert revert_hours(new, change) == HOURS
    wk = make_message(kind="weekly")
    new2, b2, a2 = compute_hours_update(HOURS, wk, [], P("edit", weekly={"monday": "closed"}))
    ch2 = YextChange(
        id="c", entity_id="e", message_id=None, reply_id=None, actor="auto", before=b2, after=a2, created_at="x"
    )
    assert revert_hours(new2, ch2) == HOURS
