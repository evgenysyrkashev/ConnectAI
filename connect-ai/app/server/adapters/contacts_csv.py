"""CRM stand-in: data/customer_contacts.csv, read once."""

from __future__ import annotations

import csv

from app import kit
from app.core.models import Contact

LANGS = ("fi", "sv", "nb", "en")


class CsvContacts:
    def __init__(self, path: str | None = None):
        self._c: dict[str, Contact] = {}
        self._raw: dict[str, str] = {}
        with open(path or kit.data_path("data", "customer_contacts.csv"), encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        for r in rows:
            raw = (r["preferred_language"] or "").strip().lower()
            self._raw[r["entity_id"]] = raw
            self._c[r["entity_id"]] = Contact(
                entity_id=r["entity_id"],
                first_name=r["contact_first_name"],
                preferred_channel=r["preferred_channel"],
                language=raw if raw in LANGS else "en",
                email=r["email"].strip().lower(),
                mobile=r["mobile"],
                best_contact_window=r["best_contact_window"],
                standing_permission=r["standing_permission_holidays"] == "1",
                opted_out=r["opted_out_of_suggestions"] == "1",
            )

    def get(self, eid: str) -> Contact | None:
        c = self._c.get(eid)
        return c.model_copy() if c else None

    def raw_language(self, eid: str) -> str | None:
        return self._raw.get(eid)
