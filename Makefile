.PHONY: install test run docker-build docker-up docker-down smoke qa clean

install:
	pip install -r requirements-dev.txt

test:
	pytest -q

test-mock:
	LLM_MOCK=true pytest -q

run:
	uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

docker-build:
	docker compose build

docker-up:
	docker compose up -d

docker-down:
	docker compose down

smoke:
	curl -sf http://127.0.0.1:8000/health

qa:
	python scripts/multi_agent_qa.py

public-samples:
	LLM_MOCK=true python scripts/test_public_samples.py --mock

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete