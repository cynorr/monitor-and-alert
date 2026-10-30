"""Date-based list features, independent of data providers and storage."""
from datetime import date


def days_to_earnings(next_earnings_date: str | None, as_of: date) -> int | None:
    return (date.fromisoformat(next_earnings_date) - as_of).days if next_earnings_date is not None else None
