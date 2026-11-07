import pytest

from app.core.compose import fallback_intro, fallback_short, fallback_subject
from app.core.intro_check import IntroOut, check_intro, check_language
from app.core.prompts import FAKE_INTRO, FAKE_SHORT

LANGS = ("fi", "sv", "nb", "en")
TEMPLATES = ("holidays", "event", "stale_hours", "permission")


@pytest.mark.parametrize("lang", LANGS)
def test_fake_intro_language(lang):
    text = FAKE_INTRO[lang] + " " + FAKE_SHORT[lang]
    assert check_language(text, lang)
    for other in LANGS:
        if other != lang:
            assert not check_language(text, other), (lang, other)


def test_english_fails_for_finnish():
    assert not check_language(FAKE_INTRO["en"], "fi")


def good(lang="en") -> IntroOut:
    return IntroOut(subject="Opening hours for the holidays", intro=FAKE_INTRO[lang], short=FAKE_SHORT[lang])


def test_good_passes():
    for lang in LANGS:
        assert check_intro(good(lang), lang) == []


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("tpl", TEMPLATES)
def test_fallbacks_pass(lang, tpl):
    o = IntroOut(subject=fallback_subject(tpl, lang), intro=fallback_intro(tpl, lang), short=fallback_short(tpl, lang))
    assert check_intro(o, lang, tpl) == []


def test_rules():
    base = good()
    assert "Wrong language" in check_intro(good("fi"), "en")
    assert check_intro(base.model_copy(update={"short": "too short"}), "en")
    assert check_intro(base.model_copy(update={"short": base.short + "\nline"}), "en")
    assert check_intro(base.model_copy(update={"short": "x" * 161}), "en")
    assert check_intro(base.model_copy(update={"subject": "Hey"}), "en")
    assert check_intro(base.model_copy(update={"subject": "x" * 71}), "en")
    assert check_intro(base.model_copy(update={"subject": "OPENING HOURS NOW"}), "en")
    assert check_intro(base.model_copy(update={"intro": "short intro"}), "en")
    assert check_intro(base.model_copy(update={"intro": base.intro + " " + "x" * 500}), "en")
    assert check_intro(base.model_copy(update={"intro": base.intro + " see http://x.fi"}), "en")
    assert check_intro(base.model_copy(update={"intro": base.intro + " mail me@x.fi"}), "en")
    assert check_intro(base.model_copy(update={"intro": base.intro + " Open at 10:30 and more"}), "en")
    assert check_intro(base.model_copy(update={"intro": base.intro + " Open at 9 pm today"}), "en")
    assert check_intro(base.model_copy(update={"intro": base.intro + " On 24.12. it is open"}), "en")
    assert check_intro(base.model_copy(update={"intro": "Hello there! " + base.intro}), "en")
    assert check_intro(base.model_copy(update={"intro": "Hei! " + base.intro}), "en")


def test_permission_has_no_digits():
    o = good()
    assert check_intro(o, "en", "permission") == []
    bad = o.model_copy(update={"intro": o.intro + " You could get 30 % more visits."})
    assert any("digits" in p for p in check_intro(bad, "en", "permission"))
    assert not any("digits" in p for p in check_intro(bad, "en", "holidays"))
