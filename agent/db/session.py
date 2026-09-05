from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session, sessionmaker

from db.base import Base


class DatabaseConfigurationError(RuntimeError):
    pass


def normalize_database_url(database_url: str) -> str:
    value = (database_url or "").strip().strip('"').strip("'")
    if not value:
        raise DatabaseConfigurationError(
            "DATABASE_URL is empty. Set it to the Railway Postgres DATABASE_URL reference."
        )
    if value.startswith("${{") or value.startswith("$"):
        raise DatabaseConfigurationError(
            "DATABASE_URL is an unresolved variable reference. In Railway, set DATABASE_URL "
            "from the Postgres service variable reference, for example ${{postgres.DATABASE_URL}}."
        )
    if value.startswith("postgres://"):
        value = f"postgresql+psycopg://{value.removeprefix('postgres://')}"
    elif value.startswith("postgresql://"):
        value = f"postgresql+psycopg://{value.removeprefix('postgresql://')}"
    elif not value.startswith("postgresql+psycopg://"):
        raise DatabaseConfigurationError(
            "Invalid DATABASE_URL. Set it to a Postgres URL such as "
            "postgresql://user:password@host:5432/database."
        )

    try:
        make_url(value)
    except ArgumentError as exc:
        raise DatabaseConfigurationError(
            "Invalid DATABASE_URL. Set it to a Postgres URL such as "
            "postgresql://user:password@host:5432/database."
        ) from exc
    return value


class Database:
    def __init__(self, database_url: str) -> None:
        database_url = normalize_database_url(database_url)
        self.engine = create_engine(database_url)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)

    def session(self) -> Generator[Session, None, None]:
        db = self.session_factory()
        try:
            yield db
        finally:
            db.close()


def create_database(engine: Engine) -> None:
    import db.models  # noqa: F401

    _ensure_pgvector_extension(engine)
    Base.metadata.create_all(bind=engine)
    _ensure_product_source_columns(engine)
    _ensure_campaign_runtime_columns(engine)
    _ensure_lead_review_columns(engine)
    _ensure_lead_verification_columns(engine)
    _ensure_canonical_contact_columns(engine)
    _ensure_business_semantic_columns(engine)
    _ensure_product_workspace_columns(engine)


def _ensure_pgvector_extension(engine: Engine) -> None:
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))


def _ensure_product_source_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    if not inspector.has_table("products"):
        return

    existing_columns = {column["name"] for column in inspector.get_columns("products")}
    dialect = engine.dialect.name
    source_last_checked_type = "TIMESTAMP WITH TIME ZONE" if dialect == "postgresql" else "DATETIME"
    source_evidence_type = "JSONB" if dialect == "postgresql" else "JSON"
    columns = {
        "source_url": "VARCHAR(1000)",
        "source_fingerprint": "VARCHAR(255)",
        "source_last_checked_at": source_last_checked_type,
        "source_evidence": source_evidence_type,
    }

    existing_indexes = {index["name"]: index for index in inspector.get_indexes("products")}
    with engine.begin() as connection:
        for column_name, column_type in columns.items():
            if column_name not in existing_columns:
                connection.execute(text(f"ALTER TABLE products ADD COLUMN {column_name} {column_type}"))
        if "ix_products_source_fingerprint" not in existing_indexes:
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_products_source_fingerprint "
                    "ON products (source_fingerprint)"
                )
            )


def _ensure_campaign_runtime_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    if not inspector.has_table("campaigns"):
        return

    existing_columns = {column["name"] for column in inspector.get_columns("campaigns")}
    with engine.begin() as connection:
        if "goal_type" not in existing_columns:
            connection.execute(text("ALTER TABLE campaigns ADD COLUMN goal_type VARCHAR(32)"))
            connection.execute(text("UPDATE campaigns SET goal_type = 'learn' WHERE goal_type IS NULL"))
        if "icp_preset_id" not in existing_columns:
            connection.execute(text("ALTER TABLE campaigns ADD COLUMN icp_preset_id VARCHAR(255)"))
        if "source_preset_id" not in existing_columns:
            connection.execute(text("ALTER TABLE campaigns ADD COLUMN source_preset_id VARCHAR(255)"))


def _ensure_lead_review_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    if not inspector.has_table("leads"):
        return

    existing_columns = {column["name"] for column in inspector.get_columns("leads")}
    dialect = engine.dialect.name
    timestamp_type = "TIMESTAMP WITH TIME ZONE" if dialect == "postgresql" else "DATETIME"
    with engine.begin() as connection:
        if "review_status" not in existing_columns:
            connection.execute(text("ALTER TABLE leads ADD COLUMN review_status VARCHAR(32)"))
            connection.execute(text("UPDATE leads SET review_status = 'unreviewed' WHERE review_status IS NULL"))
        if "review_note" not in existing_columns:
            connection.execute(text("ALTER TABLE leads ADD COLUMN review_note TEXT"))
        if "reviewed_at" not in existing_columns:
            connection.execute(text(f"ALTER TABLE leads ADD COLUMN reviewed_at {timestamp_type}"))
        if "shortlisted_at" not in existing_columns:
            connection.execute(text(f"ALTER TABLE leads ADD COLUMN shortlisted_at {timestamp_type}"))


def _ensure_lead_verification_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    if not inspector.has_table("leads"):
        return

    existing_columns = {column["name"] for column in inspector.get_columns("leads")}
    dialect = engine.dialect.name
    timestamp_type = "TIMESTAMP WITH TIME ZONE" if dialect == "postgresql" else "DATETIME"
    with engine.begin() as connection:
        if "verification_status" not in existing_columns:
            connection.execute(text("ALTER TABLE leads ADD COLUMN verification_status VARCHAR(32)"))
            connection.execute(
                text("UPDATE leads SET verification_status = 'unverified' WHERE verification_status IS NULL")
            )
        if "verification_provider" not in existing_columns:
            connection.execute(text("ALTER TABLE leads ADD COLUMN verification_provider VARCHAR(255)"))
        if "verification_checked_at" not in existing_columns:
            connection.execute(text(f"ALTER TABLE leads ADD COLUMN verification_checked_at {timestamp_type}"))
        if "verification_reason" not in existing_columns:
            connection.execute(text("ALTER TABLE leads ADD COLUMN verification_reason TEXT"))
        if "verification_score" not in existing_columns:
            connection.execute(text("ALTER TABLE leads ADD COLUMN verification_score INTEGER"))


def _ensure_canonical_contact_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    if not inspector.has_table("leads"):
        return

    existing_columns = {column["name"] for column in inspector.get_columns("leads")}
    existing_indexes = {index["name"] for index in inspector.get_indexes("leads")}
    with engine.begin() as connection:
        if "business_id" not in existing_columns:
            connection.execute(text("ALTER TABLE leads ADD COLUMN business_id VARCHAR(64)"))
        if "contact_id" not in existing_columns:
            connection.execute(text("ALTER TABLE leads ADD COLUMN contact_id VARCHAR(64)"))
        if "ix_leads_business_id" not in existing_indexes:
            connection.execute(
                text("CREATE INDEX IF NOT EXISTS ix_leads_business_id ON leads (business_id)")
            )
        if "ix_leads_contact_id" not in existing_indexes:
            connection.execute(
                text("CREATE INDEX IF NOT EXISTS ix_leads_contact_id ON leads (contact_id)")
            )


def _ensure_business_semantic_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    if not inspector.has_table("businesses"):
        return

    dialect = engine.dialect.name
    existing_columns = {column["name"] for column in inspector.get_columns("businesses")}
    existing_indexes = {index["name"] for index in inspector.get_indexes("businesses")}
    timestamp_type = "TIMESTAMP WITH TIME ZONE" if dialect == "postgresql" else "DATETIME"
    embedding_type = "vector(1536)" if dialect == "postgresql" else "JSON"
    with engine.begin() as connection:
        if "category_key" not in existing_columns:
            connection.execute(text("ALTER TABLE businesses ADD COLUMN category_key VARCHAR(255)"))
        if "market_key" not in existing_columns:
            connection.execute(text("ALTER TABLE businesses ADD COLUMN market_key VARCHAR(255)"))
        if "semantic_text" not in existing_columns:
            connection.execute(text("ALTER TABLE businesses ADD COLUMN semantic_text TEXT"))
        if "embedding" not in existing_columns:
            connection.execute(
                text(f"ALTER TABLE businesses ADD COLUMN embedding {embedding_type}")
            )
        if "embedding_model" not in existing_columns:
            connection.execute(
                text("ALTER TABLE businesses ADD COLUMN embedding_model VARCHAR(255)")
            )
        if "embedding_updated_at" not in existing_columns:
            connection.execute(
                text(f"ALTER TABLE businesses ADD COLUMN embedding_updated_at {timestamp_type}")
            )
        if "ix_businesses_category_key" not in existing_indexes:
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_businesses_category_key "
                    "ON businesses (category_key)"
                )
            )
        if "ix_businesses_market_key" not in existing_indexes:
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_businesses_market_key "
                    "ON businesses (market_key)"
                )
            )


def _ensure_product_workspace_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    if not inspector.has_table("products") or not inspector.has_table("workspaces"):
        return

    existing_columns = {column["name"] for column in inspector.get_columns("products")}
    existing_indexes = {index["name"]: index for index in inspector.get_indexes("products")}
    existing_uniques = {constraint["name"] for constraint in inspector.get_unique_constraints("products")}
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO workspaces (id, name, clerk_organization_id, created_at, updated_at)
                SELECT 'workspace_default', 'Default workspace', NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                WHERE NOT EXISTS (SELECT 1 FROM workspaces WHERE id = 'workspace_default')
                """
            )
        )
        if "workspace_id" not in existing_columns:
            connection.execute(text("ALTER TABLE products ADD COLUMN workspace_id VARCHAR(255)"))
        connection.execute(
            text("UPDATE products SET workspace_id = 'workspace_default' WHERE workspace_id IS NULL")
        )
        source_index = existing_indexes.get("ix_products_source_fingerprint")
        if source_index and source_index.get("unique"):
            connection.execute(text("DROP INDEX IF EXISTS ix_products_source_fingerprint"))
            existing_indexes.pop("ix_products_source_fingerprint", None)
        if "ix_products_source_fingerprint" not in existing_indexes:
            connection.execute(
                text("CREATE INDEX IF NOT EXISTS ix_products_source_fingerprint ON products (source_fingerprint)")
            )
        if "ix_products_workspace_id" not in existing_indexes:
            connection.execute(
                text("CREATE INDEX IF NOT EXISTS ix_products_workspace_id ON products (workspace_id)")
            )
        if (
            "uq_products_workspace_source_fingerprint" not in existing_uniques
            and "ix_products_workspace_source_fingerprint_unique" not in existing_indexes
        ):
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_products_workspace_source_fingerprint_unique "
                    "ON products (workspace_id, source_fingerprint)"
                )
            )
