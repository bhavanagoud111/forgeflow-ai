# ForgeFlow AI developer commands.
.PHONY: setup dev api web test test-docker lint typecheck format build sandbox-image up down migrate token

setup:            ## Install backend and web dependencies
	cd backend && uv sync
	cd apps/web && npm ci

api:              ## Run the API with an embedded worker (demo provider, local sandbox)
	cd backend && uv run uvicorn forgeflow.main:app --reload --port 8000

web:              ## Run the web UI (needs FORGEFLOW_API_TOKEN in apps/web/.env.local)
	cd apps/web && npm run dev

test:             ## Backend unit, integration and e2e tests + web unit tests
	cd backend && uv run pytest -q
	cd apps/web && npm test

test-docker: sandbox-image  ## Tests that need the Docker sandbox
	cd backend && FORGEFLOW_TEST_DOCKER=1 uv run pytest -q -k docker

lint:
	cd backend && uv run ruff check src tests && uv run ruff format --check src tests
	cd apps/web && npm run lint

typecheck:
	cd backend && uv run mypy src
	cd apps/web && npm run typecheck

format:
	cd backend && uv run ruff format src tests && uv run ruff check --fix src tests

build:            ## Production build of the web app
	cd apps/web && npm run build

sandbox-image:    ## Image used by FORGEFLOW_SANDBOX_MODE=docker and the sandbox-runner service
	docker build -f infrastructure/docker/sandbox.Dockerfile -t forgeflow-sandbox:latest .

migrate:          ## Apply database migrations (uses FORGEFLOW_DATABASE_URL)
	cd backend && uv run alembic upgrade head

token:            ## Create an operator token: make token NAME=alice ROLE=operator
	cd backend && uv run forgeflow create-token --name $(NAME) --role $(or $(ROLE),operator)

up:               ## Full stack in Docker Compose
	docker compose up --build

down:
	docker compose down
