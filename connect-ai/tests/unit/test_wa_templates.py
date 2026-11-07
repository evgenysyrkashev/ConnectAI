import pytest

from app.core import wa_templates as wt
from app.core.webhook_sig import verify_meta_signature
from tests.conftest import make_contact, make_item, make_message

LANGS = ("fi", "sv", "nb", "en")


def test_every_template_in_all_languages():
    assert set(wt.CODES) == set(wt.BODY) == set(wt.BUTTONS)
    for name in wt.CODES:
        assert set(wt.BODY[name]) == set(LANGS) == set(wt.BUTTONS[name])
        for lang in LANGS:
            assert len(wt.BUTTONS[name][lang]) == len(wt.CODES[name])
            assert wt.footer(lang)


@pytest.mark.parametrize("name", list(wt.BODY))
@pytest.mark.parametrize("lang", LANGS)
def test_body_rules(name, lang):
    body = wt.BODY[name][lang]
    assert not body.startswith("{{") and not body.rstrip().endswith("}}")
    n = wt.param_count(name)
    assert all(f"{{{{{i}}}}}" in body for i in range(1, n + 1))
    assert all(len(b) <= 25 for b in wt.BUTTONS[name][lang])


def _msgs(lang):
    sugg = make_message(lang=lang)
    ask = make_message([make_item("2026-12-24", None, basis=None)], lang=lang)
    weekly = make_message(kind="weekly", lang=lang)
    inform = make_message(mode="inform", lang=lang)
    return {
        "connect_hours_suggestion": sugg,
        "connect_hours_question": ask,
        "connect_hours_check": weekly,
        "connect_hours_updated": inform,
    }


@pytest.mark.parametrize("lang", LANGS)
def test_wa_content_matches_param_count(lang):
    for expect, m in _msgs(lang).items():
        name, params, codes = wt.wa_content(m, make_contact(lang), lang)
        assert name == expect
        assert len(params) == wt.param_count(name)
        assert codes == wt.CODES[name]
        assert all("\n" not in p and "\t" not in p and "  " not in p for p in params)
        assert "{{" not in wt.render_body(name, lang, params)


def test_suggestion_params():
    _name, params, codes = wt.wa_content(make_message(), make_contact("fi"), "fi")
    assert params[0] == "Maria" and params[2] == "Kahvila Testi"
    assert (
        params[3] == "to 24.12. 8–20; to 31.12. 8–20"
        and params[4] == "to 24.12. kiinni; to 31.12. 10–14 (Syy: kuten viime vuonna)"
    )
    assert params[1] == "Olemme valmistelleet ehdotukset aukioloajoiksi tuleville juhlapyhille."  # fallback short
    assert codes == ["A", "E", "D"]


def test_long_body_drops_lowest_priority(monkeypatch):
    monkeypatch.setattr(
        wt, "WA_BODY_LIMIT", 520
    )  # 6 real items never reach 1024; shrink the limit to exercise the loop
    items = [make_item(f"2026-12-{10 + i}", "closed", priority=float(p)) for i, p in enumerate([1, 9, 8, 7, 6, 5])]
    m = make_message(items, entity_name="N" * 200, short="s" * 160)
    name, params, _, dropped = wt.wa_content_fitted(m, make_contact("en"), "en")
    assert len(wt.render_body(name, "en", params)) <= 520
    assert dropped >= 1 and "10 Dec" not in params[3]


def test_updated_params_sanitized():
    p = wt.updated_params("Maria", "Kahvila\nTesti", "to 24.12. kiinni", "fi")
    assert p[1] == "Kahvila Testi" and p[3] == "Muutokset näkyvät Googlessa vuorokauden kuluessa."


def test_webhook_signature():
    import hashlib
    import hmac

    body = b'{"x":1}'
    good = "sha256=" + hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    assert verify_meta_signature("secret", body, good)
    assert not verify_meta_signature("secret", body + b" ", good)
    assert not verify_meta_signature("wrong", body, good)
    assert not verify_meta_signature("secret", body, None)
    assert not verify_meta_signature("secret", body, "")
    assert not verify_meta_signature("secret", body, good.replace("sha256=", ""))


def test_reason_in_whatsapp_and_sms():
    from app.core.channel import sms_text

    items = [
        make_item("2026-12-24", "closed", basis="PEERS"),
        make_item("2026-12-31", "10:00-14:00", basis="LAST_YEAR"),
    ]
    m = make_message(items)
    _n, params, _c = wt.wa_content(m, make_contact("en"), "en")
    assert "(Why: similar businesses are closed that day; same as last year)" in params[4]
    assert (
        "(Why: similar businesses are closed that day; same as last year)" in sms_text(m, make_contact("en"), "en")[0]
    )
    ask = make_message([make_item("2026-12-24", None, basis=None)])
    assert "Why" not in sms_text(ask, make_contact("en"), "en")[0]
