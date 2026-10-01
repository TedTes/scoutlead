import os


# App import constructs the service container, which requires a syntactically valid
# PostgreSQL URL even when tests do not open a database connection.
if not os.getenv("DATABASE_URL", "").strip():
    os.environ["DATABASE_URL"] = "postgresql://test:test@localhost:5432/scoutlead_test"

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("AUTO_CREATE_TABLES", "false")
