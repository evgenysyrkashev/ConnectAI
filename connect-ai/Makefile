PY ?= $(shell command -v python3.12 || command -v python3.13)
setup:            ; $(PY) -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
dev:              ; SCHEDULER_INTERVAL_S=$${SCHEDULER_INTERVAL_S:-15} .venv/bin/uvicorn app.server.main:app --reload --port 8080
test:             ; .venv/bin/pytest -q
test-fast:        ; .venv/bin/pytest -q -m "not integration"
lint:             ; .venv/bin/ruff check . && .venv/bin/ruff format --check .
fmt:              ; .venv/bin/ruff format . && .venv/bin/ruff check --fix .
eval:             ; .venv/bin/python -m scripts.eval_parser
messages:         ; .venv/bin/python -m scripts.export_messages
