import sqlite3

from sqlite_tx import write_transaction
from study.identity import validate_identifier
from study.roster import Roster


class StudyStore:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self.initialize()

    def initialize(self) -> None:
        self.connection.execute('PRAGMA foreign_keys = ON')
        with write_transaction(self.connection):
            self.connection.execute('''
                CREATE TABLE IF NOT EXISTS study_batches (
                    batch_id TEXT PRIMARY KEY NOT NULL,
                    roster_id TEXT NOT NULL
                )
            ''')
            self.connection.execute('''
                CREATE TABLE IF NOT EXISTS study_specimens (
                    batch_id TEXT NOT NULL REFERENCES study_batches(batch_id),
                    position INTEGER NOT NULL CHECK (position >= 0),
                    specimen_id TEXT NOT NULL,
                    PRIMARY KEY (batch_id, position),
                    UNIQUE (batch_id, specimen_id)
                )
            ''')

    def save_roster(self, roster: Roster) -> Roster:
        with write_transaction(self.connection):
            try:
                original = self.load_roster(roster.batch_id)
            except KeyError:
                self.connection.execute(
                    'INSERT INTO study_batches (batch_id, roster_id) VALUES (?, ?)',
                    (roster.batch_id, roster.roster_id),
                )
                self.connection.executemany(
                    '''INSERT INTO study_specimens (batch_id, position, specimen_id)
                       VALUES (?, ?, ?)''',
                    ((roster.batch_id, index, name)
                     for index, name in enumerate(roster.specimens)),
                )
                return roster
            if original != roster:
                raise ValueError('batch already has a different ordered roster')
            return original

    def load_roster(self, batch_id: str) -> Roster:
        batch = validate_identifier(batch_id, 'batch_id')
        rows = self.connection.execute('''
            SELECT b.roster_id, s.specimen_id
            FROM study_batches AS b JOIN study_specimens AS s USING (batch_id)
            WHERE b.batch_id = ? ORDER BY s.position
        ''', (batch,)).fetchall()
        if not rows:
            raise KeyError(batch)
        return Roster(batch, rows[0][0], tuple(row[1] for row in rows))
