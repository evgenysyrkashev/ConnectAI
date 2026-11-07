from app.core.allowlist import is_allowed
from app.core.email_checks import auth_pass, is_auto_reply, parse_auth_results, same_mailbox

AR = "mx.google.com; dkim=pass header.i=@x.com; spf=pass smtp.mailfrom=x.com; dmarc=pass (p=NONE)"


def test_auth_results():
    r = parse_auth_results(["other.host; dkim=fail", AR])
    assert r == {"dkim": "pass", "spf": "pass", "dmarc": "pass"} and auth_pass(r)
    assert not auth_pass(parse_auth_results(["mx.google.com; dkim=fail; dmarc=fail"]))
    assert parse_auth_results([]) == {} and not auth_pass({})
    assert auth_pass({"dmarc": "pass"}) and not auth_pass({"dkim": "pass"})


def test_auto_reply_rules():
    assert not is_auto_reply({}, "a@b.com")
    assert is_auto_reply({"auto-submitted": "auto-replied"}, "a@b.com")
    assert not is_auto_reply({"auto-submitted": "no"}, "a@b.com")
    assert is_auto_reply({"X-Autoreply": "yes"}, "a@b.com")
    assert is_auto_reply({"x-autorespond": "1"}, "a@b.com")
    assert is_auto_reply({"x-auto-response-suppress": "All"}, "a@b.com")
    for p in ("bulk", "junk", "list", "auto_reply"):
        assert is_auto_reply({"precedence": p}, "a@b.com")
    assert not is_auto_reply({"precedence": "normal"}, "a@b.com")
    for f in ("MAILER-DAEMON@x.com", "postmaster@x.com", "noreply@x.com", "no-reply@x.com"):
        assert is_auto_reply({}, f)


def test_same_mailbox():
    assert same_mailbox("you+fi-d0001@gmail.com", "You@gmail.com")
    assert same_mailbox("Maria <you@gmail.com>", "you+x@gmail.com")
    assert not same_mailbox("you@gmail.com", "other@gmail.com")
    assert not same_mailbox("you@gmail.com", "you@other.com")
    assert not same_mailbox("", "you@gmail.com")


def test_allowlist():
    assert is_allowed("anyone@x.com", ["*"])
    assert is_allowed("a@test.example", ["@test.example"])
    assert not is_allowed("a@other.example", ["@test.example"])
    assert is_allowed("you+fi@gmail.com", ["you@gmail.com"])
    assert not is_allowed("x@gmail.com", ["you@gmail.com"])
    assert not is_allowed("a@test.example", [])
    assert is_allowed("A@Test.Example", ["@test.example"])
