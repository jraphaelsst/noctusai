#!/usr/bin/env bash
# Forwarding shim — real script moved to scripts/hooks/install-hooks.sh
# (scripts-mcp-absorption Phase 6). Preserves the `bash scripts/install-hooks.sh`
# contract; do not add logic — edit scripts/hooks/install-hooks.sh.
exec bash "$(cd "$(dirname "$0")" && pwd)/hooks/install-hooks.sh" "$@"
