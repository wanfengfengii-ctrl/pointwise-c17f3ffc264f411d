"""SQLite write transactions shared by the laboratory stores."""

from collections.abc import Iterator
from contextlib import contextmanager
import sqlite3


@contextmanager
def write_transaction(connection: sqlite3.Connection) -> Iterator[None]:
    """Acquire the write reservation before reading state to be changed."""
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
