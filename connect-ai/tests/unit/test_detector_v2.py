"""DetectorV2 decision order on hand-built features; aliases; model hygiene."""

from __future__ import annotations

import re
from pathlib import Path

from app.core.compose import reason_for
from app.detect.aliases import aliases, mentions_closed_on
from app.detect.detector import MODEL_PATH, decide, load_model

MODEL = {
    "priors": {
        "*|*|XMAS_EVE": {"n": 100, "p_closed": 0.5, "p_regular": 0.3, "p_special": 0.2, "special_hours": "09:00-14:00"}
    },
    "source_reliability": {"mall_hours": 0.9, "last_year_exception": 0.9, "last_year_user_edit|EXPIRED": 0.85},
    "lr": {
        "review_closed": {"true": 3.0, "false": 0.8},
        "peer_bucket": {"none": 1.0, "<0.2": 0.2, "0.2-0.5": 0.8, "0.5-0.8": 2.0, ">=0.8": 8.0},
        "no_history": {"true": 1.0, "false": 1.0},
    },
    "thresholds": {"closed_min_p": 0.8, "special_min_p": 0.9, "min_source_reliability": 0.8},
}


def feats(**kw):
    f = {
        "country": "FI",
        "segment": "cafe",
        "day_key": "XMAS_EVE",
        "shown": "08:00-20:00",
        "shown_source": "regular",
        "regular": "08:00-20:00",
        "already_entered": False,
        "flag": False,
        "no_history": False,
        "mall_hours": None,
        "mall": None,
        "last_year_exception": None,
        "last_year_date": None,
        "last_year_user_edit": None,
        "last_year_user_edit_status": None,
        "review_closed": False,
        "peer_closed": None,
        "peer_n": None,
        "peer_special": None,
        "peer_entered_closed": None,
        "peer_bucket": "none",
    }
    f.update(kw)
    return f


def test_flag_first():
    assert decide(feats(flag=True, already_entered=True, mall_hours="closed"), MODEL)["action"] == "FLAG"


def test_already_entered_is_quiet():
    r = decide(feats(already_entered=True, last_year_exception="closed"), MODEL)
    assert (r["action"], r["basis"]) == ("NO_ACTION", "ALREADY_ENTERED")


def test_copy_source_priority_and_equal_to_shown():
    r = decide(feats(mall_hours="10:00-16:00", last_year_exception="closed"), MODEL)
    assert (r["action"], r["hours"], r["basis"]) == ("SUGGEST", "10:00-16:00", "SHOPPING_CENTRE")
    assert decide(feats(last_year_exception="08:00-20:00"), MODEL)["action"] == "NO_ACTION"


def test_unreliable_source_is_skipped():
    m = {**MODEL, "source_reliability": {"last_year_user_edit|EXPIRED": 0.5}}
    r = decide(feats(last_year_user_edit="closed", last_year_user_edit_status="EXPIRED"), m)
    assert r["action"] == "NO_ACTION"


def test_user_edit_source():
    r = decide(feats(last_year_user_edit="closed", last_year_user_edit_status="EXPIRED"), MODEL)
    assert (r["action"], r["basis"]) == ("SUGGEST", "USER_EDIT")


def test_closed_probability_needs_peers_who_entered_closed():
    f = feats(peer_closed=0.9, peer_n=50, peer_bucket=">=0.8", peer_entered_closed=0.5)
    r = decide(f, MODEL)
    assert (r["action"], r["hours"], r["basis"]) == ("SUGGEST", "closed", "PEERS")
    assert r["signals"]
    assert decide({**f, "peer_entered_closed": 0.05}, MODEL)["action"] == "NO_ACTION"
    assert decide({**f, "shown": "closed"}, MODEL)["action"] == "NO_ACTION"


def test_review_signal_adds_reason_without_quoting():
    f = feats(peer_closed=0.6, peer_n=50, peer_bucket="0.5-0.8", peer_entered_closed=0.5, review_closed=True)
    r = decide(f, MODEL)
    assert r["action"] == "SUGGEST" and r["evidence"]["review_closed"]
    text = reason_for(r["basis"], r["evidence"], "en")
    assert "Customers have mentioned" in text and "Most similar" in text


def test_reason_lines_exist_in_every_language():
    for lang in ("fi", "sv", "nb", "en"):
        for basis in ("USER_EDIT", "PATTERN", "PATTERN_HOURS"):
            assert reason_for(basis, {}, lang).startswith("(")


def test_pattern_hours_only_when_sure():
    f = feats()
    assert decide(f, MODEL)["action"] == "NO_ACTION"
    m = {**MODEL, "priors": {"*|*|XMAS_EVE": {**MODEL["priors"]["*|*|XMAS_EVE"], "p_special": 0.95, "p_closed": 0.01}}}
    r = decide(f, m)
    assert (r["action"], r["hours"], r["basis"]) == ("SUGGEST", "09:00-14:00", "PATTERN_HOURS")


def test_aliases_cover_every_day_key_in_every_language():
    a = aliases()
    for key in a:
        assert a[key]
    assert mentions_closed_on("Oli kiinni jouluaattona", "XMAS_EVE")
    assert mentions_closed_on("Closed on Christmas Eve!", "XMAS_EVE")
    assert not mentions_closed_on("Great coffee on Christmas Eve", "XMAS_EVE")


def test_model_has_no_entity_ids_and_is_small():
    raw = Path(MODEL_PATH).read_text(encoding="utf-8")
    assert len(raw) < 1_000_000
    assert not re.search(r"\b(FI|SE|NO)-D?\d", raw)
    m = load_model()
    assert {"priors", "source_reliability", "lr", "thresholds"} <= set(m)
