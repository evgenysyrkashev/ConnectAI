from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.core.escalation import parse_chain, plan_escalation

CHAIN = {"whatsapp": "email", "sms": "email"}
HEL = ZoneInfo("Europe/Helsinki")


def plan(
    sent,
    channel="whatsapp",
    usual=0.4,
    window="10-18",
    tz="Europe/Helsinki",
    factor=2.0,
    min_h=4,
    respect=True,
    chain=CHAIN,
):
    return plan_escalation(sent, channel, usual, "channel", window, tz, chain, factor, min_h, respect)


def utc(*a):
    return datetime(*a, tzinfo=UTC)


def local(t):
    return t.astimezone(HEL)


def test_parse_chain():
    assert parse_chain("whatsapp>email;sms>email;email>permission") == {
        "whatsapp": "email",
        "sms": "email",
        "email": "permission",
    }
    assert parse_chain("") == {} and parse_chain(["a>b"]) == {"a": "b"}


def test_no_fallback_for_channel():
    assert plan(utc(2026, 11, 6, 9), channel="email") == (None, None)


def test_floor_wins_and_inside_window():
    t, basis = plan(utc(2026, 11, 6, 9))  # 11:00 local; 2×0.4 h < 4 h floor → 15:00 local
    assert t == utc(2026, 11, 6, 13) and local(t).hour == 15
    assert "wait 4.0 h" in basis and "usual 0.4 h (channel)" in basis and "2× " in basis


def test_factor_above_floor():
    t, basis = plan(utc(2026, 11, 6, 8), usual=2.0, window="")  # 4 h wait = 2×2 → equals floor; try 3
    t, basis = plan(utc(2026, 11, 6, 8), usual=3.0, window="")
    assert t == utc(2026, 11, 6, 14) and "wait 6.0 h" in basis and "no window" in basis


def test_before_window_moves_to_same_day_start():
    t, _ = plan(utc(2026, 11, 6, 3), min_h=1, usual=0.1)  # 05:00 local + 1 h = 06:00 → 10:00 same day
    assert local(t).hour == 10 and local(t).day == 6


def test_after_window_moves_to_next_day():
    t, basis = plan(utc(2026, 11, 6, 14, 30))  # 16:30 local + 4 h = 20:30 → next day 10:00
    assert local(t).day == 7 and local(t).hour == 10 and local(t).minute == 0
    assert "moved to window 10–18" in basis


def test_dst_transition():
    # EEST (+3) ends 25 Oct 2026. Sent Sat 24 Oct 17:00 local (14:00 UTC) → +4 h = 21:00 → Sun 25 Oct 10:00 EET (+2).
    t, _ = plan(utc(2026, 10, 24, 14))
    assert local(t).day == 25 and local(t).hour == 10
    assert t == utc(2026, 10, 25, 8)  # 10:00 at +2 = 08:00 UTC, not 07:00


def test_unparseable_window_no_shift():
    for w in ("", "anytime", "25-26x", "10"):
        t, basis = plan(utc(2026, 11, 6, 15), window=w)
        assert t == utc(2026, 11, 6, 19) and "no window" in basis
    t, _ = plan(utc(2026, 11, 6, 15), respect=False)
    assert t == utc(2026, 11, 6, 19)
