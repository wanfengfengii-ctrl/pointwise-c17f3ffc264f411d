import json
import sqlite3

from bench.amendment import (
    Amendment, amendment_from_payload, build_amendment, canonical_text, encode_amendment,
    text_sha256, validate_amendment_id, validate_parent_id,
)
from bench.snapshot import (
    BenchSnapshot, RevealedResult, bench_piece_payload, bench_snapshot_from_payload,
    build_bench_snapshot,
)
from sqlite_tx import write_transaction
from study.identity import validate_identifier
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
            self.connection.execute('''
                CREATE TABLE IF NOT EXISTS bench_amendments (
                    batch_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    parent_id TEXT NOT NULL,
                    parent_sha256 TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (batch_id, source_id)
                )
            ''')
            self.connection.execute('''
                CREATE TABLE IF NOT EXISTS bench_amendment_heads (
                    batch_id TEXT PRIMARY KEY NOT NULL,
                    source_id TEXT NOT NULL
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

    def publish_amendment(
        self, batch_id: str, parent_id: str, source_id: str, rows: object
    ) -> Amendment:
        key = (validate_identifier(batch_id, 'batch_id'),)
        with write_transaction(self.connection):
            saved = self.connection.execute(
                'SELECT payload FROM bench_closeouts WHERE batch_id = ?', key
            ).fetchone()
            if saved is None:
                raise ValueError('batch has no sealed result batch')
            root = bench_snapshot_from_payload(json.loads(saved[0]))
            root_text = canonical_text(bench_piece_payload(root))
            root_sha = text_sha256(root_text)
            stored = self.connection.execute('''
                SELECT payload FROM bench_amendments
                WHERE batch_id = ? AND source_id = ?
            ''', (*key, validate_amendment_id(source_id))).fetchone()
            if stored is not None:
                original = amendment_from_payload(json.loads(stored[0]))
                if original.parent_id != parent_id:
                    raise ValueError('amendment number already has a different parent')
                replay = build_amendment(original.roster, source_id, parent_id,
                                         original.parent_sha256, rows)
                if encode_amendment(replay) != stored[0]:
                    raise ValueError('amendment number already has different content')
                return original
            if parent_id == root.closeout_id:
                parent_sha = root_sha
            else:
                parent = self.connection.execute('''
                    SELECT payload FROM bench_amendments
                    WHERE batch_id = ? AND source_id = ?
                ''', (*key, validate_parent_id(parent_id))).fetchone()
                if parent is None:
                    raise ValueError('parent is not the sealed batch or an issued amendment')
                if amendment_from_payload(json.loads(parent[0])).roster != root.roster:
                    raise ValueError('parent amendment belongs to a different roster')
                parent_sha = text_sha256(parent[0])
            head = self._amendment_head(key[0])
            expected = root.closeout_id if head is None else head
            if parent_id != expected:
                raise ValueError('amendment must extend the current chain head')
            amendment = build_amendment(root.roster, source_id, parent_id, parent_sha, rows)
            payload = encode_amendment(amendment)
            self.connection.execute('''
                INSERT INTO bench_amendments
                    (batch_id, source_id, parent_id, parent_sha256, payload)
                VALUES (?, ?, ?, ?, ?)
            ''', (key[0], amendment.source_id, amendment.parent_id, amendment.parent_sha256, payload))
            self.connection.execute('''
                INSERT INTO bench_amendment_heads (batch_id, source_id) VALUES (?, ?)
                ON CONFLICT (batch_id) DO UPDATE SET source_id = excluded.source_id
            ''', (key[0], amendment.source_id))
            return amendment

    def load_amendment(self, batch_id: str, source_id: str) -> Amendment:
        key = (validate_identifier(batch_id, 'batch_id'),
               validate_amendment_id(source_id))
        row = self.connection.execute('''
            SELECT payload FROM bench_amendments WHERE batch_id = ? AND source_id = ?
        ''', key).fetchone()
        if row is None:
            raise KeyError(key)
        return amendment_from_payload(json.loads(row[0]))

    def _amendment_head(self, batch_id: str) -> str | None:
        row = self.connection.execute(
            'SELECT source_id FROM bench_amendment_heads WHERE batch_id = ?', (batch_id,)
        ).fetchone()
        return None if row is None else row[0]
