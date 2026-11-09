PY ?= python3
export PYTHONPATH := src

.PHONY: check lint test web-test tf dev heldout lock lock-check cost report api
check: lint test web-test lock-check
lint:
	ruff format --check src tests scripts && ruff check src tests scripts
test:
	$(PY) -m pytest -q
web-test:
	cd web && npx vitest run
tf:
	cd infra/terraform && tofu fmt -check -recursive && tofu init -backend=false -input=false && tofu validate
dev:
	$(PY) scripts/evaluate.py dev
heldout:
	$(PY) scripts/evaluate.py heldout
lock:
	$(PY) scripts/lock.py write
lock-check:
	$(PY) scripts/lock.py verify
cost:
	$(PY) scripts/cost_report.py
report:
	$(PY) scripts/report.py
api:
	$(PY) -m uvicorn paved.api:app --reload
