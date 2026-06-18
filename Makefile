.PHONY: dev prod down logs shell migrate test test-all

# Use Docker Compose v2 if available, fall back to v1 otherwise.
DOCKER_COMPOSE := $(shell docker compose version >/dev/null 2>&1 && echo 'docker compose' || echo 'docker-compose')

# Startet die Dev-Umgebung. Entfernt alte Container zuerst,
# um den bekannten docker-compose v1.29.2 / Docker Engine >=25 Bug
# ('ContainerConfig' KeyError) zu umgehen.
dev:
	$(DOCKER_COMPOSE) -f docker-compose.dev.yaml rm -sf 2>/dev/null || true
	$(DOCKER_COMPOSE) -f docker-compose.dev.yaml up --build

dev-d:
	$(DOCKER_COMPOSE) -f docker-compose.dev.yaml rm -sf 2>/dev/null || true
	$(DOCKER_COMPOSE) -f docker-compose.dev.yaml up --build -d

prod:
	$(DOCKER_COMPOSE) -f docker-compose.prod.yaml up --build -d

down:
	$(DOCKER_COMPOSE) -f docker-compose.dev.yaml down 2>/dev/null || \
	$(DOCKER_COMPOSE) -f docker-compose.prod.yaml down 2>/dev/null || true

logs:
	docker logs -f trackable-dev

shell:
	docker exec -it trackable-dev python manage.py shell

migrate:
	docker exec -it trackable-dev python manage.py migrate

test:
	# Run without -it so it also works in non-TTY environments (CI, scripts).
	docker exec trackable-dev python manage.py test --settings=trackable.settings.test

test-all:
	# Run tests in a fresh container and rebuild the image first.
	$(DOCKER_COMPOSE) -f docker-compose.dev.yaml run --rm --build app python manage.py test --settings=trackable.settings.test
