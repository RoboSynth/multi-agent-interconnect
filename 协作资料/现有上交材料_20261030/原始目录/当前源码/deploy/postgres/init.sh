#!/bin/sh
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --set=app_password="$ORDERS_DB_PASSWORD" <<'SQL'
CREATE ROLE orders_app LOGIN;
ALTER ROLE orders_app PASSWORD :'app_password';
\i /schema/orders.sql
GRANT CONNECT ON DATABASE orders TO orders_app;
GRANT USAGE ON SCHEMA public TO orders_app;
GRANT SELECT, INSERT, UPDATE ON orders TO orders_app;
GRANT SELECT, INSERT ON operation_receipts TO orders_app;
SQL
if [ -n "${BRIDGE_DB_PASSWORD:-}" ]; then
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    --set=bridge_password="$BRIDGE_DB_PASSWORD" <<'SQL'
\i /schema/bridge.sql
ALTER ROLE bridge_operator PASSWORD :'bridge_password';
SQL
fi
