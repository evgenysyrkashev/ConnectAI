"""Minimal in-memory stand-in for the parts of google-cloud-firestore that FirestoreStore uses."""

from __future__ import annotations

import copy

from google.api_core.exceptions import AlreadyExists, NotFound


class Snap:
    def __init__(self, id_, data, reference=None):
        self.id, self._d, self.exists, self.reference = id_, data, data is not None, reference

    def to_dict(self):
        return copy.deepcopy(self._d)


class Query:
    def __init__(self, store, name, filters=(), orders=(), lim=None):
        self.store, self.name, self.filters, self.orders, self.lim = store, name, tuple(filters), tuple(orders), lim

    def where(self, *args, filter=None):
        f = filter or type("F", (), {"field_path": args[0], "op_string": args[1], "value": args[2]})
        return Query(self.store, self.name, (*self.filters, f), self.orders, self.lim)

    def order_by(self, field, direction="ASCENDING"):
        return Query(self.store, self.name, self.filters, (*self.orders, (field, direction)), self.lim)

    def limit(self, n):
        return Query(self.store, self.name, self.filters, self.orders, n)

    def stream(self):
        docs = [(i, d) for i, d in self.store.data.setdefault(self.name, {}).items()]
        for f in self.filters:
            docs = [(i, d) for i, d in docs if _match(d.get(f.field_path), f.op_string, f.value)]
        for field, direction in reversed(self.orders):
            docs = sorted(docs, key=lambda x: x[1].get(field) or "", reverse=direction == "DESCENDING")
        if self.lim is not None:
            docs = docs[: self.lim]
        return [Snap(i, copy.deepcopy(d), DocRef(self.store, self.name, i)) for i, d in docs]


def _match(actual, op, value):
    if op == "==":
        return actual == value
    if actual is None or type(actual) is not type(value):
        return False
    return {"<=": actual <= value, "<": actual < value, ">=": actual >= value, ">": actual > value}[op]


class DocRef:
    def __init__(self, store, col, id_):
        self.store, self.col, self.id = store, col, id_

    @property
    def _docs(self):
        return self.store.data.setdefault(self.col, {})

    def get(self, transaction=None):
        return Snap(self.id, copy.deepcopy(self._docs.get(self.id)))

    def set(self, d):
        self._docs[self.id] = copy.deepcopy(d)

    def create(self, d):
        if self.id in self._docs:
            raise AlreadyExists("exists")
        self._docs[self.id] = copy.deepcopy(d)

    def delete(self):
        self._docs.pop(self.id, None)

    def update(self, d):
        if self.id not in self._docs:
            raise NotFound("missing")
        self._docs[self.id].update(copy.deepcopy(d))


class Collection(Query):
    def document(self, id_):
        return DocRef(self.store, self.name, id_)


class Tx:
    def update(self, ref, d):
        ref.update(d)

    def set(self, ref, d):
        ref.set(d)


class FakeFirestore:
    def __init__(self):
        self.data: dict[str, dict] = {}

    def collection(self, name):
        return Collection(self, name)

    def transaction(self):
        return Tx()
