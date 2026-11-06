#!/usr/bin/env bash
# Regenerate tests/fixtures/anonymize/{mysql_dump.sql,pg_dump.sql}.
#
# Starts throwaway mariadb:11 / postgres:16 containers, loads the synthetic
# seeds, dumps with the same tools `jarvis db` uses (mariadb-dump defaults,
# pg_dump plain text) and removes the containers again.
#
#   bash tests/fixtures/anonymize/make_fixtures.sh
#
# Needs docker; the first run pulls the images. No production data is involved.
set -euo pipefail

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
mysql_image=${MYSQL_IMAGE:-mariadb:11}
pg_image=${PG_IMAGE:-postgres:16}
password=test
mysql_name="jarvis-anon-fixtures-mysql-$$"
pg_name="jarvis-anon-fixtures-pg-$$"

command -v docker >/dev/null || { echo "docker is required" >&2; exit 1; }

cleanup() {
  docker rm -f "$mysql_name" "$pg_name" >/dev/null 2>&1 || true
}
trap cleanup EXIT

wait_mysql() {
  local attempt
  for attempt in $(seq 1 120); do
    if docker logs "$mysql_name" 2>&1 | grep -q "MariaDB init process done" &&
      docker exec "$mysql_name" mariadb -uroot -p"$password" -e 'SELECT 1' \
        >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  echo "mariadb did not become ready" >&2
  docker logs "$mysql_name" >&2 || true
  return 1
}

wait_pg() {
  local attempt
  for attempt in $(seq 1 120); do
    if docker logs "$pg_name" 2>&1 | grep -q "PostgreSQL init process complete" &&
      docker exec "$pg_name" psql -U postgres -d postgres -c 'SELECT 1' \
        >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  echo "postgres did not become ready" >&2
  docker logs "$pg_name" >&2 || true
  return 1
}

echo "== mariadb: seeding ==" >&2
docker run -d --name "$mysql_name" -e MARIADB_ROOT_PASSWORD="$password" \
  "$mysql_image" >/dev/null
wait_mysql
docker exec "$mysql_name" mariadb -uroot -p"$password" \
  -e 'CREATE DATABASE koha_fixture CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci'
docker exec -i "$mysql_name" mariadb -uroot -p"$password" \
  --default-character-set=utf8mb4 koha_fixture < "$here/seed_mysql.sql"
echo "== mariadb: dumping ==" >&2
docker exec "$mysql_name" mariadb-dump -uroot -p"$password" koha_fixture \
  >"$here/mysql_dump.sql"

echo "== postgres: seeding ==" >&2
docker run -d --name "$pg_name" -e POSTGRES_PASSWORD="$password" \
  "$pg_image" >/dev/null
wait_pg
docker exec "$pg_name" psql -U postgres -d postgres -v ON_ERROR_STOP=1 \
  -c 'CREATE DATABASE dspace_fixture'
docker exec -i "$pg_name" psql -U postgres -d dspace_fixture \
  -v ON_ERROR_STOP=1 <"$here/seed_pg.sql"
echo "== postgres: dumping ==" >&2
docker exec "$pg_name" pg_dump -U postgres -d dspace_fixture \
  >"$here/pg_dump.sql"

echo "== checks ==" >&2
printf 'mysql_dump.sql: %s borrowers INSERT statements\n' \
  "$(grep -c '^INSERT INTO `borrowers`' "$here/mysql_dump.sql" || true)"
printf 'pg_dump.sql: %s public.eperson COPY headers\n' \
  "$(grep -c '^COPY public.eperson ' "$here/pg_dump.sql" || true)"
if grep -q '^\\restrict' "$here/pg_dump.sql"; then
  echo 'pg_dump.sql: contains \restrict'
else
  echo 'pg_dump.sql: contains no \restrict line'
fi
du -h "$here/mysql_dump.sql" "$here/pg_dump.sql"
