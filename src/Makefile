install: 
	./ctf_proxy/bin/setup.sh

ui:
	docker compose run --rm ui
	docker compose kill -s SIGINT ui

ui-logs:
	docker compose logs -f ui

generate-config:
	python3 ./ctf_proxy/bin/docker-config-gen.py > config.yml

stop:
	docker-compose down

dev:
	@$(MAKE) -f Makefile.dev $(filter-out $@,$(MAKECMDGOALS))

%:
	@:
