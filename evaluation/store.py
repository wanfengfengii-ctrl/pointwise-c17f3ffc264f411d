import sqlite3

from evaluation.piece_content import FixedPiece, decode_piece, encode_piece
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
                number = original[0]
            else:
                cursor = self.connection.execute('''
                    INSERT INTO accepted_pieces (kind, batch_id, source_id, payload)
                    VALUES (?, ?, ?, ?)
                ''', (*key, payload))
                number = cursor.lastrowid
        return f'piece-{number}'

    def load_piece(self, accession_id: str) -> FixedPiece:
        token = validate_identifier(accession_id, 'accession_id')
        row = self.connection.execute(
            'SELECT id, payload FROM accepted_pieces WHERE id = ?',
            (token.removeprefix('piece-'),),
        ).fetchone()
        if row is None or token != f'piece-{row[0]}':
            raise KeyError(token)
        return decode_piece(row[1])
