#!/bin/bash

# Script to find and kill checker processes running the specific command

# Search for processes matching the checker command pattern
PIDS=$(pgrep -f "do PYTHONPATH=/Users/andrey/Src/Workspaces/ctf/ctf-proxy/3rd/ctf-gameserver/src uv run")

if [ -n "$PIDS" ]; then
    echo "Found checker processes with PIDs: $PIDS"
    kill -9 $PIDS
    echo "Killed checker processes"
else
    echo "No matching checker processes found"
fi
