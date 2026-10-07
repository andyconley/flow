"""Sealed wall-time authority, independent from context and spending budgets."""
from datetime import datetime, timedelta, timezone


def seal_runtime_budget(seconds: int, started_at: str) -> dict:
    if type(seconds) is not int or seconds < 1:
        raise ValueError('runtime budget must be a positive integer')
    start = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
    return {'seconds': seconds, 'started_at': started_at,
            'deadline_at': (start + timedelta(seconds=seconds)).isoformat()}


def validate_runtime_budget(envelope: dict) -> None:
    budget = envelope.get('runtime_budget')
    if budget is None:  # Historic envelopes stay readable without a new cap.
        return
    if not isinstance(budget, dict) or set(budget) != {'seconds', 'started_at', 'deadline_at'}:
        raise ValueError('runtime budget fields are invalid')
    if budget['seconds'] != envelope['limits'].get('max_runtime_seconds'):
        raise ValueError('runtime budget differs from approved limits')
    expected = seal_runtime_budget(budget['seconds'], budget['started_at'])
    if expected != budget or datetime.fromisoformat(budget['started_at'].replace('Z', '+00:00')).tzinfo is None:
        raise ValueError('runtime budget deadline is invalid')


def remaining_runtime(envelope: dict, *, now: datetime | None = None) -> float | None:
    validate_runtime_budget(envelope)
    budget = envelope.get('runtime_budget')
    if budget is None:
        return None
    remaining = (datetime.fromisoformat(budget['deadline_at']) - (now or datetime.now(timezone.utc))).total_seconds()
    if remaining <= 0:
        raise TimeoutError('sealed runtime budget exhausted; successor approval is required')
    return remaining
