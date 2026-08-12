from collections.abc import Generator
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from db.base import Base


class Database:
    def __init__(self, database_url: str) -> None:
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
