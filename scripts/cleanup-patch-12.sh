#!/bin/sh
set -eu

# Patch 12 cleanup: remove generated files that may have slipped into earlier patch archives.
rm -rf src/privatetv.egg-info
find . -type d \( -name '__pycache__' -o -name '.pytest_cache' -o -name '.ruff_cache' \) -prune -exec rm -rf {} +
