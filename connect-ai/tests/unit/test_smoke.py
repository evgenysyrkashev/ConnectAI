from fastapi.testclient import TestClient

from app.server.config import ConfigError, load_config
from app.server.main import create_app


def test_healthz():
    client = TestClient(create_app(load_config({})))
    r = client.get("/healthz")
    assert r.status_code == 200 and r.text == "ok"


def test_config_fails_fast():
    try:
        load_config({"APP_ENV": "staging", "SERVICE_ROLE": "web"})
    except ConfigError as e:
        assert "TOKEN_HMAC_KEY" in str(e)
    else:
        raise AssertionError("expected ConfigError")


def test_kit_bridge():
    from app import kit

    assert kit.is_valid_hours("09:00-17:00") and "monday" in [d.lower() for d in kit.DAYS]
