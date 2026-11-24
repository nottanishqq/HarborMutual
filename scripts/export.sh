#!/bin/sh
# Snapshot the migrated database into data/harbor.surql for the hosted demo.
# DEFINE ACCESS is dropped: export redacts its JWT key; schema/access.surql re-creates it on boot.
set -e
cd "$(dirname "$0")/.."
MSYS_NO_PATHCONV=1 docker compose exec -T surrealdb /surreal export \
  --endpoint http://localhost:8000 -u "${SURREAL_USER:-root}" -p "${SURREAL_PASS:-root}" \
  --ns harbor --db main - | grep -v '^DEFINE ACCESS' > data/harbor.surql
ls -lh data/harbor.surql
