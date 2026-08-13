from collections.abc import Generator
from pathlib import Path

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

    try:
        make_url(value)
    except ArgumentError as exc:
        raise DatabaseConfigurationError(
            "Invalid DATABASE_URL. Expected a SQLAlchemy URL such as "
            "postgresql://user:password@host:5432/database or sqlite:///./data/soutlead.db."
        ) from exc
    return value


class Database:
    def __init__(self, database_url: str) -> None:
        database_url = normalize_database_url(database_url)
        if database_url.startswith("sqlite:///"):
            path = database_url.removeprefix("sqlite:///")
            if path and path != ":memory:":
                Path(path).parent.mkdir(parents=True, exist_ok=True)

        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        self.engine = create_engine(database_url, connect_args=connect_args)
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
