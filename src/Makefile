install: 
	sudo useradd --system --no-create-home --uid 1337 envoy || true
	sudo mkdir -p logs/tap
	sudo chown -R 1337:1337 logs
	sudo ./iptables-config.sh setup
	docker-compose up -d
