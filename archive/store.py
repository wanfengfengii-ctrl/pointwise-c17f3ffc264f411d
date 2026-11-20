"""Archive storage for original reviews and formally issued replacements."""

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
            self.connection.execute('''
                CREATE TABLE IF NOT EXISTS replacement_catalog (
                    report_id INTEGER PRIMARY KEY REFERENCES review_reports(id),
                    original_report_id TEXT NOT NULL,
                    amendment_accession TEXT NOT NULL,
                    UNIQUE (original_report_id, amendment_accession)
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
            LEFT JOIN replacement_catalog AS catalog ON catalog.report_id = reports.id
            WHERE reports.id = ? AND catalog.report_id IS NULL
        ''', (token.removeprefix('review-'),)).fetchone()
        if row is None or token != f'review-{row[1]}':
            raise KeyError(token)
        return row[0], f'review-{row[1]}'

    def find_replacement(self, original_report_id: str, amendment_accession: str) -> str | None:
        row = self.connection.execute('''
            SELECT reports.body FROM replacement_catalog AS catalog
            JOIN review_reports AS reports ON reports.id = catalog.report_id
            WHERE catalog.original_report_id = ? AND catalog.amendment_accession = ?
        ''', (original_report_id, amendment_accession)).fetchone()
        return None if row is None else row[0]

    def commit_replacement(
        self, original_report_id: str, amendment_accession: str, build_body
    ) -> str:
        """Number, write body, associations and receipt in one archive transaction."""
        with write_transaction(self.connection):
            stored = self.connection.execute('''
                SELECT reports.id FROM replacement_catalog AS catalog
                JOIN review_reports AS reports ON reports.id = catalog.report_id
                WHERE catalog.original_report_id = ? AND catalog.amendment_accession = ?
            ''', (original_report_id, amendment_accession)).fetchone()
            if stored is not None:
                return f'review-{stored[0]}'
            number = self.connection.execute(
                'SELECT coalesce(max(id), 0) + 1 FROM review_reports'
            ).fetchone()[0]
            text = build_body(f'review-{number}')
            self.connection.execute(
                'INSERT INTO review_reports (id, body) VALUES (?, ?)', (number, text)
            )
            self.connection.execute(
                'INSERT INTO review_receipts (report_id) VALUES (?)', (number,)
            )
            self.connection.execute('''
                INSERT INTO replacement_catalog
                    (report_id, original_report_id, amendment_accession)
                VALUES (?, ?, ?)
            ''', (number, original_report_id, amendment_accession))
        return f'review-{number}'

    def load_replacement(self, report_id: str) -> str:
        token = validate_identifier(report_id, 'report_id')
        suffix = token.removeprefix('review-')
        row = self.connection.execute('''
            SELECT reports.body FROM replacement_catalog AS catalog
            JOIN review_reports AS reports ON reports.id = catalog.report_id
            JOIN review_receipts AS receipts ON receipts.report_id = reports.id
            WHERE catalog.report_id = ?
        ''', (suffix,)).fetchone()
        if row is None:
            if self.connection.execute(
                'SELECT 1 FROM review_reports WHERE id = ?', (suffix,)
            ).fetchone() is not None:
                raise ValueError('report number belongs to an original review, not a replacement')
            raise KeyError(token)
        return row[0]

    def is_replacement(self, report_id: str) -> bool:
        token = validate_identifier(report_id, 'report_id')
        suffix = token.removeprefix('review-')
        return self.connection.execute(
            'SELECT 1 FROM replacement_catalog WHERE report_id = ?', (suffix,)
        ).fetchone() is not None
