#!/usr/bin/env bash
# Start the vegetable MCP server. Reads VEG_MCP_TOKEN from .env next to this file.
cd "$(dirname "$0")"
set -a; [ -f .env ] && . ./.env; set +a
exec .venv/bin/python veg_mcp.py
