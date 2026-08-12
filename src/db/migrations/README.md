Alembic migrations belong here.

The first local implementation uses `Base.metadata.create_all` on startup so the API can run immediately. For production, initialize Alembic and generate migrations from the SQLAlchemy models before deploying schema changes.
