-- Development-only helper: run this once against your local PostgreSQL install
-- as the postgres superuser to create the role/database this backend's .env
-- expects, and to enable PostGIS on it.
--
-- Example from the repository root:
--   psql -U postgres -h 127.0.0.1 -p 5432 -v oilspill_password="<local-dev-password>" -f backend\scripts\local_postgres_setup.sql
--
-- It will prompt for the postgres superuser password you set at install time.
-- Do not commit real local passwords.

\if :{?oilspill_password}
\else
  \echo 'Missing required psql variable: oilspill_password'
  \echo 'Example: psql -U postgres -h 127.0.0.1 -p 5432 -v oilspill_password="<local-dev-password>" -f backend\scripts\local_postgres_setup.sql'
  \quit 1
\endif

SELECT format('CREATE ROLE oilspill_user LOGIN PASSWORD %L', :'oilspill_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'oilspill_user')
\gexec

SELECT 'CREATE DATABASE oilspill OWNER oilspill_user'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'oilspill')
\gexec

\connect oilspill
CREATE EXTENSION IF NOT EXISTS postgis;
GRANT ALL PRIVILEGES ON DATABASE oilspill TO oilspill_user;
GRANT ALL ON SCHEMA public TO oilspill_user;
