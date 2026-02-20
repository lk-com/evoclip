#!/usr/bin/env bash
set -euo pipefail

# Requires API service and worker process to be running.
python -m pytest tests/e2e -m e2e -q
