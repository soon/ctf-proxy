#!/bin/bash

# Script to install and start all Faust CTF services in examples directory

set -e

EXAMPLES_DIR="~/services"

# Find all faustctf-2024-* directories
for dir in "$EXAMPLES_DIR"/faustctf-2024-*; do
    if [ -d "$dir" ]; then
        echo "Processing $dir"

        # Change to the directory
        cd "$dir"

        # Run make install
        echo "Running make install in $(basename "$dir")"
        make install

        # Extract SERVICE name from Makefile
        SERVICE=$(grep "^SERVICE :=" Makefile | cut -d' ' -f3)

        if [ -z "$SERVICE" ]; then
            echo "Warning: Could not find SERVICE in $dir/Makefile"
            continue
        fi

        # Go to the installed service directory
        SERVICE_DIR="dist_root/srv/$SERVICE"
        if [ -d "$SERVICE_DIR" ]; then
            cd "$SERVICE_DIR"
            echo "Starting docker compose in $SERVICE_DIR"
            docker compose up -d
        else
            echo "Warning: Service directory $SERVICE_DIR not found"
        fi

        # Go back to examples dir for next iteration
        cd "$EXAMPLES_DIR"
    fi
done

echo "All services processed"
