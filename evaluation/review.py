from archive.export import IssuedReview, ReviewBody, ReviewRow
from archive.issue import issue_report
from archive.store import ArchiveStore
from evaluation.accession import get_accepted_piece
from evaluation.alignment import align_accepted_pair
from evaluation.brier import score_brier
from evaluation.store import AccessionStore


def issue_review(
    accessions: AccessionStore, archive: ArchiveStore, forecast_accession: str, results_accession: str
) -> IssuedReview:
    forecast = get_accepted_piece(accessions, forecast_accession)
    results = get_accepted_piece(accessions, results_accession)
    score = score_brier(align_accepted_pair(forecast, results))
    rows = tuple(
        ReviewRow(
            row.specimen.specimen_id,
            row.specimen.probability,
            row.specimen.outcome,
            row.specimen.forecast_source,
            row.specimen.result_source,
            row.squared_error,
        )
        for row in score.rows
    )
    body = ReviewBody(
        batch_id=forecast.roster.batch_id,
        roster_id=forecast.roster.roster_id,
        forecast_accession=forecast_accession,
        results_accession=results_accession,
        forecast_revision=forecast.source_id,
        results_closeout=results.source_id,
        rows=rows,
        mean=score.mean,
    )
    return issue_report(archive, body)
