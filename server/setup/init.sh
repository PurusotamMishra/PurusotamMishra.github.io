#!/bin/bash
echo "Starting init.sh"

interfaces=("a2a" "api" "mcp")

for interface in "${interfaces[@]}"; do
  python3 -m interfaces.$interface.run &
done

wait
echo "Completed init.sh"
