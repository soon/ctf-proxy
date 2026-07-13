.PHONY: build

build:
	@echo "Building interceptor WASM files..."
	@rm -rf wasm
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
	docker buildx build --output type=local,dest=./wasm -f Dockerfile.build . \
		|| { echo "ERROR: docker buildx build failed" >&2; exit 1; }; \
	if [ ! -f wasm/interceptor.wasm ]; then \
		echo "ERROR: build produced no wasm/interceptor.wasm" >&2; \
		exit 1; \
	fi; \
	cp wasm/interceptor.wasm wasm/interceptor_$$SUFFIX.wasm; \
	echo "Created: wasm/interceptor_$$SUFFIX.wasm"
