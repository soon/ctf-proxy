.PHONY: build

build:
	@echo "Building interceptor WASM files..."
	@mkdir -p wasm
	@TIMESTAMP=$$(date +"%Y%m%d_%H%M%S"); \
	if [ -n "$(LABEL)" ]; then \
		LABEL="$(LABEL)"; \
	else \
		read -p "Enter optional label (or press enter for none): " LABEL; \
	fi; \
	if [ -n "$$LABEL" ]; then \
		SUFFIX="$${TIMESTAMP}_$${LABEL}"; \
	else \
		SUFFIX="$$TIMESTAMP"; \
	fi; \
	echo "Building with suffix: $$SUFFIX"; \
	docker buildx build --output type=local,dest=./ -f Dockerfile.build .; \
	if [ -f wasm/interceptor_http.wasm ]; then \
		cp wasm/interceptor_http.wasm wasm/interceptor_http_$$SUFFIX.wasm; \
		echo "Created: wasm/interceptor_http_$$SUFFIX.wasm"; \
	fi; \
	if [ -f wasm/interceptor_tcp.wasm ]; then \
		cp wasm/interceptor_tcp.wasm wasm/interceptor_tcp_$$SUFFIX.wasm; \
		echo "Created: wasm/interceptor_tcp_$$SUFFIX.wasm"; \
	fi
