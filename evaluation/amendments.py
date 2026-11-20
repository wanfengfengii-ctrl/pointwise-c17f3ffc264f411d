"""Verified amendment chains over accepted fixed pieces."""

from evaluation.piece_content import FixedPiece, decode_piece, piece_fingerprint
from evaluation.store import AccessionStore, AmendmentRecord


def piece_sha256(piece: FixedPiece) -> str:
    """Canonical fingerprint of a fixed piece, matching publish-side parent hashes."""
    return piece_fingerprint(piece)


def sealed_results(store: AccessionStore, batch_id: str) -> FixedPiece | None:
    row = store.connection.execute('''
        SELECT payload FROM accepted_pieces
        WHERE kind = 'results' AND batch_id = ? AND source_id = ?
    ''', (batch_id, f'results:{batch_id}')).fetchone()
    return None if row is None else decode_piece(row[0])


def root_for(store: AccessionStore, batch_id: str, roster_id: str) -> FixedPiece | None:
    root = sealed_results(store, batch_id)
    if root is None or root.roster.roster_id != roster_id:
        return None
    return root


def chain_from_root(
    store: AccessionStore, batch_id: str, root: FixedPiece
) -> tuple[AmendmentRecord, ...]:
    records = store.amendments_for(batch_id, root.roster.roster_id)
    by_edge = {(record.parent_id, record.parent_sha256): record for record in records}
    chain: list[AmendmentRecord] = []
    current = root
    seen: set[str] = set()
    while True:
        child = by_edge.get((current.source_id, piece_sha256(current)))
        if child is None or child.source_id in seen:
            break
        child_piece = child.piece
        if child_piece.roster != root.roster:
            break
        seen.add(child.source_id)
        chain.append(child)
        current = child_piece
    return tuple(chain)


def chain_for(
    store: AccessionStore, batch_id: str, roster_id: str
) -> tuple[FixedPiece | None, tuple[AmendmentRecord, ...]]:
    root = root_for(store, batch_id, roster_id)
    if root is None:
        return None, ()
    return root, chain_from_root(store, batch_id, root)


def _proof_state(
    store: AccessionStore, record: AmendmentRecord, records: dict[str, AmendmentRecord]
) -> str:
    """Walk parent edges to the sealed batch: rooted, pending_proof or invalid."""
    current = record
    seen: set[str] = set()
    while True:
        if current.source_id in seen:
            return 'invalid'
        seen.add(current.source_id)
        parent = store.parent_piece(current.batch_id, current.parent_id)
        if parent is None:
            return 'pending_proof'
        parent_piece = decode_piece(parent[1])
        if parent_piece.roster.roster_id != current.roster_id:
            return 'invalid'
        if piece_fingerprint(parent_piece) != current.parent_sha256:
            return 'invalid'
        if parent_piece.kind == 'results':
            if parent_piece.source_id != f'results:{current.batch_id}':
                return 'invalid'
            return 'rooted'
        if parent_piece.kind != 'result-amendment':
            return 'invalid'
        following = records.get(parent_piece.source_id)
        if following is None:
            return 'invalid'
        current = following


def amendment_status(store: AccessionStore, record: AmendmentRecord) -> str:
    records = {item.source_id: item for item in store.amendments_for(record.batch_id, record.roster_id)}
    state = _proof_state(store, record, records)
    if state == 'pending_proof':
        return 'pending_proof'
    if state == 'invalid':
        return 'invalid'
    _, chain = chain_for(store, record.batch_id, record.roster_id)
    accessions = [item.accession_id for item in chain]
    if record.accession_id not in accessions:
        return 'invalid'
    return 'effective' if accessions[-1] == record.accession_id else 'superseded'


def effective_amendment(store: AccessionStore, batch_id: str, roster_id: str) -> AmendmentRecord | None:
    _, chain = chain_for(store, batch_id, roster_id)
    return chain[-1] if chain else None


def amendment_chain_rows(chain: tuple[AmendmentRecord, ...]) -> tuple[dict, ...]:
    return tuple(
        {'source_id': item.source_id, 'accession_id': item.accession_id} for item in chain
    )
