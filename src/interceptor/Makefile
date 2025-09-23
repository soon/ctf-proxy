.PHONY: build

build:
	mkdir -p wasm
	docker buildx build --output type=local,dest=./ -f Dockerfile.build .
