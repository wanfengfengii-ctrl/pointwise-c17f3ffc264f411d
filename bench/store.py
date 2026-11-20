import json
import sqlite3

from bench.snapshot import (
    BenchSnapshot, RevealedResult, bench_piece_payload, bench_snapshot_from_payload,
    build_bench_snapshot,
)
from sqlite_tx import write_transaction
from study.roster import Roster


class BenchStore:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self.initialize()

    def initialize(self) -> None:
        with write_transaction(self.connection):
            self.connection.execute('''
                CREATE TABLE IF NOT EXISTS bench_results (
                    batch_id TEXT NOT NULL,
                    specimen_id TEXT NOT NULL,
                    outcome INTEGER NOT NULL CHECK (outcome IN (0, 1)),
                    source TEXT NOT NULL,
                    revealed INTEGER NOT NULL DEFAULT 0 CHECK (revealed IN (0, 1)),
                    PRIMARY KEY (batch_id, specimen_id)
                )
            ''')
            self.connection.execute('''
                CREATE TABLE IF NOT EXISTS bench_closeouts (
                    batch_id TEXT PRIMARY KEY NOT NULL,
                    payload TEXT NOT NULL
                )
            ''')

    def save_result(self, batch_id: str, result: RevealedResult) -> RevealedResult:
        key = (batch_id, result.specimen_id)
        with write_transaction(self.connection):
            row = self._find_result(key)
            if row is None:
                self.connection.execute('''
                    INSERT INTO bench_results (batch_id, specimen_id, outcome, source)
                    VALUES (?, ?, ?, ?)
                ''', (*key, result.outcome, result.source))
            else:
                outcome, source, revealed = row
                if revealed:
                    original = RevealedResult(result.specimen_id, outcome, source)
                    if result != original:
                        raise ValueError('revealed outcome and source are fixed')
                    return original
                self.connection.execute('''
                    UPDATE bench_results SET outcome = ?, source = ?
                    WHERE batch_id = ? AND specimen_id = ?
                ''', (result.outcome, result.source, *key))
        return result

    def mark_revealed(self, batch_id: str, specimen_id: str) -> RevealedResult:
        key = (batch_id, specimen_id)
        with write_transaction(self.connection):
            row = self._find_result(key)
            if row is None:
                raise ValueError('specimen has no recorded result')
            outcome, source, revealed = row
            if not revealed:
                self.connection.execute('''
                    UPDATE bench_results SET revealed = 1
                    WHERE batch_id = ? AND specimen_id = ?
                ''', key)
        return RevealedResult(specimen_id, outcome, source)

    def save_or_recall_closeout(self, roster: Roster) -> BenchSnapshot:
        key = (roster.batch_id,)
        with write_transaction(self.connection):
            saved = self.connection.execute(
                'SELECT payload FROM bench_closeouts WHERE batch_id = ?', key
            ).fetchone()
            if saved is not None:
                original = bench_snapshot_from_payload(json.loads(saved[0]))
                if original.roster != roster:
                    raise ValueError('closeout already has a different roster')
                return original
            rows = self.connection.execute('''
                SELECT specimen_id, outcome, source FROM bench_results
                WHERE batch_id = ? AND revealed = 1
            ''', key).fetchall()
            snapshot = build_bench_snapshot(roster, [RevealedResult(*row) for row in rows])
            payload = json.dumps(bench_piece_payload(snapshot), sort_keys=True, separators=(',', ':'))
            self.connection.execute(
                'INSERT INTO bench_closeouts (batch_id, payload) VALUES (?, ?)',
                (roster.batch_id, payload),
            )
            return snapshot

    def _find_result(self, key: tuple[str, str]) -> tuple[int, str, int] | None:
        return self.connection.execute('''
            SELECT outcome, source, revealed FROM bench_results
            WHERE batch_id = ? AND specimen_id = ?
        ''', key).fetchone()
