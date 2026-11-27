#!/usr/bin/env bash
set -eu
exec python3 "$(dirname "$0")/../../scripts/install_stand.py" "${1:-prepare}"
