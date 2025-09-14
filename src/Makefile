install: 
	./ctf_proxy/bin/setup.sh
	make ui

install-with-ui: 
	sudo useradd --system --no-create-home --uid 1337 envoy || true
	sudo mkdir -p logs/tap logs/pre-tap logs-archive data
	sudo chown -R 1337:1337 logs logs-archive data
	sudo ./ctf_proxy/proxy/iptables-config.sh setup
	python3 ./ctf_proxy/bin/docker-config-gen.py | sudo tee data/config.yml
	docker-compose up -d --build --force-recreate ui

ui:
	docker compose run --rm ui
	docker compose kill -s SIGINT ui

ui-logs:
	docker compose logs -f ui

generate-config:
	python3 ./ctf_proxy/bin/docker-config-gen.py > config.yml

stop:
	docker-compose down

uninstall:
	sudo ./ctf_proxy/proxy/iptables-config.sh cleanup

dev:
	@$(MAKE) -f Makefile.dev $(filter-out $@,$(MAKECMDGOALS))

%:
	@:
