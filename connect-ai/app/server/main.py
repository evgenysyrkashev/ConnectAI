"""FastAPI app factory. `app` is a lazy ASGI wrapper so importing this module is cheap."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles

from app.server.config import Config, load_config
from app.server.security import SecurityMiddleware

log = logging.getLogger("connect")
HERE = Path(__file__).parent


def _setup_logging(level: str) -> None:
    lg = logging.getLogger("connect")
    lg.setLevel(level.upper())
    if not lg.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        lg.addHandler(h)


def _start_scheduler_ticks(deps, every_s: int) -> None:
    """Local demo only: call the scheduler on a timer, like the Cloud Scheduler cron does on GCP."""
    import threading
    import time

    from app.server.services import scheduler

    def loop() -> None:
        try:  # schedule everything with suggestions right at startup; sends follow on the ticks
            scheduler.auto_schedule(deps)
        except Exception as e:  # noqa: BLE001
            log.warning("startup scheduling failed: %s", type(e).__name__)
        while True:
            time.sleep(every_s)
            try:
                scheduler.run_scheduled(deps)
            except Exception as e:  # noqa: BLE001
                log.warning("scheduler tick failed: %s", type(e).__name__)

    threading.Thread(target=loop, daemon=True, name="scheduler-tick").start()


def create_app(config: Config | None = None, deps=None) -> FastAPI:
    config = config or load_config()
    app = FastAPI(title="ConnectAI", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.config = config
    app.state.deps = deps
    _setup_logging(config.log_level)
    app.add_middleware(SecurityMiddleware)

    @app.get("/healthz", response_class=PlainTextResponse)
    def healthz() -> str:
        return "ok"

    role = config.service_role
    if deps is not None and config.scheduler_interval_s > 0 and role in ("web", "all"):
        _start_scheduler_ticks(deps, config.scheduler_interval_s)
    if deps is not None:
        if role in ("webhooks", "all"):
            from app.server.routes_webhooks import make_router as webhooks

            app.include_router(webhooks(deps))
        if role in ("inbound", "all"):
            from app.server.routes_inbound import make_router as inbound

            app.include_router(inbound(deps))
        if role in ("web", "all"):
            from app.server.routes_dev import make_router as dev
            from app.server.routes_web import make_router as web

            app.include_router(web(deps))
            app.include_router(dev(deps))
    if role in ("web", "all"):
        app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    return app


class LazyApp:
    """ASGI callable that builds the real app (and its adapters) on the first request."""

    def __init__(self) -> None:
        self._app: FastAPI | None = None
        self._lock = threading.Lock()

    def _build(self) -> FastAPI:
        with self._lock:
            if self._app is None:
                from app.server.deps import build_deps

                cfg = load_config()
                self._app = create_app(cfg, build_deps(cfg))
            return self._app

    async def __call__(self, scope, receive, send):
        if self._app is None:
            import asyncio

            await asyncio.get_running_loop().run_in_executor(None, self._build)
        await self._app(scope, receive, send)  # type: ignore[misc]


app = LazyApp()
