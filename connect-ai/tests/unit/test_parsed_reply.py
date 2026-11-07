from app.core.decide import decide
from app.core.models import DateDecision, ParsedReply, ReplyChecks
from app.core.parsed_reply import valid_hours, validate_parsed
from tests.conftest import make_message


def P(**kw) -> ParsedReply:
    base = {"intent": "edit", "summary": "s", "confidence": 0.9}
    base.update(kw)
    return ParsedReply(**base)


def dd(date, action, hours=None):
    return DateDecision(date=date, action=action, hours=hours)


def test_valid_hours():
    assert valid_hours("closed") and valid_hours("18:00-02:00") and valid_hours("00:00-23:59")
    assert valid_hours("10:00-14:00,17:00-22:00")
    assert not valid_hours("10:00-10:00") and not valid_hours("25:00-26:00") and not valid_hours("10-14")


def run(parsed, message=None):
    message = message or make_message()
    from app.core.apply import resolve_decisions

    return validate_parsed(parsed, resolve_decisions(parsed, message), message)


def test_clean():
    p = P(dates=[dd("2026-12-24", "set", "10:00-14:00")])
    assert run(p) == []
    assert run(None) == []


def test_kind_mismatch():
    assert any("Weekly" in x for x in run(P(weekly={"monday": "closed"}, dates=[dd("2026-12-24", "accept")])))
    wk = make_message(kind="weekly")
    assert any("Dates given" in x for x in run(P(dates=[dd("2026-12-24", "accept")], weekly={"monday": "closed"}), wk))
    perm = make_message(kind="permission", template_id="permission")
    assert any("permission" in x for x in run(P(intent="approve", dates=[dd("2026-12-24", "accept")]), perm))
    assert run(P(intent="approve"), perm) == []


def test_dates_rules():
    assert any("not one we asked" in x for x in run(P(dates=[dd("2026-12-25", "accept")])))
    assert any("twice" in x for x in run(P(dates=[dd("2026-12-24", "accept"), dd("2026-12-24", "regular")])))
    assert any("Invalid hours" in x for x in run(P(dates=[dd("2026-12-24", "set", "10-14")])))
    assert any("Invalid hours" in x for x in run(P(dates=[dd("2026-12-24", "set", None)])))
    assert any("Invalid hours" in x for x in run(P(dates=[dd("2026-12-24", "set", "10:00-10:00")])))
    assert any("Hours given" in x for x in run(P(dates=[dd("2026-12-24", "accept", "closed")])))


def test_weekly_rules():
    wk = make_message(kind="weekly")
    assert any("Unknown weekday" in x for x in run(P(weekly={"funday": "closed"}), wk))
    assert any("Invalid hours" in x for x in run(P(weekly={"monday": "9-17"}), wk))
    assert any("not change" in x for x in run(P(weekly={}), wk))
    assert run(P(weekly={"monday": "09:00-17:00"}), wk) == []


def test_edit_nothing_and_closed():
    assert any("not change" in x for x in run(P(dates=[dd("2026-12-24", "decline")])))
    assert any("closed for good" in x for x in run(P(intent="unclear", permanently_closed=True)))


def checks(**kw) -> ReplyChecks:
    base = {
        "token_valid": True,
        "matched_by": "token",
        "sender_matches": True,
        "auth_pass": True,
        "auto_reply": False,
        "expired": False,
        "duplicate": False,
    }
    base.update(kw)
    return ReplyChecks(**base)


def D(c=None, parsed=None, problems=(), message=None, auto=True, minc=0.8):
    return decide(c or checks(), parsed or P(intent="approve"), list(problems), message or make_message(), auto, minc)


def test_decide_happy():
    d = D()
    assert d.action == "apply" and d.problems == []


def test_decide_each_problem():
    cases = [
        ({"c": checks(sender_matches=False)}, "Sender"),
        ({"c": checks(auth_pass=False)}, "DKIM"),
        ({"c": checks(expired=True)}, "expired"),
        ({"c": checks(duplicate=True)}, "already has"),
        ({"c": checks(matched_by="thread")}, "thread only"),
        ({"parsed": P(intent="unclear")}, "unclear"),
        ({"parsed": P(intent="approve", confidence=0.5)}, "Low confidence"),
        ({"problems": ["x problem"]}, "x problem"),
        ({"auto": False}, "disabled"),
        ({"parsed": P(intent="decline"), "message": make_message(mode="inform")}, "disputes"),
    ]
    for kw, needle in cases:
        d = D(**kw)
        assert d.action == "review" and any(needle in p for p in d.problems), (kw, d)
    d = decide(checks(), None, [], make_message(), True, 0.8)
    assert d.action == "review" and "No parsed answer" in d.problems


def test_decide_button_context_phone_ok():
    for m in ("button", "context", "phone"):
        assert D(c=checks(matched_by=m)).action == "apply"


def test_simulator_bypass_is_checks_true():
    # the caller sets sender_matches/auth_pass True for simulator and SMS sources
    assert D(c=checks(sender_matches=True, auth_pass=True, matched_by="token")).action == "apply"
