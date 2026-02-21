#!/usr/bin/env bash
set -euo pipefail

# OpenWebUI -> local OpenAI-compatible backend
export OPENAI_API_BASE_URL="http://127.0.0.1:8080/v1"
export OPENAI_API_KEY="truthbattle-local"
# Compatibility aliases used by some OpenWebUI versions
export OPENAI_API_BASE_URLS="http://127.0.0.1:8080/v1"
export OPENAI_API_KEYS="truthbattle-local"

# Optional: disable login for local dev
export WEBUI_AUTH=False

open-webui serve --host 0.0.0.0 --port 3000
