PYTHON ?= python3
VENV ?= .venv
PIP := $(VENV)/bin/pip
VENV_PYTHON := $(VENV)/bin/python
UVICORN := $(VENV)/bin/uvicorn
PYTEST := $(VENV)/bin/pytest
ALEMBIC := $(VENV)/bin/alembic
LOAD_BASE_URL ?=
LOAD_COLLECTION_ID ?= load_test_collection_01

.PHONY: setup run test migrate check load-smoke clean

setup:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -e "./backend[test]"

run:
	cd backend && ../$(UVICORN) app.main:app --reload --host 127.0.0.1 --port 8000

test:
	cd backend && ../$(PYTEST)

migrate:
	cd backend && ../$(ALEMBIC) upgrade head

check:
	$(PYTHON) -m compileall -q backend/app
	node --check frontend/app.js
	cd backend && ../$(PYTEST)

load-smoke:
	@test -n "$(LOAD_BASE_URL)" || (echo "Set LOAD_BASE_URL=https://your-service.onrender.com" && exit 2)
	@mkdir -p load-test-results
	cd backend && ../$(VENV_PYTHON) -m app.load_testing \
		--base-url "$(LOAD_BASE_URL)" \
		--collection-id "$(LOAD_COLLECTION_ID)" \
		--users 5 \
		--duration 20 \
		--ramp 5 \
		--scenario mixed \
		--json-output ../load-test-results/smoke.json

clean:
	rm -rf $(VENV) .pytest_cache backend/.pytest_cache data/storage data/*.db load-test-results
