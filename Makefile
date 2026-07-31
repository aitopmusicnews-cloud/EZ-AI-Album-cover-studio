PYTHON ?= python3
VENV ?= .venv
PIP := $(VENV)/bin/pip
UVICORN := $(VENV)/bin/uvicorn
PYTEST := $(VENV)/bin/pytest
ALEMBIC := $(VENV)/bin/alembic

.PHONY: setup run test migrate check clean

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

clean:
	rm -rf $(VENV) .pytest_cache backend/.pytest_cache data/storage data/*.db
