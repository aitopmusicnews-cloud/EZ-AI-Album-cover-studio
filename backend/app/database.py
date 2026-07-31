from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


@dataclass(slots=True)
class Database:
    engine: object
    session_factory: sessionmaker[Session]

    def create_all(self) -> None:
        Base.metadata.create_all(self.engine)

    def session(self) -> Generator[Session, None, None]:
        db = self.session_factory()
        try:
            yield db
        finally:
            db.close()


def create_database(database_url: str) -> Database:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, connect_args=connect_args, future=True)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
    return Database(engine=engine, session_factory=factory)
