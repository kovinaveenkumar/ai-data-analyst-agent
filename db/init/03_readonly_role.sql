-- =====================================================================
-- Read-only role used by the MCP server. Layer 1 of the safety design:
-- even if a harmful query slipped past the SQL validator, the database
-- itself refuses to write.
-- (Change the password for any shared or hosted deployment.)
-- =====================================================================
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'analyst_ro') THEN
    CREATE ROLE analyst_ro LOGIN PASSWORD 'analyst_ro_pw';
  END IF;
END $$;

GRANT USAGE ON SCHEMA shop TO analyst_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA shop TO analyst_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA shop GRANT SELECT ON TABLES TO analyst_ro;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

ALTER ROLE analyst_ro SET default_transaction_read_only = on;
ALTER ROLE analyst_ro SET statement_timeout = '30s';
ALTER ROLE analyst_ro SET search_path = shop;
