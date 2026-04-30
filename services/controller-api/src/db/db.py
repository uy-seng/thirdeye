from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def create_session_factory(database_path: Path) -> sessionmaker:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{database_path}",
        future=True,
        connect_args={"check_same_thread": False},
    )
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def ensure_schema_compatibility(engine: Engine) -> None:
    with engine.begin() as connection:
        jobs_table = connection.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'jobs'"
        ).first()
        if jobs_table is None:
            return

        columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(jobs)")}
        expected_columns = set(Base.metadata.tables["jobs"].columns.keys())
        for column in sorted(columns - expected_columns):
            connection.exec_driver_sql(f'ALTER TABLE jobs DROP COLUMN {_quote_identifier(column)}')


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'
