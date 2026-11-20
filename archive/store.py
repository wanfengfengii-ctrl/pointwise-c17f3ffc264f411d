import sqlite3

from sqlite_tx import write_transaction
from study.identity import validate_identifier


class ArchiveStore:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self.initialize()

    def initialize(self) -> None:
        self.connection.execute('PRAGMA foreign_keys = ON')
        with write_transaction(self.connection):
            self.connection.execute('''
                CREATE TABLE IF NOT EXISTS review_reports (
                    id INTEGER PRIMARY KEY,
                    body TEXT NOT NULL
                )
            ''')
            self.connection.execute('''
                CREATE TABLE IF NOT EXISTS review_receipts (
                    report_id INTEGER PRIMARY KEY REFERENCES review_reports(id)
                )
            ''')

    def commit_review(self, body: str) -> str:
        with write_transaction(self.connection):
            report = self.connection.execute('INSERT INTO review_reports (body) VALUES (?)', (body,))
            number = report.lastrowid
            self.connection.execute('INSERT INTO review_receipts (report_id) VALUES (?)', (number,))
        return f'review-{number}'

    def load_review(self, report_id: str) -> tuple[str, str]:
        token = validate_identifier(report_id, 'report_id')
        row = self.connection.execute('''
            SELECT reports.body, receipts.report_id
            FROM review_reports AS reports
            JOIN review_receipts AS receipts ON receipts.report_id = reports.id
            WHERE reports.id = ?
        ''', (token.removeprefix('review-'),)).fetchone()
        if row is None or token != f'review-{row[1]}':
            raise KeyError(token)
        return row[0], f'review-{row[1]}'
