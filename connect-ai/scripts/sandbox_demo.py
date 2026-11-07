"""Put the Yext sandbox demo entity into a known demo state, and restore it afterwards.

    python -m scripts.sandbox_demo show                          # print the entity's category and hours
    python -m scripts.sandbox_demo seed --category P#### --yes   # snapshot the original, then copy name + hours of the kit entity
    python -m scripts.sandbox_demo seed --hours-only --yes       # snapshot, then copy only the kit entity's weekly hours
    python -m scripts.sandbox_demo rename --name "..." --yes     # snapshot the original, then change only the name
    python -m scripts.sandbox_demo restore --yes                 # put the snapshot back

Settings come from `.env` / the environment: YEXT_SANDBOX_API_KEY, YEXT_SANDBOX_BASE_URL (optional) and
YEXT_SANDBOX_ENTITY_MAP (the first entry is used, or pass --entity LOCAL_ID). The local id must be a kit entity
(for example FI-D0001=SinceAI14): its name and weekly hours are copied into the sandbox entity, so the sandbox
matches what the detector expects.

The snapshot (`outputs/sandbox_snapshot_<id>.json`, git-ignored) holds only the `name`, `hours` and `categories` fields.
It is never overwritten unless you pass --force, so a second `seed` cannot lose the true original.
The API key is never printed.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from pathlib import Path

from app import kit
from app.server.adapters.yext_http import HttpYext
from app.server.config import read_dotenv
from app.server.services.sandbox import entity_map

FIELDS = ("name", "hours", "categories")
OUT = Path(__file__).resolve().parent.parent / "outputs"


def _kit_entity(local_id: str) -> dict:
    with open(kit.data_path("data", "entities.json"), encoding="utf-8") as f:
        for e in json.load(f)["response"]["entities"]:
            if e["meta"]["id"] == local_id:
                return e
    sys.exit(f"{local_id} is not a kit entity; map a kit id such as FI-D0001 to the sandbox entity")


def _client(env: dict[str, str], entity: str | None) -> tuple[HttpYext, str, str]:
    key = env.get("YEXT_SANDBOX_API_KEY")
    if not key:
        sys.exit("YEXT_SANDBOX_API_KEY is not set")
    mapping = entity_map(env.get("YEXT_SANDBOX_ENTITY_MAP"))
    if not mapping:
        sys.exit("YEXT_SANDBOX_ENTITY_MAP is empty (format LOCAL=SANDBOX)")
    local = entity or next(iter(mapping))
    if local not in mapping:
        sys.exit(f"{local} is not in YEXT_SANDBOX_ENTITY_MAP")
    base = env.get("YEXT_SANDBOX_BASE_URL") or "https://sbx-api.yextapis.com"
    return HttpYext(base, key), local, mapping[local]


def _state(ent: dict) -> dict:
    return {f: copy.deepcopy(ent.get(f)) for f in FIELDS}  # None = the field is absent


def _read(client: HttpYext, sid: str) -> dict:
    client._cache.pop(sid, None)  # never show a cached copy
    return _state(client.get_entity(sid))


def _write(client: HttpYext, sid: str, state: dict, fields: tuple[str, ...] = FIELDS) -> None:
    # PUT only the managed fields; None asks Yext to clear the field.
    client._req("PUT", f"entities/{sid}", body={f: state.get(f) for f in fields if f in state})
    client._cache.pop(sid, None)


def _snapshot_path(sid: str) -> Path:
    return OUT / f"sandbox_snapshot_{sid}.json"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["show", "seed", "rename", "restore"])
    ap.add_argument("--entity", help="local id from YEXT_SANDBOX_ENTITY_MAP (default: the first one)")
    ap.add_argument("--category", help="Fonecta category code for a cafe, e.g. P1234 (look it up in the Yext UI)")
    ap.add_argument(
        "--hours-only", action="store_true", help="seed: change only the weekly hours (keep name and category)"
    )
    ap.add_argument("--name", help="new business name for the rename command")
    ap.add_argument("--yes", action="store_true", help="confirm that the sandbox entity is changed")
    ap.add_argument("--force", action="store_true", help="overwrite an existing snapshot")
    a = ap.parse_args(argv)

    env = {**read_dotenv(), **os.environ}
    client, local, sid = _client(env, a.entity)
    snap = _snapshot_path(sid)
    current = _read(client, sid)

    if a.command == "show":
        print(json.dumps(current, indent=2, ensure_ascii=False))
        print(f"snapshot: {'present' if snap.exists() else 'none'} ({snap})")
        return 0

    if a.command == "rename":
        if not a.name:
            sys.exit("rename needs --name")
        target = {**current, "name": a.name}
        print("will rename the Yext sandbox entity", sid, "from", repr(current["name"]), "to", repr(a.name))
        if not a.yes:
            print("dry run; add --yes to apply")
            return 0
        if not snap.exists() or a.force:
            OUT.mkdir(exist_ok=True)
            snap.write_text(json.dumps(current, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"snapshot saved to {snap}")
        else:
            print(f"keeping the existing snapshot {snap} (the true original)")
        _write(client, sid, {"name": a.name})
        print("renamed. Restart the server to see it; `restore --yes` puts the original back.")
        return 0

    if a.command == "seed":
        target = copy.deepcopy(current)
        ke = _kit_entity(local)
        if not a.hours_only:
            target["name"] = ke["name"]
        target["hours"] = copy.deepcopy(ke["hours"])
        if a.category and not a.hours_only:
            target["categories"] = {**(current.get("categories") or {}), "fonecta": [a.category]}
        elif not a.hours_only:
            print("note: no --category given, so the category stays as it is (the kit uses another taxonomy)")
        print("will write to the Yext sandbox entity:", sid)
        print(json.dumps({f: target[f] for f in FIELDS}, indent=2, ensure_ascii=False))
        if not a.yes:
            print("dry run; add --yes to apply")
            return 0
        if not snap.exists() or a.force:
            OUT.mkdir(exist_ok=True)
            snap.write_text(json.dumps(current, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"snapshot saved to {snap}")
        else:
            print(f"keeping the existing snapshot {snap} (the true original)")
        _write(client, sid, target, ("hours",) if a.hours_only else FIELDS)
        print("seeded. The sandbox now has the demo state.")
        return 0

    # restore
    if not snap.exists():
        sys.exit(f"no snapshot at {snap}; nothing to restore")
    original = json.loads(snap.read_text(encoding="utf-8"))
    print("will restore", sid, "to:")
    print(json.dumps(original, indent=2, ensure_ascii=False))
    if not a.yes:
        print("dry run; add --yes to apply")
        return 0
    _write(client, sid, original)
    after = _read(client, sid)
    if after == original:
        print("restored and verified.")
        return 0
    print("WARNING: Yext did not return exactly the original state. Compare:")
    print(json.dumps({"original": original, "now": after}, indent=2, ensure_ascii=False))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
