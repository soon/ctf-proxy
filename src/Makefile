install:
	./ctf_proxy/bin/setup.sh

setup-test:
	./ctf_proxy/bin/setup.sh --test

ui:
	docker compose run --rm ui
	docker compose kill -s SIGINT ui

ui-logs:
	docker compose logs -f ui

stop:
	docker-compose down

dev:
	@$(MAKE) -f Makefile.dev $(filter-out $@,$(MAKECMDGOALS))

%:
	@:
