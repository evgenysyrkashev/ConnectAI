from app.core.learning import entry_from_decision, merge, override


def h(date, outcome, hours, key="XMAS_EVE"):
    return {"date": date, "day_key": key, "outcome": outcome, "hours": hours}


def test_edit_wins_next_year():
    o = override([h("2025-12-24", "edited", "10:00-14:00")], "XMAS_EVE", "2026-12-24", "08:00-20:00", "closed")
    assert o["action"] == "SUGGEST" and o["hours"] == "10:00-14:00" and o["basis"] == "OWN_EDIT"


def test_approved_is_repeated_even_without_detector_suggestion():
    o = override([h("2025-12-24", "approved", "closed")], "XMAS_EVE", "2026-12-24", "08:00-20:00")
    assert (o["action"], o["hours"], o["basis"]) == ("SUGGEST", "closed", "OWN_APPROVED")


def test_own_hours_equal_to_shown_is_quiet():
    o = override([h("2025-12-24", "edited", "08:00-20:00")], "XMAS_EVE", "2026-12-24", "08:00-20:00", "closed")
    assert o["action"] == "NO_ACTION"


def test_declined_blocks_only_the_same_suggestion():
    hist = [h("2025-12-24", "declined", "closed")]
    assert override(hist, "XMAS_EVE", "2026-12-24", "08:00-20:00", "closed")["action"] == "QUIET"
    assert override(hist, "XMAS_EVE", "2026-12-24", "08:00-20:00", "10:00-14:00") is None
    assert override(hist, "XMAS_EVE", "2026-12-24", "08:00-20:00", None) is None


def test_same_year_and_other_days_are_ignored():
    hist = [h("2026-12-24", "edited", "10:00-14:00"), h("2025-12-31", "edited", "10:00-12:00", "NYE")]
    assert override(hist, "XMAS_EVE", "2026-12-24", "08:00-20:00", "closed") is None


def test_latest_year_wins():
    hist = [h("2024-12-24", "edited", "09:00-12:00"), h("2025-12-24", "approved", "closed")]
    assert override(hist, "XMAS_EVE", "2026-12-24", "08:00-20:00")["hours"] == "closed"


def test_entry_from_decision():
    assert entry_from_decision("2026-12-24", "XMAS_EVE", "regular", "closed", None) is None
    assert entry_from_decision("2026-12-24", "XMAS_EVE", "decline", "closed", None)["hours"] == "closed"
    assert entry_from_decision("2026-12-24", "XMAS_EVE", "set", "closed", "10:00-14:00")["outcome"] == "edited"
    assert len(merge([h("2025-12-24", "approved", "closed")], [h("2025-12-24", "edited", "9-12")])) == 1
