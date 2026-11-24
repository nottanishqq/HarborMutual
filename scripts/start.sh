#!/bin/sh
# Container entrypoint: in-memory SurrealDB, load snapshot + access rules, then the app.
set -e
export SURREAL_USER=root
# Root never leaves the container; a fresh random password each boot.
export SURREAL_PASS="${SURREAL_PASS:-$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')}"
export SURREAL_URL=http://127.0.0.1:8000

surreal start --log warn --bind 127.0.0.1:8000 --user root --pass "$SURREAL_PASS" memory &
until surreal is-ready --endpoint "$SURREAL_URL" >/dev/null 2>&1; do sleep 0.5; done

surreal import --endpoint "$SURREAL_URL" -u root -p "$SURREAL_PASS" --ns harbor --db main data/harbor.surql
surreal sql --endpoint "$SURREAL_URL" -u root -p "$SURREAL_PASS" --ns harbor --db main --hide-welcome < schema/access.surql

exec python -m uvicorn harbor.app:app --host 0.0.0.0 --port "${PORT:-7860}"
