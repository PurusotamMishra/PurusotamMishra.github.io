#!/bin/bash
echo "Starting init.sh"

servers=("a2a" "api" "mcp")

for server in "${servers[@]}"; do
  python3 -m server.interfaces.$server.run &
done

wait
echo "Completed init.sh"
