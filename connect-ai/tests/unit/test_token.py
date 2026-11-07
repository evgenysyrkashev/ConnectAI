from app.core.token import extract_tokens, new_message_id, reply_address, sign_token, verify_token

KEY = "k" * 40


def test_round_trip():
    mid = new_message_id()
    assert len(mid) == 16
    assert verify_token(sign_token(mid, KEY), KEY) == mid


def test_tampered_or_wrong_key():
    tok = sign_token(new_message_id(), KEY)
    bad = tok[:-1] + ("0" if tok[-1] != "0" else "1")
    assert verify_token(bad, KEY) is None
    assert verify_token(tok, "other-key") is None
    assert verify_token("zz" * 16, KEY) is None
    assert verify_token(tok[:-2], KEY) is None


def test_uppercase_accepted():
    mid = new_message_id()
    assert verify_token(sign_token(mid, KEY).upper(), KEY) == mid


def test_extract_tokens():
    tok = sign_token(new_message_id(), KEY)
    assert extract_tokens([f"Connect <bot+{tok}@gmail.com>", f"x+{tok.upper()}@y.com"]) == [tok]
    assert extract_tokens(["nothing here"]) == []


def test_reply_address_length():
    tok = sign_token(new_message_id(), KEY)
    addr = reply_address("a" * 30 + "@gmail.com", tok)
    assert len(addr.split("@")[0]) <= 64
