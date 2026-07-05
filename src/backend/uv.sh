#!/bin/bash

# Detect if we're on the VM system
if [ "$(hostname)" = "qs-Virtual-Machine.local" ]; then
    export UV_PROJECT_ENVIRONMENT=.venv_vm
fi

# Pass all arguments to uv
exec uv "$@"