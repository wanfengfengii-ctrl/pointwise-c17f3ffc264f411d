import json
import sqlite3

from forecast.snapshot import ForecastSnapshot, forecast_piece_payload, forecast_snapshot_from_payload
from sqlite_tx import write_transaction
from study.identity import validate_identifier


class ForecastStore:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self.initialize()

    def initialize(self) -> None:
        with write_transaction(self.connection):
            self.connection.execute('''
                CREATE TABLE IF NOT EXISTS forecast_revisions (
                    batch_id TEXT NOT NULL,
                    revision_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (batch_id, revision_id)
                )
            ''')

    def save_or_recall(self, snapshot: ForecastSnapshot) -> ForecastSnapshot:
        key = (snapshot.roster.batch_id, snapshot.revision_id)
        payload = json.dumps(forecast_piece_payload(snapshot), sort_keys=True, separators=(',', ':'))
        with write_transaction(self.connection):
            original = self._find_payload(key)
            if original is None:
                self.connection.execute(
                    '''INSERT INTO forecast_revisions (batch_id, revision_id, payload)
                       VALUES (?, ?, ?)''',
                    (*key, payload),
                )
                return snapshot
            if original != payload:
                raise ValueError('revision identifier already has different forecast content')
            return forecast_snapshot_from_payload(json.loads(original))

    def load_revision(self, batch_id: str, revision_id: str) -> ForecastSnapshot:
        key = (validate_identifier(batch_id, 'batch_id'),
               validate_identifier(revision_id, 'revision_id'))
        payload = self._find_payload(key)
        if payload is None:
            raise KeyError(key)
        return forecast_snapshot_from_payload(json.loads(payload))

    def _find_payload(self, key: tuple[str, str]) -> str | None:
        row = self.connection.execute(
            'SELECT payload FROM forecast_revisions WHERE batch_id = ? AND revision_id = ?', key
        ).fetchone()
        return None if row is None else row[0]
