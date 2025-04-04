
default:
	@echo "Call a specific subcommand:"
	@echo
	@$(MAKE) -pRrq -f $(lastword $(MAKEFILE_LIST)) : 2>/dev/null\
	| awk -v RS= -F: '/^# File/,/^# Finished Make data base/ {if ($$1 !~ "^[#.]") {print $$1}}'\
	| sort\
	| egrep -v -e '^[^[:alnum:]]' -e '^$@$$'
	@echo
	@exit 1

.state/docker-build-web: Dockerfile requirements.txt requirements-dev.txt
	# Build our web container for this project.
	docker compose build --build-arg  USER_ID=$(shell id -u)  --build-arg GROUP_ID=$(shell id -g) --force-rm web

	# Collect static assets
	docker compose run --rm web python manage.py collectstatic --noinput

	# Mark the state so we don't rebuild this needlessly.
	mkdir -p .state
	touch .state/docker-build-web

.state/db-migrated:
	make migrate
	mkdir -p .state && touch .state/db-migrated

.state/db-initialized: .state/docker-build-web .state/db-migrated
        # Do anything you might need to after the DB is built/migrated here (like fixtures)

	# Mark the state so we don't reload after first launch.
	mkdir -p .state
	touch .state/db-initialized

serve: .state/db-initialized
	docker compose up --remove-orphans -d

shell: .state/db-initialized
	docker compose run --rm web /bin/bash

dbshell: .state/db-initialized
	docker compose exec postgres psql -U pyladiescon pyladiescon

manage: .state/db-initialized
	# Run Django manage to accept arbitrary arguments
	docker compose run --rm web ./manage.py $(filter-out $@,$(MAKECMDGOALS))

migrations: .state/db-initialized
	# Run Django makemigrations
	docker compose run --rm web ./manage.py makemigrations

migrate: .state/docker-build-web
	# Run Django migrate
	docker compose run --rm web ./manage.py migrate $(filter-out $@,$(MAKECMDGOALS))

lint: .state/docker-build-web
	docker compose run --rm web isort --check-only .
	docker compose run --rm web black --check .
	docker compose run --rm web flake8

reformat: .state/docker-build-web
	docker compose run --rm web isort .
	docker compose run --rm web black .

test: .state/docker-build-web
	docker compose run --rm web pytest --cov --reuse-db --no-migrations
	docker compose run --rm web python -m coverage html --show-contexts
	docker compose run --rm web python -m coverage report -m

check: test lint

clean:
	docker compose down -v
	rm -rf staticroot
	rm -f .state/docker-build-web
	rm -f .state/db-initialized
	rm -f .state/db-migrated
