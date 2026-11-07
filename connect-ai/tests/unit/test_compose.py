from app.core import compose
from tests.conftest import make_contact, make_item, make_message

SENDER = "ConnectAI (demo)"
LISTINGS = [
    {"status": "LIVE", "publisherId": "APPLE", "typicalUpdateSpeedSeconds": 172800},
    {"status": "LIVE", "publisherId": "GOOGLEMYBUSINESS", "typicalUpdateSpeedSeconds": 120},
    {"status": "WAITING_ON_PUBLISHER", "publisherId": "BING", "typicalUpdateSpeedSeconds": 60},
]


def test_reason_for():
    assert compose.reason_for("LAST_YEAR", {"last_year_hours": "closed"}, "fi") == "(Viime vuonna olitte kiinni.)"
    assert compose.reason_for("LAST_YEAR", {"last_year_hours": "10:00-14:00"}, "en") == "(Last year you were 10–14.)"
    assert compose.reason_for("SHOPPING_CENTRE", {"mall": "Itis"}, "sv") == "(Itis har publicerat dessa tider.)"
    assert "closed that day" in compose.reason_for("PEERS", None, "en")
    assert (
        compose.reason_for("LAST_EVENT", {"hours": "closed"}, "nb")
        == "(På tidligere arrangementskvelder hadde dere stengt.)"
    )
    assert compose.reason_for("CLOSED_SIGNALS", {}, "en") == "" and compose.reason_for(None, None, "en") == ""


def test_ask_body_fi():
    items = [
        make_item("2026-12-24", "closed", reason="(Viime vuonna olitte kiinni.)"),
        make_item("2026-12-31", None, basis=None),
    ]
    body = compose.compose_body(make_message(items), make_contact("fi"), "fi", SENDER)
    assert body.startswith("Hei Maria,\n\nIntro text goes here for the owner.\n\n")
    assert (
        "• Jouluaatto, torstai 24.12.: Google näyttää nyt: 8–20.\n  Ehdotamme: kiinni. (Viime vuonna olitte kiinni.)"
        in body
    )
    assert "  Mitkä ovat aukioloaikanne sinä päivänä?" in body
    assert '"OK" – hyväksytte ehdotukset' in body and '"24.12. 10–14"' in body
    assert body.rstrip().endswith("Vastatkaa STOP, jos ette halua näitä viestejä.")
    assert f"Kiitos!\n{SENDER}\n\n—" in body


def test_ask_body_en_and_no_suggestions():
    body = compose.compose_body(make_message(), make_contact("en"), "en", SENDER)
    assert "• Jouluaatto, Thursday 24 Dec: Google now shows 8–20.\n  We suggest: closed." in body
    assert 'e.g. "24 Dec 10–14"' in body and '"No thanks" – keep everything as it is' in body
    only_ask = make_message([make_item("2026-12-24", None, basis=None)])
    b2 = compose.compose_body(only_ask, make_contact("en"), "en", SENDER)
    assert "Just reply to this email with your hours" in b2 and '"No thanks"' not in b2


def test_views_line():
    it = make_item()
    assert compose.round_2sf(1234) == 1200 and compose.round_2sf(340) == 340 and compose.round_2sf(87) == 87
    assert compose.round_2sf(34567) == 34000
    assert compose.views_line(it, 340, "en", 20) == (
        "Last year on Jouluaatto, your business was seen about 340 times on Google."
    )
    assert compose.views_line(it, 12, "en", 20) is None and compose.views_line(it, None, "en", 20) is None
    line = compose.views_line(it, 1234, "fi", 20)
    assert "1 200" in line
    body = compose.compose_body(make_message(), make_contact("en"), "en", SENDER, views=line)
    assert line in body


def test_inform_body():
    en = compose.compose_body(make_message(mode="inform"), make_contact("en"), "en", SENDER)
    assert "we have already set these on Google:" in en
    assert "• Jouluaatto, Thursday 24 Dec: closed\n• Jouluaatto, Thursday 31 Dec: 10–14" in en
    assert 'Reply "MANUAL"' in en and "Google now shows" not in en
    fi = compose.compose_body(make_message(mode="inform"), make_contact("fi"), "fi", SENDER)
    assert "• Jouluaatto, torstai 24.12.: kiinni" in fi and "MANUAALINEN" in fi


def test_weekly_body():
    m = make_message(kind="weekly")
    fi = compose.compose_body(m, make_contact("fi"), "fi", SENDER)
    assert "  maanantai: 9–17" in fi and "  sunnuntai: kiinni" in fi and "ma–pe 9–17" in fi
    en = compose.compose_body(m, make_contact("en"), "en", SENDER)
    assert "  Saturday: closed" in en and "Mon–Fri 9–17" in en


def test_permission_body():
    m = make_message(template_id="permission", kind="permission")
    b = compose.compose_permission_body(m, make_contact("en"), "en", SENDER, {"views": 1234, "calls": 5, "actions": 7})
    assert "→ we suggest closed" in b and "What automatic updates mean:" in b
    assert "seen 1,234 times on Google, with 5 calls and 7 requests" in b
    assert 'Reply "YES"' in b
    assert "seen" not in compose.compose_permission_body(m, make_contact("en"), "en", SENDER, {"views": 49})
    assert "seen" not in compose.compose_permission_body(m, make_contact("en"), "en", SENDER, None)


def test_followup_applied():
    c = make_contact("sv")
    t = compose.compose_followup_applied(c, "sv", [("2026-12-24", "closed")], LISTINGS, None)
    assert t.startswith("Tack Maria! Vi har uppdaterat era öppettider:\n• torsdag 24/12: stängt")
    # only LIVE, sorted by speed, publisher names localized
    assert t.index("Google Sök och Maps – om cirka 2 min") < t.index("Apple Kartor – om cirka 2 dygn")
    assert "Bing" not in t and "AUTOMATISK" not in t
    assert "AUTOMATISK" in compose.compose_followup_applied(
        c, "sv", [("2026-12-24", "closed")], [], None, offer_permission=True
    )


def test_followup_applied_weekly_and_limit():
    t = compose.compose_followup_applied(make_contact("en"), "en", [("monday", "09:00-17:00")], [], None, weekly=True)
    assert "• Monday: 9–17" in t and "The new hours" not in t
    many = [{"status": "LIVE", "publisherId": f"P{i}", "typicalUpdateSpeedSeconds": i} for i in range(9)]
    t2 = compose.compose_followup_applied(make_contact("en"), "en", [("2026-12-24", "closed")], many, None)
    assert t2.count("  P") == 5


def test_other_followups():
    c = make_contact("fi")
    assert "Jätimme aukioloaikanne ennalleen." in compose.compose_followup_declined(c, "fi")
    assert compose.compose_followup_stopped("en") == "You will not receive these messages anymore. Thank you!"
    g = compose.compose_followup_permission_granted(c, "en", [("2026-12-24", "closed")], LISTINGS)
    assert "Automatic updates are on" in g and "Thursday 24 Dec: closed" in g and "Reply STOP" in g
    assert "No problem" in compose.compose_followup_permission_declined("en")
    assert compose.compose_followup_revoked("en")


def test_sim_reply():
    acc = {"date": "2026-12-24", "decision": "ACCEPTED", "final_hours": "closed", "shown_hours": "08:00-20:00"}
    rej = {"date": "2026-12-31", "decision": "REJECTED", "final_hours": "08:00-20:00", "shown_hours": "08:00-20:00"}
    edit = {"date": "2027-01-01", "decision": "EDITED", "final_hours": "10:00-14:00", "shown_hours": "08:00-20:00"}
    assert compose.compose_sim_reply([acc, acc], "en") == "OK, sounds good!"
    assert compose.compose_sim_reply([rej], "en") == "No thanks, keep it as it is."
    assert compose.compose_sim_reply([acc, rej, edit], "en") == "24 Dec ok, 31 Dec 8–20, 1 Jan 10–14"
    assert compose.compose_sim_reply([acc, edit], "fi") == "24.12. ok, 1.1. 10–14"


def test_same_hours_dates_share_one_line():
    items = [
        make_item("2026-12-24", "closed", reason="(r)"),
        make_item("2026-12-25", "closed", reason="(r)"),
        make_item("2026-12-31", "10:00-14:00", reason=""),
    ]
    body = compose.compose_body(make_message(items), make_contact("en"), "en", SENDER)
    assert body.count("Google now shows") == 2
    assert "Thursday 24 Dec; " in body and "Friday 25 Dec: Google now shows" in body
