#!/bin/bash

# Script to refresh Envoy configuration with latest WASM files
# Usage: ./refresh-envoy

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
INTERCEPTOR_DIR="$ROOT_DIR/interceptor"
PROXY_DIR="$ROOT_DIR/ctf_proxy/proxy"

echo "Refreshing Envoy configuration with latest WASM files..."

# Check if interceptor directory exists
if [ ! -d "$INTERCEPTOR_DIR/wasm" ]; then
    echo "Error: WASM directory not found at $INTERCEPTOR_DIR/wasm"
    echo "Please build interceptors first using: cd $INTERCEPTOR_DIR && make build"
    exit 1
fi

# Find latest WASM files
HTTP_LATEST=$(ls -t "$INTERCEPTOR_DIR/wasm/interceptor_http_"*.wasm 2>/dev/null | head -n1 | xargs basename 2>/dev/null || echo "interceptor_http.wasm")
TCP_LATEST=$(ls -t "$INTERCEPTOR_DIR/wasm/interceptor_tcp_"*.wasm 2>/dev/null | head -n1 | xargs basename 2>/dev/null || echo "interceptor_tcp.wasm")

echo "Using HTTP WASM: $HTTP_LATEST"
echo "Using TCP WASM: $TCP_LATEST"

# Check if template exists
if [ ! -f "$PROXY_DIR/envoy.template.yaml" ]; then
    echo "Error: Envoy template not found at $PROXY_DIR/envoy.template.yaml"
    exit 1
fi

# Generate new envoy.yaml from template
sed "s/{HTTP_INTERCEPTOR_FILENAME}/$HTTP_LATEST/g; s/{TCP_INTERCEPTOR_FILENAME}/$TCP_LATEST/g" \
    "$PROXY_DIR/envoy.template.yaml" > "$PROXY_DIR/envoy.yaml"

echo "Envoy configuration updated: $PROXY_DIR/envoy.yaml"
echo "Restart your proxy to apply the new configuration."