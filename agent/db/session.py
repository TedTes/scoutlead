from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
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

    Base.metadata.create_all(bind=engine)
