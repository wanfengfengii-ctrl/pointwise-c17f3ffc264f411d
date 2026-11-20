from dataclasses import dataclass
from fractions import Fraction
import json

from forecast.probability import fraction_from_payload, fraction_payload


@dataclass(frozen=True)
class ReviewRow:
    specimen_id: str
    probability: Fraction
    outcome: int
    forecast_source: str
    result_source: str
    squared_error: Fraction


@dataclass(frozen=True)
class ReviewBody:
    batch_id: str
    roster_id: str
    forecast_accession: str
    results_accession: str
    forecast_revision: str
    results_closeout: str
    rows: tuple[ReviewRow, ...]
    mean: Fraction


@dataclass(frozen=True)
class ReviewReceipt:
    report_id: str


@dataclass(frozen=True)
class IssuedReview:
    report_id: str
    body: ReviewBody
    receipt: ReviewReceipt


def _body_payload(body: ReviewBody) -> dict:
    return {
        'batch_id': body.batch_id,
        'roster_id': body.roster_id,
        'forecast_accession': body.forecast_accession,
        'results_accession': body.results_accession,
        'forecast_revision': body.forecast_revision,
        'results_closeout': body.results_closeout,
        'mean': fraction_payload(body.mean),
        'rows': [
            {
                'specimen_id': row.specimen_id,
                'probability': fraction_payload(row.probability),
                'outcome': row.outcome,
                'forecast_source': row.forecast_source,
                'result_source': row.result_source,
                'squared_error': fraction_payload(row.squared_error),
            }
            for row in body.rows
        ],
    }


def _json_text(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def encode_review_body(body: ReviewBody) -> str:
    return _json_text(_body_payload(body))


def decode_review_body(text: str) -> ReviewBody:
    body = json.loads(text)
    rows = tuple(
        ReviewRow(
            row['specimen_id'], fraction_from_payload(row['probability']), row['outcome'],
            row['forecast_source'], row['result_source'], fraction_from_payload(row['squared_error']),
        )
        for row in body['rows']
    )
    return ReviewBody(
        body['batch_id'], body['roster_id'], body['forecast_accession'], body['results_accession'],
        body['forecast_revision'], body['results_closeout'], rows, fraction_from_payload(body['mean']),
    )


def render_review_json(review: IssuedReview) -> str:
    return _json_text({
        'report_id': review.report_id,
        'body': _body_payload(review.body),
        'receipt': {'report_id': review.receipt.report_id},
    })
