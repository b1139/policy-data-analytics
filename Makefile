.PHONY: help start start-local stop status test test-backend test-frontend migrate lint lint-backend lint-frontend logs shell shell-backend install install-backend install-frontend

VENV ?= ./venv/bin
PYTHON := $(shell if [ -x "$(VENV)/python" ]; then echo "$(VENV)/python"; elif command -v python3 >/dev/null 2>&1; then echo "python3"; else echo "python"; fi)
UVICORN := $(shell if [ -x "$(VENV)/uvicorn" ]; then echo "$(VENV)/uvicorn"; elif command -v uvicorn >/dev/null 2>&1; then echo "uvicorn"; else echo "$(PYTHON) -m uvicorn"; fi)
ALEMBIC := $(shell if [ -x "$(VENV)/alembic" ]; then echo "$(VENV)/alembic"; elif command -v alembic >/dev/null 2>&1; then echo "alembic"; else echo "$(PYTHON) -m alembic"; fi)
PYTEST := $(shell if [ -x "$(VENV)/pytest" ]; then echo "$(VENV)/pytest"; elif command -v pytest >/dev/null 2>&1; then echo "pytest"; else echo "$(PYTHON) -m pytest"; fi)
RUFF := $(shell if [ -x "$(VENV)/ruff" ]; then echo "$(VENV)/ruff"; elif command -v ruff >/dev/null 2>&1; then echo "ruff"; else echo "$(PYTHON) -m ruff"; fi)

help:
	@echo "Agentic Policy Data Analytics Platform - Command Center"
	@echo "Available commands:"
	@echo "  make install        Install both backend (Python) and frontend (npm) dependencies"
	@echo "  make install-backend Install backend dependencies into ./venv"
	@echo "  make install-frontend Install frontend npm dependencies"
	@echo "  make start          Start all services (Docker if available, otherwise native background)"
	@echo "  make start-local    Start FastAPI & Next.js directly on host in background"
	@echo "  make stop           Stop all running services"
	@echo "  make status         Check running status of backend & frontend"
	@echo "  make test           Run backend and frontend tests (Docker or local)"
	@echo "  make test-backend   Run backend pytest suite (auto-detects Docker / local venv)"
	@echo "  make test-frontend  Run frontend jest suite"
	@echo "  make migrate        Run database migrations (alembic upgrade head)"
	@echo "  make lint           Run lint checks (ruff + eslint)"
	@echo "  make logs           Follow service logs"
	@echo "  make shell          Open an interactive shell in backend service"

install: install-backend install-frontend

install-backend:
	@echo "Setting up Python virtual environment and installing backend dependencies..."
	@if [ ! -d "./venv" ]; then python3 -m venv ./venv; fi
	@./venv/bin/pip install --upgrade pip
	@./venv/bin/pip install -r backend/requirements.txt
	@echo "✔ Backend dependencies installed successfully."

install-frontend:
	@echo "Installing frontend npm dependencies..."
	@cd frontend && npm install
	@echo "✔ Frontend dependencies installed successfully."

start:
	@if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then \
		echo "Starting services via Docker Compose..."; \
		docker compose up -d; \
	else \
		echo "Docker daemon not running; launching services locally..."; \
		$(MAKE) start-local; \
	fi

start-local: migrate
	@if ! [ -x "$(VENV)/uvicorn" ] && ! command -v uvicorn >/dev/null 2>&1; then \
		echo "Error: uvicorn is not installed. Run 'make install-backend' first."; \
		exit 1; \
	fi
	@echo "Starting FastAPI Backend on http://localhost:8000..."
	@pkill -f "uvicorn app.main:app" 2>/dev/null || true
	@nohup $(UVICORN) app.main:app --host 0.0.0.0 --port 8000 > backend.log 2>&1 & echo $$! > .backend.pid
	@echo "Starting Next.js Frontend on http://localhost:3000..."
	@pkill -f "next-server|next dev" 2>/dev/null || true
	@cd frontend && nohup npm run dev > ../frontend.log 2>&1 & echo $$! > ../.frontend.pid
	@sleep 4
	@echo "==> Services are up and running!"
	@echo "  • Backend API:  http://localhost:8000 (Docs: http://localhost:8000/docs)"
	@echo "  • Frontend UI:  http://localhost:3000"

status:
	@echo "=== Service Status ==="
	@curl -s -f http://localhost:8000/api/v1/health >/dev/null 2>&1 && echo "  Backend (8000):  RUNNING (Healthy)" || echo "  Backend (8000):  STOPPED"
	@curl -s -f http://localhost:3000 >/dev/null 2>&1 && echo "  Frontend (3000): RUNNING (Healthy)" || echo "  Frontend (3000): STOPPED"

stop:
	@if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then \
		docker compose down 2>/dev/null || true; \
	fi
	@if [ -f .backend.pid ]; then \
		kill $$(cat .backend.pid) 2>/dev/null || true; \
		rm -f .backend.pid; \
	fi
	@pkill -f "uvicorn app.main:app" 2>/dev/null || true
	@if [ -f .frontend.pid ]; then \
		kill $$(cat .frontend.pid) 2>/dev/null || true; \
		rm -f .frontend.pid; \
	fi
	@pkill -f "next-server|next dev" 2>/dev/null || true
	@echo "All services stopped."

logs:
	@if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then \
		docker compose logs -f; \
	else \
		tail -f backend.log frontend.log; \
	fi

migrate:
	@if command -v docker >/dev/null 2>&1 && docker compose ps --services --filter "status=running" 2>/dev/null | grep -q "^backend$$"; then \
		echo "Running database migrations inside running Docker backend container..."; \
		docker compose exec -T backend alembic upgrade head; \
	elif [ -x "$(VENV)/alembic" ]; then \
		$(VENV)/alembic -c backend/alembic.ini upgrade head; \
	elif command -v alembic >/dev/null 2>&1; then \
		alembic -c backend/alembic.ini upgrade head; \
	elif $(PYTHON) -m alembic --help >/dev/null 2>&1; then \
		$(PYTHON) -m alembic -c backend/alembic.ini upgrade head; \
	elif command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then \
		echo "Running database migrations via Docker Compose..."; \
		docker compose run --rm backend alembic upgrade head; \
	else \
		echo "Error: alembic not found locally and Docker is not running."; \
		echo "Run 'make install-backend' to set up local dependencies."; \
		exit 1; \
	fi

test-backend:
	@if [ -x "$(VENV)/pytest" ]; then \
		echo "Running backend tests using local venv ($(VENV)/pytest)..."; \
		PYTHONPATH=backend:$$PYTHONPATH $(VENV)/pytest backend/tests; \
	elif command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then \
		if docker compose ps --services --filter "status=running" 2>/dev/null | grep -q "^backend$$"; then \
			echo "Running backend tests inside running Docker container (backend)..."; \
			docker compose exec -T backend pytest tests; \
		else \
			echo "Running backend tests via Docker Compose (backend container)..."; \
			docker compose run --rm backend pytest tests; \
		fi; \
	elif command -v pytest >/dev/null 2>&1; then \
		echo "Running backend tests using system pytest..."; \
		PYTHONPATH=backend:$$PYTHONPATH pytest backend/tests; \
	elif $(PYTHON) -m pytest --version >/dev/null 2>&1; then \
		echo "Running backend tests using $(PYTHON) -m pytest..."; \
		PYTHONPATH=backend:$$PYTHONPATH $(PYTHON) -m pytest backend/tests; \
	else \
		echo "Error: pytest not found in $(VENV), system PATH, or Docker."; \
		echo "To resolve this, either:"; \
		echo "  1) Install dependencies into your local venv: make install-backend"; \
		echo "  2) Or start Docker: docker compose up -d (then run 'make test-backend')"; \
		exit 1; \
	fi

test-frontend:
	@if [ -d "frontend/node_modules" ]; then \
		echo "Running frontend tests using local node_modules..."; \
		cd frontend && npm test -- --watchAll=false; \
	elif command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then \
		echo "Running frontend tests via Docker container with test dependencies..."; \
		docker run --rm -v $$(pwd)/frontend:/app -w /app node:18-alpine sh -c "npm ci && npm test -- --watchAll=false"; \
	else \
		echo "Error: frontend/node_modules not found. Run 'make install-frontend' first."; \
		exit 1; \
	fi

test: test-backend test-frontend

lint-backend:
	@if [ -x "$(VENV)/ruff" ]; then \
		$(VENV)/ruff check backend && $(VENV)/ruff format --check backend; \
	elif command -v ruff >/dev/null 2>&1; then \
		ruff check backend && ruff format --check backend; \
	elif command -v docker >/dev/null 2>&1 && docker compose ps --services --filter "status=running" 2>/dev/null | grep -q "^backend$$"; then \
		docker compose exec -T backend ruff check app tests && docker compose exec -T backend ruff format --check app tests; \
	elif $(PYTHON) -m ruff --version >/dev/null 2>&1; then \
		$(PYTHON) -m ruff check backend && $(PYTHON) -m ruff format --check backend; \
	else \
		echo "Error: ruff not found. Run 'make install-backend' or 'pip install ruff'."; \
		exit 1; \
	fi

lint-frontend:
	@if [ -d "frontend/node_modules" ]; then \
		cd frontend && npm run lint; \
	elif command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then \
		docker run --rm -v $$(pwd)/frontend:/app -w /app node:18-alpine sh -c "npm ci && npm run lint"; \
	else \
		echo "Error: frontend/node_modules not found. Run 'make install-frontend' first."; \
		exit 1; \
	fi

lint: lint-backend lint-frontend

shell-backend:
	@if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then \
		docker compose exec backend bash; \
	else \
		echo "Error: Docker is required for container shell."; \
		exit 1; \
	fi

shell: shell-backend
