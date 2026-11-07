"""Bridge to the hackathon kit. Never modify kit files; import them only from here."""

import os
import sys

# DECISION: the project lives in a subfolder of the kit repo, so the kit root is the parent
# folder by default. Override with KIT_ROOT (e.g. in Docker, where the kit is copied next to app/).
_PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.abspath(os.environ.get("KIT_ROOT") or os.path.dirname(_PROJECT))
for sub in ("mock_api", "examples"):
    p = os.path.join(ROOT, sub)
    if p not in sys.path:
        sys.path.insert(0, p)

from hours import DAYS, hours_str_to_yext_day, is_valid_hours, str_to_ivs, yext_day_to_str

__all__ = [
    "DAYS",
    "ROOT",
    "data_path",
    "hours_str_to_yext_day",
    "is_valid_hours",
    "load_baseline",
    "mock_server_module",
    "str_to_ivs",
    "yext_day_to_str",
]


def data_path(*parts: str) -> str:
    return os.path.join(ROOT, *parts)


def load_baseline(season: int = 2026):
    from baseline import Baseline  # heavy: loads ~40 MB of JSON; call once, lazily

    return Baseline(season)


def mock_server_module():
    import server  # kit mock_api/server.py

    return server
