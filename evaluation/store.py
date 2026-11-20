"""Acceptance store for fixed pieces, including formally published amendments."""

from contextlib import contextmanager
import sqlite3

from evaluation.piece_content import FixedPiece, decode_piece, encode_piece, piece_fingerprint
from sqlite_tx import write_transaction
from study.identity import validate_identifier


class AccessionStore:
    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self.initialize()

    def initialize(self) -> None:
        with write_transaction(self.connection):
            self.connection.execute('''
                CREATE TABLE IF NOT EXISTS accepted_pieces (
                    id INTEGER PRIMARY KEY,
                    kind TEXT NOT NULL,
                    batch_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    UNIQUE (kind, batch_id, source_id)
                )
            ''')
            self.connection.execute('''
                CREATE TABLE IF NOT EXISTS amendment_edges (
                    accession_id INTEGER PRIMARY KEY
                        REFERENCES accepted_pieces(id),
                    batch_id TEXT NOT NULL,
                    roster_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    parent_id TEXT NOT NULL,
                    parent_sha256 TEXT NOT NULL,
                    UNIQUE (batch_id, roster_id, parent_id, parent_sha256)
                )
            ''')

    @contextmanager
    def snapshot(self):
        """Read accepted state from one consistent point in time."""
        if self.connection.in_transaction:
            yield
            return
        self.connection.execute('BEGIN')
        try:
            yield
        finally:
            self.connection.rollback()

    def admit(self, piece: FixedPiece) -> str:
        key = (piece.kind, piece.roster.batch_id, piece.source_id)
        payload = encode_piece(piece)
        with write_transaction(self.connection):
            original = self.connection.execute('''
                SELECT id, payload FROM accepted_pieces
                WHERE kind = ? AND batch_id = ? AND source_id = ?
            ''', key).fetchone()
            if original is not None:
                if original[1] != payload:
                    raise ValueError('fixed-piece identity already has different content')
                return f'piece-{original[0]}'
            if piece.kind == 'result-amendment':
                self._check_known_parent(piece)
                claim = (piece.roster.batch_id, piece.roster.roster_id,
                         piece.parent_id, piece.parent_sha256)
                occupied = self.connection.execute('''
                    SELECT accession_id FROM amendment_edges
                    WHERE batch_id = ? AND roster_id = ? AND parent_id = ?
                      AND parent_sha256 = ?
                ''', claim).fetchone()
                if occupied is not None:
                    raise ValueError('another amendment already claims this parent edge')
            cursor = self.connection.execute('''
                INSERT INTO accepted_pieces (kind, batch_id, source_id, payload)
                VALUES (?, ?, ?, ?)
            ''', (*key, payload))
            number = cursor.lastrowid
            if piece.kind == 'result-amendment':
                self.connection.execute('''
                    INSERT INTO amendment_edges
                        (accession_id, batch_id, roster_id, source_id, parent_id, parent_sha256)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (number, piece.roster.batch_id, piece.roster.roster_id,
                      piece.source_id, piece.parent_id, piece.parent_sha256))
        return f'piece-{number}'

    def _check_known_parent(self, piece: FixedPiece) -> None:
        parent = self.parent_piece(piece.roster.batch_id, piece.parent_id)
        if parent is None:
            other = self.connection.execute('''
                SELECT 1 FROM accepted_pieces WHERE batch_id = ? AND source_id = ?
            ''', (piece.roster.batch_id, piece.parent_id)).fetchone()
            if other is not None:
                raise ValueError('amendment parent is not a sealed result batch or amendment')
            return
        parent_piece = decode_piece(parent[1])
        if parent_piece.roster.roster_id != piece.roster.roster_id:
            raise ValueError('amendment parent belongs to a different roster')
        if piece_fingerprint(parent_piece) != piece.parent_sha256:
            raise ValueError('amendment parent fingerprint does not match the known parent')

    def load_piece(self, accession_id: str) -> FixedPiece:
        number = self._number(accession_id)
        row = self.connection.execute(
            'SELECT id, payload FROM accepted_pieces WHERE id = ?', (number,)
        ).fetchone()
        if row is None:
            raise KeyError(validate_identifier(accession_id, 'accession_id'))
        return decode_piece(row[1])

    def load_amendment_record(self, accession_id: str) -> 'AmendmentRecord':
        token = validate_identifier(accession_id, 'accession_id')
        number = self._amendment_number(token)
        row = self._amendment_query('AND pieces.id = ?', (number,)).fetchone()
        if row is None:
            known = self.connection.execute(
                'SELECT kind FROM accepted_pieces WHERE id = ?', (number,)
            ).fetchone()
            if known is None:
                raise KeyError(token)
            raise ValueError('accession is not a result amendment')
        return _record(row)

    def parent_piece(self, batch_id: str, parent_id: str) -> tuple[tuple, str] | None:
        """The accepted amendment or seal named by a parent identifier."""
        for kind in ('result-amendment', 'results'):
            row = self.connection.execute('''
                SELECT id, batch_id, source_id, payload FROM accepted_pieces
                WHERE kind = ? AND batch_id = ? AND source_id = ?
            ''', (kind, batch_id, parent_id)).fetchone()
            if row is not None:
                return row, row[3]
        return None

    def amendments_for(self, batch_id: str, roster_id: str) -> tuple['AmendmentRecord', ...]:
        rows = self._amendment_query(
            'AND pieces.batch_id = ? AND edges.roster_id = ? ORDER BY pieces.id',
            (batch_id, roster_id),
        ).fetchall()
        return tuple(_record(row) for row in rows)

    def _amendment_query(self, suffix: str, parameters: tuple):
        return self.connection.execute(f'''
            SELECT pieces.id, pieces.batch_id, pieces.source_id, pieces.payload,
                   edges.roster_id, edges.parent_id, edges.parent_sha256
            FROM accepted_pieces AS pieces
            JOIN amendment_edges AS edges ON edges.accession_id = pieces.id
            WHERE pieces.kind = 'result-amendment' {suffix}
        ''', parameters)

    def _number(self, token: str) -> int:
        text = validate_identifier(token, 'accession_id')
        suffix = text.removeprefix('piece-')
        if suffix == text or not suffix.isdigit():
            raise KeyError(text)
        return int(suffix)

    def _amendment_number(self, token: str) -> int:
        """Unknown numbers raise KeyError; malformed tokens raise ValueError."""
        suffix = token.removeprefix('piece-')
        if suffix == token or not suffix.isdigit() or int(suffix) <= 0:
            raise ValueError('accession_id must look like piece-<positive number>')
        return int(suffix)


class AmendmentRecord:
    """A stored amendment together with the parent edge it claims."""

    __slots__ = ('accession_id', 'number', 'batch_id', 'source_id', 'payload',
                 'roster_id', 'parent_id', 'parent_sha256')

    def __init__(self, accession_id, number, batch_id, source_id, payload,
                 roster_id, parent_id, parent_sha256):
        self.accession_id = accession_id
        self.number = number
        self.batch_id = batch_id
        self.source_id = source_id
        self.payload = payload
        self.roster_id = roster_id
        self.parent_id = parent_id
        self.parent_sha256 = parent_sha256

    @property
    def piece(self) -> FixedPiece:
        return decode_piece(self.payload)

    def __eq__(self, other):
        return isinstance(other, AmendmentRecord) and self.accession_id == other.accession_id

    def __hash__(self):
        return hash(self.accession_id)


def _record(row) -> AmendmentRecord:
    return AmendmentRecord(f'piece-{row[0]}', row[0], row[1], row[2], row[3],
                           row[4], row[5], row[6])
