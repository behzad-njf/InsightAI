-- InsightAI — PostgreSQL read-only role for AI query execution
-- Runs once on first container start (docker-entrypoint-initdb.d).
-- Production CampusMetrics uses MSSQL; this is for local Docker development only.

\set ON_ERROR_STOP on

-- Read-only login used by INSIGHTAI_DATABASE_READONLY_URL in Docker Compose
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'insightai_readonly') THEN
        CREATE ROLE insightai_readonly LOGIN PASSWORD 'insightai_readonly';
    END IF;
END
$$;

GRANT CONNECT ON DATABASE insightai TO insightai_readonly;
GRANT USAGE ON SCHEMA public TO insightai_readonly;

-- Existing objects (run after sample tables in 02-sample-schema.sql)
GRANT SELECT ON ALL TABLES IN SCHEMA public TO insightai_readonly;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO insightai_readonly;

-- Future tables created by the app owner (POSTGRES_USER=insightai)
ALTER DEFAULT PRIVILEGES FOR ROLE insightai IN SCHEMA public
    GRANT SELECT ON TABLES TO insightai_readonly;
ALTER DEFAULT PRIVILEGES FOR ROLE insightai IN SCHEMA public
    GRANT SELECT ON SEQUENCES TO insightai_readonly;

-- Prevent writes explicitly
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
    ON ALL TABLES IN SCHEMA public FROM insightai_readonly;
