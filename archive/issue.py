from archive.export import IssuedReview, ReviewBody, ReviewReceipt, encode_review_body
from archive.store import ArchiveStore


def issue_report(store: ArchiveStore, body: ReviewBody) -> IssuedReview:
    report_id = store.commit_review(encode_review_body(body))
    return IssuedReview(report_id, body, ReviewReceipt(report_id))
