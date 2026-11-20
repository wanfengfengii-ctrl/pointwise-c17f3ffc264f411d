from evaluation.piece_content import FixedPiece, normalize_piece
from evaluation.store import AccessionStore


def accept_piece(store: AccessionStore, payload: object) -> str:
    return store.admit(normalize_piece(payload))


def get_accepted_piece(store: AccessionStore, accession_id: str) -> FixedPiece:
    return store.load_piece(accession_id)


def amendment_status(store: AccessionStore, accession_id: str) -> str:
    from evaluation.amendments import amendment_status as status
    return status(store, store.load_amendment_record(accession_id))
