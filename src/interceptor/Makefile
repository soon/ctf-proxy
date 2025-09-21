.PHONY: build clean test

build:
	@echo "Building WASM interceptor with TCP support..."
	@tinygo build -o wasm/interceptor.wasm -scheduler=none -target=wasi -wasm-abi=generic \
		-panic=trap -opt=2 \
		main.go interceptor.go tcp_interceptor.go types.go utils.go helpers.go
	@echo "Build complete: wasm/interceptor.wasm"

clean:
	@rm -f wasm/interceptor.wasm
	@echo "Cleaned build artifacts"

test:
	@cd test && $(MAKE) test

docker-build:
	@docker run --rm -v $(PWD):/src -w /src tinygo/tinygo:latest \
		tinygo build -o wasm/interceptor.wasm -scheduler=none -target=wasi -wasm-abi=generic \
		-panic=trap -opt=2 \
		main.go interceptor.go tcp_interceptor.go types.go utils.go helpers.go
	@echo "Docker build complete: wasm/interceptor.wasm"