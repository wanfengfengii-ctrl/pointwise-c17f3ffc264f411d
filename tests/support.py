from contextlib import ExitStack, closing, contextmanager
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from archive.store import ArchiveStore
from bench.closeout import close_results
from bench.results import record_result
from bench.reveal import reveal_result
from bench.snapshot import bench_piece_payload
from bench.store import BenchStore
from evaluation.accession import accept_piece
from evaluation.store import AccessionStore
from forecast.revisions import freeze_forecast
from forecast.snapshot import forecast_piece_payload
from forecast.store import ForecastStore
from study.registry import create_study
from study.store import StudyStore


BATCH = 'tray-17'
ROSTER = ('B', 'A')


def forecast_rows(a='1/4', b='1/2', a_source='model:A', b_source='model:B'):
    return [
        {'specimen_id': 'A', 'probability': a, 'source': a_source},
        {'specimen_id': 'B', 'probability': b, 'source': b_source},
    ]


class LostReply(ConnectionError):
    pass


class LocalMessages:
    """Hold encoded pieces until explicitly delivered to a real accession store."""

    def __init__(self):
        self._pending: dict[str, str] = {}
        self.committed: dict[str, str] = {}

    def queue(self, delivery_id: str, payload: dict) -> None:
        if delivery_id in self._pending or delivery_id in self.committed:
            raise ValueError('delivery identifier already used')
        self._pending[delivery_id] = json.dumps(payload)

    def deliver(self, delivery_id: str, store: AccessionStore, *, lose_reply: bool = False) -> str:
        accession_id = accept_piece(store, json.loads(self._pending[delivery_id]))
        del self._pending[delivery_id]
        self.committed[delivery_id] = accession_id
        if lose_reply:
            raise LostReply(delivery_id)
        return accession_id


@contextmanager
def fail_receipt_write(store: ArchiveStore):
    connection = store.connection
    connection.execute('''
        CREATE TEMP TRIGGER refuse_receipt BEFORE INSERT ON main.review_receipts
        BEGIN
            SELECT RAISE(ABORT, 'receipt write refused');
        END
    ''')
    try:
        yield
    finally:
        connection.execute('DROP TRIGGER temp.refuse_receipt')


@contextmanager
def fail_review_commit(store: ArchiveStore):
    connection = store.connection
    connection.executescript('''
        CREATE TEMP TABLE allowed_review (id INTEGER PRIMARY KEY);
        CREATE TEMP TABLE pending_review (
            id INTEGER REFERENCES allowed_review(id) DEFERRABLE INITIALLY DEFERRED
        );
        CREATE TEMP TRIGGER defer_receipt_check AFTER INSERT ON main.review_receipts
        BEGIN
            INSERT INTO pending_review (id) VALUES (NEW.report_id);
        END;
    ''')
    try:
        yield
    finally:
        connection.executescript('''
            DROP TRIGGER temp.defer_receipt_check;
            DROP TABLE temp.pending_review;
            DROP TABLE temp.allowed_review;
        ''')


def archive_counts(store: ArchiveStore) -> tuple[int, int]:
    return store.connection.execute('''
        SELECT (SELECT count(*) FROM review_reports), (SELECT count(*) FROM review_receipts)
    ''').fetchone()


class LabCase(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(TemporaryDirectory(prefix='liwan-test-')))
        self.studies = self.open_store(StudyStore, 'study')
        self.forecasts = self.open_store(ForecastStore, 'forecast')
        self.bench = self.open_store(BenchStore, 'bench')
        self.accessions = self.open_store(AccessionStore, 'accession')
        self.archive = self.open_store(ArchiveStore, 'archive')

    def open_store(self, store_type, name):
        connection = self.stack.enter_context(closing(sqlite3.connect(self.root / f'{name}.sqlite3')))
        return store_type(connection)

    def reopen(self, previous, name):
        previous.connection.close()
        return self.open_store(type(previous), name)

    def register(self, batch_id=BATCH, specimens=ROSTER):
        return create_study(self.studies, batch_id, specimens)

    def freeze(self, revision='r1', *, batch_id=BATCH, rows=None):
        return freeze_forecast(
            self.studies, self.forecasts, batch_id, revision, forecast_rows() if rows is None else rows
        )

    def complete_results(self, batch_id=BATCH, *, studies=None, bench=None):
        studies = self.studies if studies is None else studies
        bench = self.bench if bench is None else bench
        record_result(studies, bench, batch_id, 'A', 1, 'bench:A')
        record_result(studies, bench, batch_id, 'B', 0, 'bench:B')
        reveal_result(studies, bench, batch_id, 'A')
        reveal_result(studies, bench, batch_id, 'B')
        return close_results(studies, bench, batch_id)

    def selected_pair(self, *, rows=None):
        self.register()
        forecast = self.freeze(rows=rows)
        results = self.complete_results()
        return (
            accept_piece(self.accessions, forecast_piece_payload(forecast)),
            accept_piece(self.accessions, bench_piece_payload(results)),
        )
