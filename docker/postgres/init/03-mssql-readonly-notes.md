# MSSQL read-only user (CampusMetrics production)

Docker Compose in this repo uses **PostgreSQL for local development**.
Your production schema (`schema/database_schema.md`) targets **Microsoft SQL Server (CampusMetrics)**.

Create a dedicated read-only login on the customer SQL Server instance:

```sql
-- Example (adjust names/passwords; run as admin on campus_analytics database)
CREATE LOGIN insightai_readonly WITH PASSWORD = 'strong-password-here';
USE campus_analytics;
CREATE USER insightai_readonly FOR LOGIN insightai_readonly;

-- Database-level read
ALTER ROLE db_datareader ADD MEMBER insightai_readonly;

-- Optional: deny writes explicitly
DENY INSERT, UPDATE, DELETE ON SCHEMA::dbo TO insightai_readonly;
```

Set in `.env`:

```env
INSIGHTAI_DATABASE_KIND=mssql
INSIGHTAI_DATABASE_READONLY_URL=mssql+pyodbc://insightai_readonly:PASSWORD@HOST:1433/campus_analytics?driver=ODBC+Driver+17+for+SQL+Server
```

The API Docker image does **not** include ODBC drivers for MSSQL. Run the API on the host (or a custom image with `pyodbc` + Microsoft ODBC Driver 17) when connecting to CampusMetrics.
