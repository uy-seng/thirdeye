from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy import event
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

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


STARTUP_MIGRATIONS = (
    "0001_rebuild_jobs_schema",
    "0002_add_operations_and_artifact_manifest",
    "0003_add_voice_notes",
)


def run_startup_migrations(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT NOT NULL PRIMARY KEY,
                applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        applied = {row[0] for row in connection.exec_driver_sql("SELECT version FROM schema_migrations")}
        if "0001_rebuild_jobs_schema" not in applied:
            _rebuild_table_if_columns_differ(connection, "jobs")
            connection.exec_driver_sql("INSERT INTO schema_migrations (version) VALUES ('0001_rebuild_jobs_schema')")
        if "0002_add_operations_and_artifact_manifest" not in applied:
            for table_name in ("operations", "artifact_manifest"):
                table = Base.metadata.tables.get(table_name)
                if table is not None:
                    table.create(connection, checkfirst=True)
            connection.exec_driver_sql("INSERT INTO schema_migrations (version) VALUES ('0002_add_operations_and_artifact_manifest')")
        if "0003_add_voice_notes" not in applied:
            table = Base.metadata.tables.get("voice_notes")
            if table is not None:
                table.create(connection, checkfirst=True)
            connection.exec_driver_sql("INSERT INTO schema_migrations (version) VALUES ('0003_add_voice_notes')")


def _rebuild_table_if_columns_differ(connection, table_name: str) -> None:
    table = Base.metadata.tables[table_name]
    existing_table = connection.exec_driver_sql(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).first()
    if existing_table is None:
        table.create(connection, checkfirst=True)
        return

    existing_columns = [row[1] for row in connection.exec_driver_sql(f"PRAGMA table_info({_quote_identifier(table_name)})")]
    expected_columns = [column.name for column in table.columns]
    if existing_columns == expected_columns:
        return

    temp_table_name = f"_{table_name}_migration_new"
    connection.exec_driver_sql(f"DROP TABLE IF EXISTS {_quote_identifier(temp_table_name)}")
    temp_table = table.to_metadata(Base.metadata.__class__(), name=temp_table_name)
    temp_table.create(connection)

    common_columns = [column for column in expected_columns if column in existing_columns]
    insert_columns_sql = ", ".join(_quote_identifier(column) for column in expected_columns)
    select_columns_sql = ", ".join(
        _quote_identifier(column) if column in common_columns else _default_sql_literal(table.columns[column])
        for column in expected_columns
    )
    connection.exec_driver_sql(
        f"INSERT INTO {_quote_identifier(temp_table_name)} ({insert_columns_sql}) "
        f"SELECT {select_columns_sql} FROM {_quote_identifier(table_name)}"
    )
    connection.exec_driver_sql(f"DROP TABLE {_quote_identifier(table_name)}")
    connection.exec_driver_sql(f"ALTER TABLE {_quote_identifier(temp_table_name)} RENAME TO {_quote_identifier(table_name)}")


def _default_sql_literal(column) -> str:
    if column.nullable:
        return "NULL"
    default = column.default.arg if column.default is not None else None
    if isinstance(default, bool):
        return "1" if default else "0"
    if isinstance(default, int):
        return str(default)
    if isinstance(default, str):
        return "'" + default.replace("'", "''") + "'"
    return "0"


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'
