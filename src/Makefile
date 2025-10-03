install:
	./ctf_proxy/bin/setup.sh

config:
	mkdir -p traefik
	./uv.sh run ./ctf_proxy/bin/traefik-config-gen.py ./data/config.yml ./traefik
	./uv.sh run ./ctf_proxy/bin/docker-compose-gen.py ./data/config.yml ./docker-compose.template.yml ./docker-compose.yml

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
