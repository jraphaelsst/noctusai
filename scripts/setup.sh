#!/usr/bin/env bash
# Forwarding shim — real script moved to scripts/bootstrap/setup.sh
# (scripts-mcp-absorption Phase 6 folder reorg). The `bash scripts/setup.sh`
# fresh-clone contract is preserved here; do not add logic — edit
# scripts/bootstrap/setup.sh.
exec bash "$(cd "$(dirname "$0")" && pwd)/bootstrap/setup.sh" "$@"
