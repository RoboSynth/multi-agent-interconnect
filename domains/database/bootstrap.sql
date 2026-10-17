-- Execute as the disposable lab database administrator, never the coordinator.
-- Role passwords must be provisioned by the deployment environment, not here.
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'bridge_operator') THEN
    CREATE ROLE bridge_operator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
  END IF;
END $$;
ALTER ROLE bridge_operator NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
GRANT CONNECT ON DATABASE orders TO bridge_operator;
GRANT pg_read_all_stats TO bridge_operator;
CREATE SCHEMA IF NOT EXISTS incident_ops;
REVOKE ALL ON SCHEMA incident_ops FROM PUBLIC;
GRANT USAGE ON SCHEMA incident_ops TO bridge_operator;

CREATE OR REPLACE FUNCTION incident_ops.restore_writes() RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
  ALTER ROLE orders_app SET default_transaction_read_only = off;
  ALTER DATABASE orders SET default_transaction_read_only = off;
  RETURN false;
END $$;
REVOKE ALL ON FUNCTION incident_ops.restore_writes() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION incident_ops.restore_writes() TO bridge_operator;

CREATE OR REPLACE FUNCTION incident_ops.terminate_blocker(target_pid integer) RETURNS boolean
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_stat_activity blocker
    WHERE blocker.pid = target_pid AND blocker.usename = 'orders_app'
      AND blocker.datname = 'orders' AND blocker.pid <> pg_backend_pid()
      AND EXISTS (SELECT 1 FROM pg_stat_activity waiter
          WHERE waiter.datname = 'orders' AND waiter.usename = 'orders_app'
            AND target_pid = ANY(pg_blocking_pids(waiter.pid)))) THEN
    RAISE EXCEPTION 'target is not an authorized experiment blocker';
  END IF;
  RETURN pg_terminate_backend(target_pid);
END $$;
REVOKE ALL ON FUNCTION incident_ops.terminate_blocker(integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION incident_ops.terminate_blocker(integer) TO bridge_operator;

ALTER ROLE bridge_operator SET statement_timeout = '10s';
ALTER ROLE bridge_operator SET lock_timeout = '3s';
-- The MCP process has CONNECT, monitoring and these two functions only. It is
-- not an orders table owner and receives no DDL, DML, CREATEDB or CREATEROLE.
