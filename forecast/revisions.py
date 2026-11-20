from forecast.snapshot import ForecastSnapshot, build_forecast_snapshot
from forecast.store import ForecastStore
from study.registry import get_roster
from study.store import StudyStore


def freeze_forecast(
    studies: StudyStore, forecasts: ForecastStore, batch_id: str, revision_id: str, rows: object
) -> ForecastSnapshot:
    roster = get_roster(studies, batch_id)
    return forecasts.save_or_recall(build_forecast_snapshot(roster, revision_id, rows))


def get_frozen_forecast(forecasts: ForecastStore, batch_id: str, revision_id: str) -> ForecastSnapshot:
    return forecasts.load_revision(batch_id, revision_id)
