from archive.export import (
    IssuedReview, ReviewReceipt, decode_replacement, decode_review_body, render_review_json,
)
from archive.store import ArchiveStore


def read_review(store: ArchiveStore, report_id: str, *, as_json: bool = False) -> IssuedReview | str:
    body, receipt_id = store.load_review(report_id)
    review = IssuedReview(report_id, decode_review_body(body), ReviewReceipt(receipt_id))
    return render_review_json(review) if as_json else review


def read_replacement(store: ArchiveStore, report_id: str) -> dict:
    return decode_replacement(store.load_replacement(report_id))
