COMPOSE ?= docker compose
COMPOSE_FILE ?= infra/compose.yaml
RUNTIME_ROOT ?= $(CURDIR)/runtime
MACOS_APP_DIR ?= apps
MACOS_CAPTURE_LABEL ?= com.thirdeye.macos-capture-agent
MACOS_CAPTURE_HOST ?= 127.0.0.1
MACOS_CAPTURE_PORT ?= 8791
MACOS_CAPTURE_RUNTIME_DIR ?= $(RUNTIME_ROOT)/macos-capture-runtime
MACOS_CAPTURE_LOG_DIR ?= $(RUNTIME_ROOT)/logs
MACOS_CAPTURE_PLIST ?= $(RUNTIME_ROOT)/macos-capture-agent.plist
PYTHONPATH_DIRS := $(CURDIR)/services/controller-api/src:$(CURDIR)/services/desktop-agent/src:$(CURDIR)/services/macos-capture-agent/src:$(CURDIR)/packages

export MACOS_CAPTURE_LABEL
export MACOS_CAPTURE_HOST
export MACOS_CAPTURE_PORT
export MACOS_CAPTURE_RUNTIME_DIR
export MACOS_CAPTURE_LOG_DIR
export MACOS_CAPTURE_PLIST

.DEFAULT_GOAL := help

.PHONY: help setup doctor services-start services-stop services-status build up up-openclaw openclaw-sync down logs ps smoke test test-all dev-api dev-local macos-capture-build macos-capture-up macos-capture-status macos-capture-down macos-capture-logs macos-capture-permissions macos-app-install macos-app-dev macos-app-build macos-app-test

help:
	@printf 'Common commands:\n'
	@printf '  make setup                 Install source-built macOS app dependencies\n'
	@printf '  make doctor                Check local tool and runtime readiness\n'
	@printf '  make services-start        Start app-managed local services\n'
	@printf '  make services-status       Show app-managed local service status\n'
	@printf '  make up                    Start Docker services\n'
	@printf '  make dev-api               Start the local controller API\n'
	@printf '  make macos-capture-up      Start This Mac capture targets in the background\n'
	@printf '  make macos-capture-status  Check the This Mac capture agent\n'
	@printf '  make macos-capture-down    Stop the This Mac capture agent\n'
	@printf '  make macos-capture-permissions  Open macOS Screen Recording settings\n'
	@printf '  make macos-app-dev         Run thirdeye as a macOS app\n'
	@printf '  make macos-app-build       Build thirdeye.app\n'

setup:
	PYTHONPATH="$(PYTHONPATH_DIRS)" python3 -m core.local_services setup --repo-root "$(CURDIR)" --runtime-root "$(RUNTIME_ROOT)"

doctor:
	PYTHONPATH="$(PYTHONPATH_DIRS)" .venv/bin/python -m core.local_services doctor --repo-root "$(CURDIR)" --runtime-root "$(RUNTIME_ROOT)"

services-start:
	PYTHONPATH="$(PYTHONPATH_DIRS)" .venv/bin/python -m core.local_services start --repo-root "$(CURDIR)" --runtime-root "$(RUNTIME_ROOT)"

services-stop:
	PYTHONPATH="$(PYTHONPATH_DIRS)" .venv/bin/python -m core.local_services stop --repo-root "$(CURDIR)" --runtime-root "$(RUNTIME_ROOT)"

services-status:
	PYTHONPATH="$(PYTHONPATH_DIRS)" .venv/bin/python -m core.local_services status --repo-root "$(CURDIR)" --runtime-root "$(RUNTIME_ROOT)"

build:
	$(COMPOSE) --env-file .env -f "$(COMPOSE_FILE)" build

up:
	THIRDEYE_RUNTIME_ROOT="$(RUNTIME_ROOT)" $(COMPOSE) --env-file .env -f "$(COMPOSE_FILE)" up -d --remove-orphans

up-openclaw:
	./scripts/remediate_openclaw_gateway.sh --restart

openclaw-sync:
	./scripts/remediate_openclaw_gateway.sh

down:
	THIRDEYE_RUNTIME_ROOT="$(RUNTIME_ROOT)" $(COMPOSE) --env-file .env -f "$(COMPOSE_FILE)" down

logs:
	THIRDEYE_RUNTIME_ROOT="$(RUNTIME_ROOT)" $(COMPOSE) --env-file .env -f "$(COMPOSE_FILE)" logs -f --tail=200

ps:
	THIRDEYE_RUNTIME_ROOT="$(RUNTIME_ROOT)" $(COMPOSE) --env-file .env -f "$(COMPOSE_FILE)" ps

smoke:
	./scripts/smoke_test.sh

test:
	PYTHONPATH="$(PYTHONPATH_DIRS)" .venv/bin/python -m pytest tests/python -q

test-all: test macos-app-test
	cd $(MACOS_APP_DIR) && npm test
	cd $(MACOS_APP_DIR) && npm run typecheck

macos-capture-build:
	./scripts/build_macos_capture_helper.sh

macos-capture-up: macos-capture-build
	./scripts/macos_capture_agent.sh up

macos-capture-status:
	./scripts/macos_capture_agent.sh status

macos-capture-down:
	./scripts/macos_capture_agent.sh down

macos-capture-logs:
	./scripts/macos_capture_agent.sh logs

macos-capture-permissions:
	./scripts/macos_capture_agent.sh permissions

macos-app-install:
	cd $(MACOS_APP_DIR) && npm install

macos-app-dev:
	cd $(MACOS_APP_DIR) && THIRDEYE_REPO_ROOT="$(CURDIR)" THIRDEYE_RUNTIME_ROOT="$(RUNTIME_ROOT)" npm run dev

macos-app-build:
	cd $(MACOS_APP_DIR) && THIRDEYE_REPO_ROOT="$(CURDIR)" npm run build

macos-app-test:
	cd $(MACOS_APP_DIR)/tauri && cargo test

dev-local:
	@printf 'Local dev startup:\n'
	@printf '  1. make up\n'
	@printf '  2. make macos-capture-up      # optional, enables This Mac targets\n'
	@printf '  3. make dev-api               # keep running in its own terminal\n'
	@printf '\n'
	@printf 'Useful checks:\n'
	@printf '  make macos-capture-status\n'
	@printf '  make macos-capture-logs\n'
	@printf '  make macos-capture-permissions\n'

dev-api:
	mkdir -p "$(RUNTIME_ROOT)/desktop-config" "$(RUNTIME_ROOT)/recordings" "$(RUNTIME_ROOT)/artifacts" "$(RUNTIME_ROOT)/controller" "$(RUNTIME_ROOT)/controller-events"
	set -a; [ ! -f .env ] || . ./.env; set +a; PYTHONPATH="$(PYTHONPATH_DIRS)" CONTROLLER_BASE_URL=http://127.0.0.1:8788 DESKTOP_BASE_URL=$${LOCAL_DESKTOP_BASE_URL:-http://127.0.0.1:8790} OPENCLAW_BASE_URL=$${LOCAL_OPENCLAW_BASE_URL:-http://127.0.0.1:18789} CONTROLLER_DB_PATH=$${CONTROLLER_DB_PATH:-$(RUNTIME_ROOT)/controller/controller.db} ARTIFACTS_ROOT=$${ARTIFACTS_ROOT:-$(RUNTIME_ROOT)/artifacts} RECORDINGS_ROOT=$${RECORDINGS_ROOT:-$(RUNTIME_ROOT)/recordings} CONTROLLER_EVENTS_ROOT=$${CONTROLLER_EVENTS_ROOT:-$(RUNTIME_ROOT)/controller-events} .venv/bin/uvicorn api.main:create_app --factory --host 127.0.0.1 --port 8788
