-- Minimal sample schema for local Docker testing (mirrors naming from CampusMetrics docs).
\set ON_ERROR_STOP on

CREATE TABLE IF NOT EXISTS accounts_user (
    id BIGSERIAL PRIMARY KEY,
    email TEXT NOT NULL,
    first_name TEXT,
    last_name TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

INSERT INTO accounts_user (email, first_name, last_name, is_active)
SELECT 'parent@example.com', 'Pat', 'Parent', TRUE
WHERE NOT EXISTS (SELECT 1 FROM accounts_user WHERE email = 'parent@example.com');

INSERT INTO accounts_user (email, first_name, last_name, is_active)
SELECT 'child@example.com', 'Chris', 'Child', TRUE
WHERE NOT EXISTS (SELECT 1 FROM accounts_user WHERE email = 'child@example.com');

-- Ensure readonly role can SELECT new tables
GRANT SELECT ON ALL TABLES IN SCHEMA public TO insightai_readonly;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO insightai_readonly;
