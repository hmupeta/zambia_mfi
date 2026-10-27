#!/bin/sh
# ============================================================
# Container health probe — hits /healthz/
# ============================================================
set -e

curl -fsS http://127.0.0.1:8000/healthz/ > /dev/null \
    || curl -fsS http://127.0.0.1:8000/ > /dev/null \
    || exit 1
exit 0
