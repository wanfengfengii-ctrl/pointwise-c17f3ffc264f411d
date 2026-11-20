"""Recompute an original review on top of its verified amendment chain."""

from archive.export import (
    IssuedReview, ReplacementBody, ReviewRow, decode_replacement, encode_replacement,
)
from archive.export import ReviewBody
from archive.issue import issue_report
from archive.lookup import read_review
from archive.store import ArchiveStore
from evaluation.accession import get_accepted_piece
from evaluation.alignment import align_accepted_pair, AlignedSpecimen
from evaluation.amendments import amendment_chain_rows, chain_for, effective_amendment
from evaluation.brier import score_brier
from evaluation.piece_content import FixedPiece
from evaluation.store import AccessionStore
from study.identity import validate_identifier
import json


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


def _apply_chain(results: FixedPiece, chain) -> FixedPiece:
    by_specimen = {row.specimen_id: row for row in results.rows}
    for record in chain:
        for row in record.piece.rows:
            by_specimen[row.specimen_id] = row
    return FixedPiece('results', results.roster, results.source_id,
                      tuple(by_specimen[name] for name in results.roster.specimens))


def _replacement_body(
    original: IssuedReview, forecast: FixedPiece, results: FixedPiece, chain, target
) -> ReplacementBody:
    result_rows = {row.specimen_id: row for row in results.rows}
    forecast_rows = {row.specimen_id: row for row in forecast.rows}
    aligned = tuple(
        AlignedSpecimen(
            name, forecast_rows[name].probability, result_rows[name].outcome,
            forecast_rows[name].source, result_rows[name].source,
        )
        for name in forecast.roster.specimens
    )
    score = score_brier(aligned)
    return ReplacementBody(
        batch_id=forecast.roster.batch_id,
        roster_id=forecast.roster.roster_id,
        forecast_accession=original.body.forecast_accession,
        results_accession=original.body.results_accession,
        forecast_revision=forecast.source_id,
        results_closeout=results.source_id,
        rows=tuple(
            ReviewRow(row.specimen.specimen_id, row.specimen.probability, row.specimen.outcome,
                      row.specimen.forecast_source, row.specimen.result_source,
                      row.squared_error)
            for row in score.rows
        ),
        mean=score.mean,
        original_report_id=original.report_id,
        amendment_accession=target.accession_id,
        amendment_chain=amendment_chain_rows(chain),
    )


def _stored(archive: ArchiveStore, original_report_id: str, accession_id: str) -> dict | None:
    text = archive.find_replacement(original_report_id, accession_id)
    return None if text is None else decode_replacement(text)


def _validate_selection(original: IssuedReview, forecast: FixedPiece, results: FixedPiece) -> None:
    if forecast.kind != 'forecast' or results.kind != 'results':
        raise ValueError('original report does not reference a forecast and sealed results')
    roster_id = original.body.roster_id
    if forecast.roster.roster_id != roster_id or results.roster.roster_id != roster_id:
        raise ValueError('original report roster does not match its selected pieces')
    if results.source_id != f'results:{original.body.batch_id}':
        raise ValueError('original report does not reference the sealed result batch')


def _original_report(archive: ArchiveStore, token: str) -> IssuedReview:
    try:
        return read_review(archive, token)
    except KeyError:
        if archive.is_replacement(token):
            raise ValueError('a replacement report is not an original review') from None
        raise


def issue_replacement(
    accessions: AccessionStore, archive: ArchiveStore, original_report_id: str, amendment_accession: str
) -> dict:
    token = validate_identifier(original_report_id, 'report_id')
    attempt = validate_identifier(amendment_accession, 'accession_id')
    original = _original_report(archive, token)
    target = accessions.load_amendment_record(attempt)

    stored = _stored(archive, token, attempt)
    if stored is not None:
        if stored.get('body', {}).get('amendment_accession') != attempt:
            raise ValueError('stored replacement names a different amendment')
        return stored

    with accessions.snapshot():
        batch_id = original.body.batch_id
        roster_id = original.body.roster_id
        forecast = get_accepted_piece(accessions, original.body.forecast_accession)
        results = get_accepted_piece(accessions, original.body.results_accession)
        _validate_selection(original, forecast, results)
        if target.batch_id != batch_id or target.roster_id != roster_id:
            raise ValueError('requested amendment belongs to another batch')
        root, chain = chain_for(accessions, batch_id, roster_id)
        if root is None:
            raise ValueError('original report has no sealed result batch')
        if target.accession_id not in {item.accession_id for item in chain}:
            raise ValueError('requested amendment is not in the effective chain')
        index = next(i for i, item in enumerate(chain) if item.accession_id == attempt)
        if index != len(chain) - 1:
            raise ValueError('requested amendment is not the current effective generation')
        scoped = chain[:index + 1]
        amended = _apply_chain(results, scoped)
        body = _replacement_body(original, forecast, amended, scoped, target)
        archive.commit_replacement(
            token, attempt, lambda number: encode_replacement(number, body)
        )
    return _stored(archive, token, attempt)


def _latest_tip(accessions: AccessionStore, batch_id: str, roster_id: str):
    with accessions.snapshot():
        return effective_amendment(accessions, batch_id, roster_id)


def read_current_review(accessions: AccessionStore, archive: ArchiveStore, original_report_id: str) -> dict:
    token = validate_identifier(original_report_id, 'report_id')
    original = _original_report(archive, token)
    original_json = read_review(archive, token, as_json=True)
    batch_id = original.body.batch_id
    roster_id = original.body.roster_id

    def tip_key(tip):
        return None if tip is None else tip.accession_id

    for _ in range(16):
        before = tip_key(_latest_tip(accessions, batch_id, roster_id))
        if before is None:
            view = {'status': 'original', 'amendment_accession': None,
                    'report': json.loads(original_json)}
        else:
            stored = _stored(archive, token, before)
            if stored is None:
                view = {'status': 'pending_recompute', 'amendment_accession': before,
                        'report': None}
            else:
                view = {'status': 'replacement', 'amendment_accession': before, 'report': stored}
        # The chain only advances, so an unchanged tip proves the archive read and the
        # reported generation held at the same point in time.
        after = tip_key(_latest_tip(accessions, batch_id, roster_id))
        if before == after:
            return view
    raise ValueError('accepted amendments kept advancing during the current-review query')
