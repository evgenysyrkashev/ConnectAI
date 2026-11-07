import pytest

from app.server.adapters.yext_embedded import start_embedded_mock
from app.server.config import load_config
from app.server.deps import build_deps


@pytest.fixture(scope="session")
def mock_url():
    return start_embedded_mock()


@pytest.fixture(scope="session")
def suggestions():
    from app.server.adapters.suggestions_baseline import BaselineSuggestions

    return BaselineSuggestions()


@pytest.fixture(scope="session")
def findability():
    from app.server.adapters.findability import ParquetFindability

    return ParquetFindability()


@pytest.fixture
def real_deps():
    """Real baseline + parquet findability + embedded kit mock, with fake mail/LLM and the memory store."""
    deps = build_deps(load_config({"DEMO_RECIPIENT_TEMPLATE": "tester+{entity}@example.com", "PHONE_ALLOWLIST": "*"}))
    return deps
