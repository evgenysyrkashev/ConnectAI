"""Owner-facing strings in fi / sv / nb / en. Pure data; formatting lives in i18n.py.

# DECISION: split out of i18n.py to keep files readable. fi/sv/nb were written by the implementer:
# a native-speaker check is still needed.
"""

from __future__ import annotations

TEXT: dict[str, dict[str, str]] = {
    "en": {
        "greeting": "Hi {first_name},",
        "closed": "closed",
        "open_24h": "open 24 hours",
        "item_line": "• {day_name}, {weekday} {date}: Google now shows {shown}.",
        "item_line_group": "• {labels}: Google now shows {shown}.",
        "views_line": "Last year on {day_name}, your business was seen about {n} times on Google.",
        "suggest_line": "  We suggest: {suggested}. {reason}",
        "ask_line": "  What are your hours that day?",
        "reason_LAST_YEAR": "(Last year you were {last}.)",
        "reason_SHOPPING_CENTRE": "({mall} has published these hours.)",
        "reason_PEERS": "(Most similar businesses nearby are closed that day.)",
        "reason_LAST_EVENT": "(On earlier event nights you were {last}.)",
        "why_LAST_EVENT": "same as on earlier event nights",
        "why_LAST_YEAR": "same as last year",
        "why_SHOPPING_CENTRE": "the shopping centre has published these hours",
        "why_PEERS": "similar businesses are closed that day",
        "why_PATTERN": "similar businesses are closed that day",
        "why_PATTERN_HOURS": "similar businesses have shorter hours that day",
        "why_USER_EDIT": "Google users reported these hours last year",
        "why_label": "Why",
        "reason_OWN_EDIT": "(You set these hours for this day last time.)",
        "reason_OWN_APPROVED": "(You approved these hours for this day last time.)",
        "reason_USER_EDIT": "(Google users reported these hours for this day last year.)",
        "reason_PATTERN": "(Most similar businesses are closed that day.)",
        "reason_PATTERN_HOURS": "(Similar businesses usually have shorter hours that day.)",
        "reason_REVIEWS": "(Customers have mentioned that you were closed on this day.)",
        "instructions_dates": (
            'Just reply to this email:\n  • "OK" – approve the suggestions\n  • "No thanks" – keep everything as it is\n'
            '  • or write your own hours, e.g. "{example}"'
        ),
        "instructions_ask": 'Just reply to this email with your hours, e.g. "{example}", or "as usual" if nothing changes.',
        "weekly_header": "These are the opening hours Google shows for you now:",
        "weekly_line": "  {weekday}: {hours}",
        "instructions_weekly": (
            'Just reply "OK" if they are still correct, or write the correct hours, e.g. "Mon–Fri 9–17, Sat 10–14, Sun closed".'
        ),
        "inform_header": "Because you have allowed us to update holiday hours for you, we have already set these on Google:",
        "inform_line": "• {day_name}, {weekday} {date}: {hours}",
        "inform_line_group": "• {labels}: {hours}",
        "instructions_inform": "Nothing else is needed. If something is wrong, just reply with the correct hours.",
        "inform_revoke": 'Reply "MANUAL" if you would rather approve changes yourself.',
        "thanks": "Thank you!",
        "footer": "—\nYou receive this as a Connect customer. Reply STOP to stop these messages.",
        "fu_subject_prefix": "Re: ",
        "fu_applied_header": "Thanks {first_name}! We have updated your opening hours:",
        "fu_applied_line": "• {weekday} {date}: {hours}",
        "fu_visible_header": "The new hours will show up on:",
        "fu_visible_line": "  {publisher} – {eta}",
        "fu_declined": "Thanks {first_name}! We kept your opening hours as they are.",
        "fu_stopped": "You will not receive these messages anymore. Thank you!",
        "fu_offer_permission": (
            'Tip: reply "AUTO" and we will keep your holiday hours up to date automatically – you will always be informed.'
        ),
        "fu_perm_granted": "Thank you! Automatic updates are on. We have set:",
        "fu_perm_granted_end": ("We will always tell you what we change. Reply STOP at any time to turn this off."),
        "fu_perm_declined": "No problem – we will keep asking you before any change.",
        "fu_revoked": "Understood – from now on we will ask you before changing anything.",
        "eta_minutes": "in about {n} min",
        "eta_hours": "in about {n} h",
        "eta_days": "in about {n} days",
        "sim_ok": "OK, sounds good!",
        "sim_no": "No thanks, keep it as it is.",
        "sim_date_ok": "{date} ok",
        "sim_date_hours": "{date} {hours}",
        # --- permission request (10C) ---
        "perm_pending_header": "We have suggested hours for these days but have not heard from you:",
        "perm_pending_line": "• {day_name}, {weekday} {date}: Google now shows {shown} → we suggest {suggested}",
        "perm_pending_line_ask": "• {day_name}, {weekday} {date}: Google now shows {shown}",
        "perm_what_header": "What automatic updates mean:",
        "perm_what_1": "We set your holiday hours on Google and other services based on our suggestions.",
        "perm_what_2": "After every change we tell you exactly what we changed.",
        "perm_what_3": "You can correct a change or turn this off at any time – just reply.",
        "perm_benefits_header": "Why up-to-date hours matter:",
        "perm_benefit_1": "Customers see the right hours on Google, Apple Maps and other services – no closed doors.",
        "perm_benefit_2": "Listings with missing or outdated hours can drop out of “open now” searches.",
        "perm_benefit_3": "Fewer wasted trips mean happier customers and better reviews.",
        "perm_stats": (
            "Last year in the same period, your business was seen {views} times on Google, "
            "with {calls} calls and {actions} requests for directions or your website."
        ),
        "perm_instructions": (
            'Reply "YES" to allow automatic updates (we will set the hours above right away), '
            'or "NO" to keep approving each change yourself.'
        ),
        # --- fallbacks when the LLM text is unusable ---
        "fallback_subject_holidays": "Opening hours for the upcoming holidays",
        "fallback_subject_event": "Large event near your business",
        "fallback_subject_stale_hours": "Are your opening hours still correct?",
        "fallback_subject_permission": "May we keep your holiday hours up to date?",
        "fallback_intro_holidays": (
            "The holidays are coming, and we have prepared suggested opening hours for them. "
            "That way customers find the right hours on Google. Please check the suggestions below and tell us what you think."
        ),
        "fallback_intro_event": (
            "A large event takes place near your business soon. It may change your opening hours on that day. "
            "Please tell us below whether your hours are different."
        ),
        "fallback_intro_stale_hours": (
            "We would like to make sure that the regular opening hours shown on Google are still correct. "
            "It only takes a moment to check them below."
        ),
        "fallback_intro_permission": (
            "We could keep your holiday hours correct for you automatically, so you do not have to answer every time. "
            "You stay in control: you always hear from us after a change and can undo it."
        ),
        "fallback_short_holidays": "We have prepared suggested opening hours for the upcoming holidays.",
        "fallback_short_event": "A large event near your business may affect your opening hours.",
        "fallback_short_stale_hours": "Please check that your regular opening hours on Google are still correct.",
        "fallback_short_permission": "May we keep your holiday opening hours up to date automatically?",
        "fallback_footer": "Reply STOP to stop these messages.",
        "wa_prompt_edit": 'Write your hours, e.g. "24.12. closed, 31.12. 10–14".',
        "wa_prompt_edit_weekly": 'Write the correct hours, e.g. "Mon–Fri 9–17, Sat 10–14, Sun closed".',
        "wa_unsupported": "Sorry, I can only read text. Please tap a button or write your hours.",
        "wa_visibility_fallback": "Changes appear on Google within a day.",
        "sms_suggestion": (
            "{business}: {short} Google shows {shown}. We suggest {suggested}. Reply OK, NO or your own hours. STOP to opt out."
        ),
        "sms_question": (
            "{business}: {short} Google shows {shown}. Reply with your hours, or OK if as usual. STOP to opt out."
        ),
        "sms_check": "{business}: Google shows {week}. Reply OK if correct, or the right hours. STOP to opt out.",
        "sms_updated": "{business}: we updated your hours on Google: {applied}. Reply if something is wrong.",
        "sms_declined": "Thanks! We kept your opening hours as they are.",
        "sms_stopped": "You will not receive these messages anymore.",
    },
    "fi": {
        "greeting": "Hei {first_name},",
        "closed": "kiinni",
        "open_24h": "auki 24 tuntia",
        "item_line": "• {day_name}, {weekday} {date}: Google näyttää nyt: {shown}.",
        "item_line_group": "• {labels}: Google näyttää nyt: {shown}.",
        "views_line": "Viime vuonna päivänä {day_name} yrityksenne näkyi Googlessa noin {n} kertaa.",
        "suggest_line": "  Ehdotamme: {suggested}. {reason}",
        "ask_line": "  Mitkä ovat aukioloaikanne sinä päivänä?",
        "reason_LAST_YEAR": "(Viime vuonna olitte {last}.)",
        "reason_SHOPPING_CENTRE": "({mall} on julkaissut nämä ajat.)",
        "reason_PEERS": "(Useimmat vastaavat yritykset lähistöllä ovat silloin kiinni.)",
        "reason_LAST_EVENT": "(Aiempina tapahtumailtoina olitte {last}.)",
        "why_LAST_EVENT": "kuten aiempina tapahtumailtoina",
        "why_LAST_YEAR": "kuten viime vuonna",
        "why_SHOPPING_CENTRE": "kauppakeskus on julkaissut nämä ajat",
        "why_PEERS": "vastaavat yritykset ovat silloin kiinni",
        "why_PATTERN": "vastaavat yritykset ovat silloin kiinni",
        "why_PATTERN_HOURS": "vastaavilla yrityksillä on silloin lyhyemmät ajat",
        "why_USER_EDIT": "Googlen käyttäjät ilmoittivat nämä ajat viime vuonna",
        "why_label": "Syy",
        "reason_OWN_EDIT": "(Asetitte nämä ajat tälle päivälle viimeksi.)",
        "reason_OWN_APPROVED": "(Hyväksyitte nämä ajat tälle päivälle viimeksi.)",
        "reason_USER_EDIT": "(Googlen käyttäjät ilmoittivat viime vuonna nämä ajat tälle päivälle.)",
        "reason_PATTERN": "(Useimmat vastaavat yritykset ovat silloin kiinni.)",
        "reason_PATTERN_HOURS": "(Vastaavilla yrityksillä on silloin yleensä lyhyemmät aukioloajat.)",
        "reason_REVIEWS": "(Asiakkaat ovat maininneet, että olitte silloin kiinni.)",
        "instructions_dates": (
            'Vastatkaa vain tähän viestiin:\n  • "OK" – hyväksytte ehdotukset\n  • "Ei kiitos" – kaikki pysyy ennallaan\n'
            '  • tai kirjoittakaa omat aukioloaikanne, esim. "{example}"'
        ),
        "instructions_ask": (
            'Vastatkaa tähän viestiin aukioloajoillanne, esim. "{example}", tai "kuten yleensä", jos mikään ei muutu.'
        ),
        "weekly_header": "Google näyttää teille nyt nämä aukioloajat:",
        "weekly_line": "  {weekday}: {hours}",
        "instructions_weekly": (
            'Vastatkaa "OK", jos ajat ovat edelleen oikein, tai kirjoittakaa oikeat ajat, esim. "ma–pe 9–17, la 10–14, su kiinni".'
        ),
        "inform_header": "Koska olette sallineet loma-aikojen päivittämisen puolestanne, olemme jo asettaneet Googleen nämä ajat:",
        "inform_line": "• {day_name}, {weekday} {date}: {hours}",
        "inform_line_group": "• {labels}: {hours}",
        "instructions_inform": "Muuta ei tarvita. Jos jokin on väärin, vastatkaa oikeilla aukioloajoilla.",
        "inform_revoke": 'Vastatkaa "MANUAALINEN", jos haluatte mieluummin hyväksyä muutokset itse.',
        "thanks": "Kiitos!",
        "footer": "—\nSaatte tämän viestin Connect-asiakkaana. Vastatkaa STOP, jos ette halua näitä viestejä.",
        "fu_subject_prefix": "Re: ",
        "fu_applied_header": "Kiitos {first_name}! Olemme päivittäneet aukioloaikanne:",
        "fu_applied_line": "• {weekday} {date}: {hours}",
        "fu_visible_header": "Uudet ajat näkyvät seuraavissa palveluissa:",
        "fu_visible_line": "  {publisher} – {eta}",
        "fu_declined": "Kiitos {first_name}! Jätimme aukioloaikanne ennalleen.",
        "fu_stopped": "Ette saa enää näitä viestejä. Kiitos!",
        "fu_offer_permission": (
            'Vinkki: vastatkaa "AUTOMAATTINEN", niin pidämme loma-aikojenne aukioloajat ajan tasalla automaattisesti – '
            "saatte aina tiedon muutoksista."
        ),
        "fu_perm_granted": "Kiitos! Automaattiset päivitykset ovat nyt käytössä. Olemme asettaneet:",
        "fu_perm_granted_end": (
            "Kerromme aina, mitä olemme muuttaneet. Vastatkaa STOP milloin tahansa, jos haluatte poistaa tämän käytöstä."
        ),
        "fu_perm_declined": "Selvä – kysymme jatkossakin ennen jokaista muutosta.",
        "fu_revoked": "Selvä – jatkossa kysymme ennen kuin muutamme mitään.",
        "eta_minutes": "noin {n} min kuluttua",
        "eta_hours": "noin {n} h kuluttua",
        "eta_days": "noin {n} vuorokauden kuluttua",
        "sim_ok": "OK, sopii hyvin!",
        "sim_no": "Ei kiitos, jättäkää ennalleen.",
        "sim_date_ok": "{date} ok",
        "sim_date_hours": "{date} {hours}",
        "perm_pending_header": "Olemme ehdottaneet aikoja näille päiville, mutta emme ole kuulleet teistä:",
        "perm_pending_line": "• {day_name}, {weekday} {date}: Google näyttää nyt {shown} → ehdotamme {suggested}",
        "perm_pending_line_ask": "• {day_name}, {weekday} {date}: Google näyttää nyt {shown}",
        "perm_what_header": "Mitä automaattiset päivitykset tarkoittavat:",
        "perm_what_1": "Asetamme loma-aikojenne aukioloajat Googleen ja muihin palveluihin ehdotustemme mukaan.",
        "perm_what_2": "Jokaisen muutoksen jälkeen kerromme tarkasti, mitä muutimme.",
        "perm_what_3": "Voitte korjata muutoksen tai lopettaa tämän milloin tahansa – vastatkaa vain.",
        "perm_benefits_header": "Miksi ajantasaiset aukioloajat ovat tärkeitä:",
        "perm_benefit_1": "Asiakkaat näkevät oikeat ajat Googlessa, Apple Mapsissa ja muissa palveluissa – ei suljettuja ovia.",
        "perm_benefit_2": "Puutteelliset tai vanhentuneet ajat voivat pudottaa yrityksen pois ”auki nyt” -hauista.",
        "perm_benefit_3": "Vähemmän turhia käyntejä tarkoittaa tyytyväisempiä asiakkaita ja parempia arvosteluja.",
        "perm_stats": (
            "Viime vuonna samalla ajanjaksolla yrityksenne näkyi Googlessa {views} kertaa, "
            "ja siitä seurasi {calls} puhelua ja {actions} reittiohje- tai verkkosivupyyntöä."
        ),
        "perm_instructions": (
            'Vastatkaa "KYLLÄ", jos sallitte automaattiset päivitykset (asetamme yllä olevat ajat heti), '
            'tai "EI", jos haluatte jatkossakin hyväksyä jokaisen muutoksen itse.'
        ),
        "fallback_subject_holidays": "Aukioloajat tulevina juhlapyhinä",
        "fallback_subject_event": "Suuri tapahtuma yrityksenne lähellä",
        "fallback_subject_stale_hours": "Ovatko aukioloaikanne vielä oikein?",
        "fallback_subject_permission": "Saammeko pitää loma-aikojenne ajat ajan tasalla?",
        "fallback_intro_holidays": (
            "Juhlapyhät lähestyvät, ja olemme valmistelleet teille ehdotukset aukioloajoiksi. "
            "Näin asiakkaat löytävät oikeat ajat Googlesta. Tarkistakaa ehdotukset alta ja kertokaa, mitä mieltä olette."
        ),
        "fallback_intro_event": (
            "Yrityksenne lähellä järjestetään pian suuri tapahtuma, ja se voi vaikuttaa teidän aukioloaikoihinne. "
            "Kertokaa alla, ovatko ajat silloin erilaiset."
        ),
        "fallback_intro_stale_hours": (
            "Haluamme varmistaa, että Googlessa näkyvät säännölliset aukioloajat ovat edelleen oikein. "
            "Tarkistus vie vain hetken, ja ajat näet alta."
        ),
        "fallback_intro_permission": (
            "Voisimme pitää teidän loma-aikojenne aukioloajat ajan tasalla automaattisesti, jotta teidän ei tarvitse vastata joka kerta. "
            "Pysytte silti ohjat käsissä: kerromme aina muutoksen jälkeen, ja voitte perua sen."
        ),
        "fallback_short_holidays": "Olemme valmistelleet ehdotukset aukioloajoiksi tuleville juhlapyhille.",
        "fallback_short_event": "Yrityksenne lähellä on suuri tapahtuma, joka voi vaikuttaa aukioloaikoihin.",
        "fallback_short_stale_hours": "Tarkistattehan, että säännölliset aukioloaikanne Googlessa ovat edelleen oikein.",
        "fallback_short_permission": "Saammeko pitää loma-aikojenne aukioloajat ajan tasalla automaattisesti?",
        "fallback_footer": "Vastaa STOP, jos et halua näitä viestejä.",
        "wa_prompt_edit": 'Kirjoittakaa aukioloajat, esim. "24.12. kiinni, 31.12. 10–14".',
        "wa_prompt_edit_weekly": 'Kirjoittakaa oikeat ajat, esim. "ma–pe 9–17, la 10–14, su kiinni".',
        "wa_unsupported": "Valitettavasti luen vain tekstiä. Painakaa painiketta tai kirjoittakaa aukioloajat.",
        "wa_visibility_fallback": "Muutokset näkyvät Googlessa vuorokauden kuluessa.",
        "sms_suggestion": (
            "{business}: {short} Google näyttää {shown}. Ehdotamme {suggested}. Vastaa OK, EI tai omat ajat. STOP lopettaa viestit."
        ),
        "sms_question": (
            "{business}: {short} Google näyttää {shown}. Vastaa omilla ajoilla tai OK, jos kuten yleensä. STOP lopettaa viestit."
        ),
        "sms_check": "{business}: Google näyttää {week}. Vastaa OK, jos oikein, tai oikeat ajat. STOP lopettaa viestit.",
        "sms_updated": "{business}: päivitimme aukioloaikanne Googleen: {applied}. Vastaa, jos jokin on väärin.",
        "sms_declined": "Kiitos! Jätimme aukioloaikanne ennalleen.",
        "sms_stopped": "Ette saa enää näitä viestejä.",
    },
    "sv": {
        "greeting": "Hej {first_name},",
        "closed": "stängt",
        "open_24h": "öppet dygnet runt",
        "item_line": "• {day_name}, {weekday} {date}: Google visar nu: {shown}.",
        "item_line_group": "• {labels}: Google visar nu: {shown}.",
        "views_line": "Förra året på {day_name} sågs ert företag omkring {n} gånger på Google.",
        "suggest_line": "  Vi föreslår: {suggested}. {reason}",
        "ask_line": "  Vilka är era öppettider den dagen?",
        "reason_LAST_YEAR": "(Förra året hade ni {last}.)",
        "reason_SHOPPING_CENTRE": "({mall} har publicerat dessa tider.)",
        "reason_PEERS": "(De flesta liknande företag i närheten har stängt då.)",
        "reason_LAST_EVENT": "(Under tidigare evenemangskvällar hade ni {last}.)",
        "why_LAST_EVENT": "som på tidigare evenemangskvällar",
        "why_LAST_YEAR": "som förra året",
        "why_SHOPPING_CENTRE": "köpcentret har publicerat dessa tider",
        "why_PEERS": "liknande företag har stängt då",
        "why_PATTERN": "liknande företag har stängt då",
        "why_PATTERN_HOURS": "liknande företag har kortare tider då",
        "why_USER_EDIT": "Google-användare angav dessa tider förra året",
        "why_label": "Varför",
        "reason_OWN_EDIT": "(Ni angav dessa tider för dagen förra gången.)",
        "reason_OWN_APPROVED": "(Ni godkände dessa tider för dagen förra gången.)",
        "reason_USER_EDIT": "(Google-användare angav dessa tider för dagen förra året.)",
        "reason_PATTERN": "(De flesta liknande företag har stängt då.)",
        "reason_PATTERN_HOURS": "(Liknande företag har oftast kortare öppettider då.)",
        "reason_REVIEWS": "(Kunder har nämnt att ni hade stängt den dagen.)",
        "instructions_dates": (
            'Svara bara på detta mejl:\n  • "OK" – godkänn förslagen\n  • "Nej tack" – allt förblir som det är\n'
            '  • eller skriv era egna tider, t.ex. "{example}"'
        ),
        "instructions_ask": (
            'Svara bara på detta mejl med era öppettider, t.ex. "{example}", eller "som vanligt" om inget ändras.'
        ),
        "weekly_header": "Det här är de öppettider som Google visar för er nu:",
        "weekly_line": "  {weekday}: {hours}",
        "instructions_weekly": (
            'Svara "OK" om tiderna fortfarande stämmer, eller skriv de rätta tiderna, t.ex. "mån–fre 9–17, lör 10–14, sön stängt".'
        ),
        "inform_header": "Eftersom ni har gett oss tillåtelse att uppdatera helgtider åt er har vi redan lagt in dessa på Google:",
        "inform_line": "• {day_name}, {weekday} {date}: {hours}",
        "inform_line_group": "• {labels}: {hours}",
        "instructions_inform": "Inget mer behövs. Om något är fel, svara bara med de rätta tiderna.",
        "inform_revoke": 'Svara "MANUELL" om ni hellre godkänner ändringarna själva.',
        "thanks": "Tack!",
        "footer": "—\nDu får detta som Connect-kund. Svara STOPP för att sluta få dessa meddelanden.",
        "fu_subject_prefix": "Re: ",
        "fu_applied_header": "Tack {first_name}! Vi har uppdaterat era öppettider:",
        "fu_applied_line": "• {weekday} {date}: {hours}",
        "fu_visible_header": "De nya tiderna syns hos:",
        "fu_visible_line": "  {publisher} – {eta}",
        "fu_declined": "Tack {first_name}! Vi lät era öppettider vara som de är.",
        "fu_stopped": "Ni får inga fler sådana meddelanden. Tack!",
        "fu_offer_permission": (
            'Tips: svara "AUTOMATISK" så håller vi era helgtider uppdaterade automatiskt – ni blir alltid informerade.'
        ),
        "fu_perm_granted": "Tack! Automatiska uppdateringar är nu på. Vi har lagt in:",
        "fu_perm_granted_end": (
            "Vi berättar alltid vad vi ändrar. Svara STOPP när som helst om ni vill stänga av detta."
        ),
        "fu_perm_declined": "Inga problem – vi frågar er även fortsättningsvis före varje ändring.",
        "fu_revoked": "Uppfattat – från och med nu frågar vi er innan vi ändrar något.",
        "eta_minutes": "om cirka {n} min",
        "eta_hours": "om cirka {n} tim",
        "eta_days": "om cirka {n} dygn",
        "sim_ok": "OK, det låter bra!",
        "sim_no": "Nej tack, låt det vara som det är.",
        "sim_date_ok": "{date} ok",
        "sim_date_hours": "{date} {hours}",
        "perm_pending_header": "Vi har föreslagit tider för dessa dagar men har inte hört från er:",
        "perm_pending_line": "• {day_name}, {weekday} {date}: Google visar nu {shown} → vi föreslår {suggested}",
        "perm_pending_line_ask": "• {day_name}, {weekday} {date}: Google visar nu {shown}",
        "perm_what_header": "Vad automatiska uppdateringar innebär:",
        "perm_what_1": "Vi lägger in era helgtider på Google och andra tjänster utifrån våra förslag.",
        "perm_what_2": "Efter varje ändring berättar vi exakt vad vi har ändrat.",
        "perm_what_3": "Ni kan rätta en ändring eller stänga av detta när som helst – svara bara.",
        "perm_benefits_header": "Varför aktuella öppettider är viktiga:",
        "perm_benefit_1": "Kunderna ser rätt tider på Google, Apple Kartor och andra tjänster – inga stängda dörrar.",
        "perm_benefit_2": "Poster med saknade eller gamla tider kan falla bort ur sökningar på ”öppet nu”.",
        "perm_benefit_3": "Färre bortkastade resor ger nöjdare kunder och bättre omdömen.",
        "perm_stats": (
            "Förra året under samma period sågs ert företag {views} gånger på Google, "
            "med {calls} samtal och {actions} förfrågningar om vägbeskrivning eller er webbplats."
        ),
        "perm_instructions": (
            'Svara "JA" om ni tillåter automatiska uppdateringar (vi lägger in tiderna ovan direkt), '
            'eller "NEJ" om ni hellre fortsätter godkänna varje ändring själva.'
        ),
        "fallback_subject_holidays": "Öppettider inför de kommande helgerna",
        "fallback_subject_event": "Stort evenemang nära ert företag",
        "fallback_subject_stale_hours": "Stämmer era öppettider fortfarande?",
        "fallback_subject_permission": "Får vi hålla era helgtider uppdaterade?",
        "fallback_intro_holidays": (
            "Helgerna närmar sig och vi har tagit fram förslag på öppettider åt er. "
            "Då hittar kunderna rätt tider på Google. Titta på förslagen nedan och berätta vad ni tycker."
        ),
        "fallback_intro_event": (
            "Ett stort evenemang äger rum nära ert företag inom kort och det kan påverka era öppettider. "
            "Berätta nedan om tiderna är annorlunda då."
        ),
        "fallback_intro_stale_hours": (
            "Vi vill försäkra oss om att de ordinarie öppettiderna som visas på Google fortfarande stämmer. "
            "Det tar bara en stund och ni kan kontrollera tiderna nedan."
        ),
        "fallback_intro_permission": (
            "Vi kan hålla era helgtider korrekta åt er automatiskt, så att ni inte behöver svara varje gång. "
            "Ni har fortfarande kontrollen: ni får alltid besked efter en ändring och kan ångra den."
        ),
        "fallback_short_holidays": "Vi har tagit fram förslag på öppettider för de kommande helgerna.",
        "fallback_short_event": "Ett stort evenemang nära ert företag kan påverka era öppettider.",
        "fallback_short_stale_hours": "Kontrollera att era ordinarie öppettider på Google fortfarande stämmer.",
        "fallback_short_permission": "Får vi hålla era helgtider uppdaterade automatiskt?",
        "fallback_footer": "Svara STOPP för att sluta få dessa meddelanden.",
        "wa_prompt_edit": 'Skriv era tider, t.ex. "24/12 stängt, 31/12 10–14".',
        "wa_prompt_edit_weekly": 'Skriv de rätta tiderna, t.ex. "mån–fre 9–17, lör 10–14, sön stängt".',
        "wa_unsupported": "Tyvärr kan jag bara läsa text. Tryck på en knapp eller skriv era tider.",
        "wa_visibility_fallback": "Ändringar syns på Google inom ett dygn.",
        "sms_suggestion": (
            "{business}: {short} Google visar {shown}. Vi föreslår {suggested}. Svara OK, NEJ eller egna tider. STOPP avslutar."
        ),
        "sms_question": (
            "{business}: {short} Google visar {shown}. Svara med era tider, eller OK om som vanligt. STOPP avslutar."
        ),
        "sms_check": "{business}: Google visar {week}. Svara OK om det stämmer, eller de rätta tiderna. STOPP avslutar.",
        "sms_updated": "{business}: vi har uppdaterat era öppettider på Google: {applied}. Svara om något är fel.",
        "sms_declined": "Tack! Vi lät era öppettider vara som de är.",
        "sms_stopped": "Ni får inga fler sådana meddelanden.",
    },
    "nb": {
        "greeting": "Hei {first_name},",
        "closed": "stengt",
        "open_24h": "åpent hele døgnet",
        "item_line": "• {day_name}, {weekday} {date}: Google viser nå: {shown}.",
        "item_line_group": "• {labels}: Google viser nå: {shown}.",
        "views_line": "I fjor på {day_name} ble bedriften deres vist omtrent {n} ganger på Google.",
        "suggest_line": "  Vi foreslår: {suggested}. {reason}",
        "ask_line": "  Hva er åpningstidene deres den dagen?",
        "reason_LAST_YEAR": "(I fjor hadde dere {last}.)",
        "reason_SHOPPING_CENTRE": "({mall} har publisert disse tidene.)",
        "reason_PEERS": "(De fleste lignende bedrifter i nærheten har stengt da.)",
        "reason_LAST_EVENT": "(På tidligere arrangementskvelder hadde dere {last}.)",
        "why_LAST_EVENT": "som på tidligere arrangementskvelder",
        "why_LAST_YEAR": "som i fjor",
        "why_SHOPPING_CENTRE": "kjøpesenteret har publisert disse tidene",
        "why_PEERS": "lignende bedrifter har stengt da",
        "why_PATTERN": "lignende bedrifter har stengt da",
        "why_PATTERN_HOURS": "lignende bedrifter har kortere tider da",
        "why_USER_EDIT": "Google-brukere oppga disse tidene i fjor",
        "why_label": "Hvorfor",
        "reason_OWN_EDIT": "(Dere satte disse tidene for denne dagen sist.)",
        "reason_OWN_APPROVED": "(Dere godkjente disse tidene for denne dagen sist.)",
        "reason_USER_EDIT": "(Google-brukere oppga disse tidene for denne dagen i fjor.)",
        "reason_PATTERN": "(De fleste lignende bedrifter har stengt da.)",
        "reason_PATTERN_HOURS": "(Lignende bedrifter har vanligvis kortere åpningstider da.)",
        "reason_REVIEWS": "(Kunder har nevnt at dere hadde stengt denne dagen.)",
        "instructions_dates": (
            'Bare svar på denne e-posten:\n  • "OK" – godkjenn forslagene\n  • "Nei takk" – alt blir som det er\n'
            '  • eller skriv egne tider, f.eks. "{example}"'
        ),
        "instructions_ask": (
            'Bare svar på denne e-posten med åpningstidene deres, f.eks. "{example}", eller "som vanlig" hvis ingenting endres.'
        ),
        "weekly_header": "Dette er åpningstidene Google viser for dere nå:",
        "weekly_line": "  {weekday}: {hours}",
        "instructions_weekly": (
            'Svar "OK" hvis tidene fortsatt stemmer, eller skriv de riktige tidene, f.eks. "man–fre 9–17, lør 10–14, søn stengt".'
        ),
        "inform_header": "Fordi dere har gitt oss lov til å oppdatere helligdagstider for dere, har vi allerede lagt inn disse på Google:",
        "inform_line": "• {day_name}, {weekday} {date}: {hours}",
        "inform_line_group": "• {labels}: {hours}",
        "instructions_inform": "Ingenting mer trengs. Hvis noe er feil, svar bare med de riktige tidene.",
        "inform_revoke": 'Svar "MANUELT" hvis dere heller vil godkjenne endringer selv.',
        "thanks": "Takk!",
        "footer": "—\nDu får dette som Connect-kunde. Svar STOPP for å slutte å få disse meldingene.",
        "fu_subject_prefix": "Re: ",
        "fu_applied_header": "Takk {first_name}! Vi har oppdatert åpningstidene deres:",
        "fu_applied_line": "• {weekday} {date}: {hours}",
        "fu_visible_header": "De nye tidene vises hos:",
        "fu_visible_line": "  {publisher} – {eta}",
        "fu_declined": "Takk {first_name}! Vi lot åpningstidene deres stå som de er.",
        "fu_stopped": "Dere får ikke flere slike meldinger. Takk!",
        "fu_offer_permission": (
            'Tips: svar "AUTOMATISK" så holder vi helligdagstidene deres oppdatert automatisk – dere blir alltid informert.'
        ),
        "fu_perm_granted": "Takk! Automatiske oppdateringer er nå slått på. Vi har lagt inn:",
        "fu_perm_granted_end": (
            "Vi forteller alltid hva vi endrer. Svar STOPP når som helst hvis dere vil slå dette av."
        ),
        "fu_perm_declined": "Ikke noe problem – vi spør dere også fremover før hver endring.",
        "fu_revoked": "Greit – fra nå av spør vi dere før vi endrer noe.",
        "eta_minutes": "om omtrent {n} min",
        "eta_hours": "om omtrent {n} t",
        "eta_days": "om omtrent {n} døgn",
        "sim_ok": "OK, det høres bra ut!",
        "sim_no": "Nei takk, la det være som det er.",
        "sim_date_ok": "{date} ok",
        "sim_date_hours": "{date} {hours}",
        "perm_pending_header": "Vi har foreslått tider for disse dagene, men har ikke hørt fra dere:",
        "perm_pending_line": "• {day_name}, {weekday} {date}: Google viser nå {shown} → vi foreslår {suggested}",
        "perm_pending_line_ask": "• {day_name}, {weekday} {date}: Google viser nå {shown}",
        "perm_what_header": "Hva automatiske oppdateringer betyr:",
        "perm_what_1": "Vi legger inn helligdagstidene deres på Google og andre tjenester ut fra forslagene våre.",
        "perm_what_2": "Etter hver endring forteller vi nøyaktig hva vi har endret.",
        "perm_what_3": "Dere kan rette en endring eller slå dette av når som helst – bare svar.",
        "perm_benefits_header": "Hvorfor oppdaterte åpningstider er viktige:",
        "perm_benefit_1": "Kundene ser riktige tider på Google, Apple Kart og andre tjenester – ingen stengte dører.",
        "perm_benefit_2": "Oppføringer med manglende eller utdaterte tider kan falle ut av søk på «åpent nå».",
        "perm_benefit_3": "Færre bortkastede turer gir fornøyde kunder og bedre omtaler.",
        "perm_stats": (
            "I fjor i samme periode ble bedriften deres vist {views} ganger på Google, "
            "med {calls} anrop og {actions} forespørsler om veibeskrivelse eller nettsiden deres."
        ),
        "perm_instructions": (
            'Svar "JA" hvis dere tillater automatiske oppdateringer (vi legger inn tidene over med en gang), '
            'eller "NEI" hvis dere heller vil fortsette å godkjenne hver endring selv.'
        ),
        "fallback_subject_holidays": "Åpningstider for de kommende helligdagene",
        "fallback_subject_event": "Stort arrangement nær bedriften deres",
        "fallback_subject_stale_hours": "Stemmer åpningstidene deres fortsatt?",
        "fallback_subject_permission": "Kan vi holde helligdagstidene deres oppdatert?",
        "fallback_intro_holidays": (
            "Høytidene nærmer seg, og vi har laget forslag til åpningstider for dere. "
            "Da finner kundene riktige tider på Google. Se på forslagene nedenfor og fortell oss hva dere mener."
        ),
        "fallback_intro_event": (
            "Et stort arrangement finner snart sted nær bedriften deres, og det kan påvirke åpningstidene deres. "
            "Fortell oss nedenfor om tidene er annerledes da."
        ),
        "fallback_intro_stale_hours": (
            "Vi vil forsikre oss om at de vanlige åpningstidene som vises på Google fortsatt stemmer. "
            "Det tar bare et øyeblikk å sjekke dem nedenfor."
        ),
        "fallback_intro_permission": (
            "Vi kan holde helligdagstidene deres riktige automatisk, slik at dere ikke må svare hver gang. "
            "Dere har fortsatt kontrollen: dere hører alltid fra oss etter en endring og kan angre den."
        ),
        "fallback_short_holidays": "Vi har laget forslag til åpningstider for de kommende helligdagene.",
        "fallback_short_event": "Et stort arrangement nær bedriften deres kan påvirke åpningstidene.",
        "fallback_short_stale_hours": "Sjekk at de vanlige åpningstidene deres på Google fortsatt stemmer.",
        "fallback_short_permission": "Kan vi holde helligdagstidene deres oppdatert automatisk?",
        "fallback_footer": "Svar STOPP for å slutte å få disse meldingene.",
        "wa_prompt_edit": 'Skriv tidene deres, f.eks. "24.12. stengt, 31.12. 10–14".',
        "wa_prompt_edit_weekly": 'Skriv de riktige tidene, f.eks. "man–fre 9–17, lør 10–14, søn stengt".',
        "wa_unsupported": "Beklager, jeg kan bare lese tekst. Trykk på en knapp eller skriv tidene deres.",
        "wa_visibility_fallback": "Endringer vises på Google i løpet av et døgn.",
        "sms_suggestion": (
            "{business}: {short} Google viser {shown}. Vi foreslår {suggested}. Svar OK, NEI eller egne tider. STOPP avslutter."
        ),
        "sms_question": (
            "{business}: {short} Google viser {shown}. Svar med tidene deres, eller OK hvis som vanlig. STOPP avslutter."
        ),
        "sms_check": "{business}: Google viser {week}. Svar OK hvis det stemmer, eller de riktige tidene. STOPP avslutter.",
        "sms_updated": "{business}: vi har oppdatert åpningstidene deres på Google: {applied}. Svar hvis noe er feil.",
        "sms_declined": "Takk! Vi lot åpningstidene deres stå som de er.",
        "sms_stopped": "Dere får ikke flere slike meldinger.",
    },
}

WEEKDAY: dict[str, list[str]] = {
    "fi": ["maanantai", "tiistai", "keskiviikko", "torstai", "perjantai", "lauantai", "sunnuntai"],
    "sv": ["måndag", "tisdag", "onsdag", "torsdag", "fredag", "lördag", "söndag"],
    "nb": ["mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"],
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
}

WEEKDAY_SHORT: dict[str, list[str]] = {
    "fi": ["ma", "ti", "ke", "to", "pe", "la", "su"],
    "sv": ["mån", "tis", "ons", "tor", "fre", "lör", "sön"],
    "nb": ["man", "tir", "ons", "tor", "fre", "lør", "søn"],
    "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
}
