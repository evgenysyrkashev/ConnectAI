"""Start the kit's mock API inside this process (same trick as examples/quickstart.py)."""

from __future__ import annotations

import os
import socket
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer


def start_embedded_mock() -> str:
    os.environ.setdefault("MOCK_QUIET", "1")
    from app import kit

    server = kit.mock_server_module()
    server.STATE_FILE = os.path.join(tempfile.mkdtemp(), "state.json")  # never touch mock_api/state.json
    server.STORE = server.Store()
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    srv = ThreadingHTTPServer(("127.0.0.1", port), server.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.2)
    return f"http://127.0.0.1:{port}"


def add_entities(entities: list[dict]) -> None:
    """Add entities (e.g. fetched from the Yext sandbox) to the in-process mock only."""
    from app import kit

    store = kit.mock_server_module().STORE
    for e in entities:
        eid = e["meta"]["id"]
        if eid not in store.base:
            store.base[eid] = e
            store.order.append(eid)
