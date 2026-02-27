.PHONY: dev prod down logs shell migrate test

# Startet die Dev-Umgebung. Entfernt alte Container zuerst,
# um den bekannten docker-compose v1.29.2 / Docker Engine >=25 Bug
# ('ContainerConfig' KeyError) zu umgehen.
dev:
	docker-compose -f docker-compose.dev.yaml rm -sf 2>/dev/null || true
	docker-compose -f docker-compose.dev.yaml up --build

dev-d:
	docker-compose -f docker-compose.dev.yaml rm -sf 2>/dev/null || true
	docker-compose -f docker-compose.dev.yaml up --build -d

prod:
	docker-compose -f docker-compose.prod.yaml up --build -d

down:
	docker-compose -f docker-compose.dev.yaml down 2>/dev/null || \
	docker-compose -f docker-compose.prod.yaml down 2>/dev/null || true

logs:
	docker logs -f trackable-dev

shell:
	docker exec -it trackable-dev python manage.py shell

migrate:
	docker exec -it trackable-dev python manage.py migrate

test:
	docker exec -it trackable-dev python manage.py test
