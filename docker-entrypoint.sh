#!/bin/sh
# Container entry point.
#
# EXAMGEN_SECRET_KEY must be set in production. Without it the application mints
# a fresh per-process key, which silently invalidates every issued token on each
# restart. Refuse to start rather than run in that state.
set -e

if [ -z "${EXAMGEN_SECRET_KEY:-}" ]; then
    echo "EXAMGEN_SECRET_KEY is not set." >&2
    echo "Set it to a long random string, for example: openssl rand -hex 32" >&2
    exit 1
fi

if [ "${#EXAMGEN_SECRET_KEY}" -lt 16 ]; then
    echo "EXAMGEN_SECRET_KEY must be at least 16 characters." >&2
    exit 1
fi

exec uvicorn app:app --host 0.0.0.0 --port "${PORT:-8000}"
