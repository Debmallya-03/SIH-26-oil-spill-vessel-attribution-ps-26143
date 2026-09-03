-- Run this once against your local PostgreSQL 18 install (as the postgres
-- superuser) to create the role/database this backend's .env expects, and
-- to enable PostGIS on it.
--
--   & "C:\Program Files\PostgreSQL\18\bin\psql.exe" -U postgres -h 127.0.0.1 -p 5432 -f backend\scripts\local_postgres_setup.sql
--
-- It will prompt for the postgres superuser password you set at install time.

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'oilspill_user') THEN
        CREATE ROLE oilspill_user LOGIN PASSWORD 'oilspill_dev_password';
    END IF;
END
$$;

SELECT 'CREATE DATABASE oilspill OWNER oilspill_user'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'oilspill')
\gexec

\connect oilspill
CREATE EXTENSION IF NOT EXISTS postgis;
GRANT ALL PRIVILEGES ON DATABASE oilspill TO oilspill_user;
GRANT ALL ON SCHEMA public TO oilspill_user;
