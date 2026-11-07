import pytest

from app.core.priority import at_risk_views, item_priority, message_priority, top_items, weekly_priority
from app.core.quiet import filter_items, message_skip
from app.core.templates import TEMPLATES, selectable_templates
from tests.conftest import make_item

TODAY = "2026-11-06"


def test_item_priority():
    assert item_priority(100, 0.9, "10:00-14:00", "08:00-20:00", 1.5) == pytest.approx(90)
    assert item_priority(100, None, "10:00-14:00", "08:00-20:00", 1.5) == pytest.approx(80)
    assert item_priority(100, None, "closed", "08:00-20:00", 1.5) == pytest.approx(120)  # closed-door weight
    assert item_priority(100, None, "closed", "closed", 1.5) == pytest.approx(80)  # shown closed: no weight
    assert item_priority(100, None, "10:00-14:00", "closed", 1.5) == pytest.approx(80)
    assert item_priority(100, 0.9, None, "08:00-20:00", 1.5) == pytest.approx(30)  # ask items


def test_message_priority_and_helpers():
    items = [
        make_item(priority=10.04),
        make_item("2026-12-25", priority=20.0),
        make_item("2026-12-26", None, priority=1.0),
    ]
    assert message_priority(items) == 31.0
    assert at_risk_views(items) == 200  # ask item excluded
    assert weekly_priority(10) == 35


def test_top_items_keeps_best_listed_by_date():
    items = [make_item(f"2026-12-{10 + i}", priority=float(p)) for i, p in enumerate([5, 1, 9, 3, 8, 7, 2, 6])]
    top = top_items(items, 6)
    assert len(top) == 6 and [i.date for i in top] == sorted(i.date for i in top)
    assert {i.priority for i in top} == {5, 9, 8, 7, 6, 3}


def F(items, live=(), asked=(), exempt=()):
    return filter_items(items, set(live), set(asked), TODAY, set(exempt))


def test_drop_rules_individually():
    a = make_item("2026-12-24", "closed")
    assert F([a])[0] == [a]
    assert F([a], live={"2026-12-24"})[1][0][1] == "already_entered"
    assert F([a], asked={"2026-12-24"})[1][0][1] == "already_asked"
    assert F([make_item("2026-11-06", "closed")])[1][0][1] == "date_passed"
    assert F([make_item("2026-11-01", "closed")])[1][0][1] == "date_passed"
    assert F([make_item("2026-12-24", "closed", shown="closed")])[1][0][1] == "no_evidence"
    ask = make_item("2026-12-24", None, basis=None)
    assert F([ask])[0] == [ask]  # ask items are not "redundant"


def test_exempt_dates_only_for_already_asked():
    a = make_item("2026-12-24", "closed")
    assert F([a], asked={"2026-12-24"}, exempt={"2026-12-24"})[0] == [a]
    assert F([a], live={"2026-12-24"}, exempt={"2026-12-24"})[1][0][1] == "already_entered"


def test_kept_order_preserved():
    items = [make_item("2026-12-31"), make_item("2026-12-24"), make_item("2026-12-27")]
    kept, dropped = F(items, live={"2026-12-24"})
    assert [i.date for i in kept] == ["2026-12-31", "2026-12-27"] and len(dropped) == 1


def S(**kw):
    base = {
        "has_contact": True,
        "opted_out": False,
        "closed_in_yext": False,
        "flagged_evidence": None,
        "kept": [make_item()],
        "dropped": [],
    }
    base.update(kw)
    return message_skip(**base)


def test_message_skip_order():
    assert S() is None
    assert S(has_contact=False, opted_out=True)[0] == "no_contact"
    assert S(opted_out=True, closed_in_yext=True, flagged_evidence="x")[0] == "opted_out"
    assert S(closed_in_yext=True, flagged_evidence="x") == ("closed_in_yext", "closed in Yext")
    assert S(flagged_evidence="reviews say closed", kept=[]) == ("flagged", "flagged: reviews say closed")
    assert S(kept=[])[0] == "no_evidence"


def test_most_common_drop_code():
    a, b, c = make_item("2026-12-24"), make_item("2026-12-25"), make_item("2026-12-26")
    dropped = [(a, "already_asked"), (b, "already_entered"), (c, "already_asked")]
    assert S(kept=[], dropped=dropped)[0] == "already_asked"
    assert S(kept=[], dropped=[(a, "already_entered")])[0] == "already_entered"


def test_templates():
    assert set(TEMPLATES) == {"holidays", "event", "stale_hours", "permission"}
    assert [t.id for t in selectable_templates()] == ["holidays", "event", "stale_hours"]
    p = TEMPLATES["holidays"].params_model()
    assert str(p.date_from) == "2026-11-07" and str(p.date_to) == "2027-01-06"
    assert TEMPLATES["stale_hours"].kind == "weekly" and TEMPLATES["permission"].kind == "permission"
