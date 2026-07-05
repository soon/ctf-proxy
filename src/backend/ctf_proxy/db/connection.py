import os

import psycopg
from psycopg.rows import RowMaker

SEARCH_PATH = "logs,analytics,dashboard,public"


def nul_safe(value):
    if isinstance(value, str):
        return value.replace("\x00", "")
    return value


def dsn(statement_timeout_ms: int | None = None) -> str:
    host = os.environ.get("PGHOST", "localhost")
    port = os.environ.get("PGPORT", "5433")
    user = os.environ.get("PGUSER", "ctf")
    password = os.environ.get("PGPASSWORD", "ctf")
    database = os.environ.get("PGDATABASE", "ctf")
    options = f"-c search_path={SEARCH_PATH}"
    if statement_timeout_ms is not None:
        options += f" -c statement_timeout={statement_timeout_ms}"
    return (
        f"host={host} port={port} user={user} password={password} "
        f"dbname={database} options='{options}'"
    )


def describe() -> str:
    host = os.environ.get("PGHOST", "localhost")
    port = os.environ.get("PGPORT", "5433")
    database = os.environ.get("PGDATABASE", "ctf")
    return f"postgresql://{host}:{port}/{database}"


class Row:
    def __init__(self, columns, values):
        self.columns = columns
        self.values = values
        self.mapping = dict(zip(columns, values, strict=False))

    def __getitem__(self, key):
        return self.values[key] if isinstance(key, int | slice) else self.mapping[key]

    def __iter__(self):
        return iter(self.values)

    def __len__(self):
        return len(self.values)

    def __eq__(self, other):
        if isinstance(other, Row):
            return self.values == other.values
        if isinstance(other, tuple):
            return tuple(self.values) == other
        if isinstance(other, list):
            return list(self.values) == other
        return NotImplemented

    __hash__ = None

    def __repr__(self):
        return f"Row({self.mapping!r})"

    def keys(self):
        return list(self.columns)

    def get(self, key, default=None):
        return self.mapping.get(key, default)


def row_factory(cursor) -> RowMaker:
    description = cursor.description
    columns = [col.name for col in description] if description else []

    def make_row(values) -> Row:
        return Row(columns, values)

    return make_row


def connect(statement_timeout_ms: int | None = None) -> psycopg.Connection:
    return psycopg.connect(dsn(statement_timeout_ms), row_factory=row_factory)
