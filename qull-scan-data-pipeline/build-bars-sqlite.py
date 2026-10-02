"""
Build split-adjusted daily bars for SQLite jobs.

Input:
- massive/daily/*.json, for example massive/daily/2026-08-20.json.
  Contains raw unadjusted Massive daily bars.
- massive/splits.json contains the split snapshot.
- pipeline-status.json supplies the completed daily_target with daily_status=ok.

Output:
- bars.sqlite3, table bars.
- Fields: symbol, timeframe, ts, open, high, low, close, volume, turnover.
- Primary key: (symbol, timeframe, ts).
- Keep each symbol's latest 1000 bars through the completed date.
- Rebuild and atomically replace the full file.
- Table metadata records the completed date and data conventions.
- Append bounds conflicts to invalid_ohlc.jsonl without changing prices.

Run:
- Auto (default): python build-bars-sqlite.py
  Use the explicit completed date from pipeline-status.json.

Notes:
- Keep raw daily files unchanged.
- Preserve the split adjustment used by build-bars.py.
- Append .US to every original ticker without symbol lookup.
- Use Massive daily coverage without filtering trading sessions.
- ts is Unix seconds at America/New_York midnight, including DST.
- Round adjusted volume to whole shares with 0.5 rounded up.
- Estimate turnover from VWAP times unrounded volume, or use NULL.
"""

import math
import os
import sqlite3
import time
from concurrent.futures import ProcessPoolExecutor
from contextlib import closing
from datetime import UTC, date, datetime, time as clock_time
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import numpy as np
import orjson
import pandas as pd


ROOT = Path(__file__).resolve().parent

DAY_DIR = ROOT / "massive" / "daily"
SPLIT_FILE = ROOT / "massive" / "splits.json"
OUT_FILE = ROOT / "bars.sqlite3"
STATUS_FILE = ROOT / "pipeline-status.json"
INVALID_FILE = ROOT / "invalid_ohlc.jsonl"
TIMEFRAME = "1d"
MAX_HISTORY = 1000
NEW_YORK = ZoneInfo("America/New_York")


SCHEMA = """
CREATE TABLE bars (
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    ts INTEGER NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume INTEGER NOT NULL,
    turnover REAL,
    PRIMARY KEY (symbol, timeframe, ts)
)
"""


def read_status():
    data = orjson.loads(STATUS_FILE.read_bytes())
    if data.get("daily_status") != "ok":
        raise ValueError("Daily update is not complete in pipeline-status.json")

    day = date.fromisoformat(data["daily_target"])
    calendar = xcals.get_calendar("XNYS")
    if not calendar.is_session(day):
        raise ValueError(f"Completed date is not a trading session: {day}")
    if datetime.now(UTC) < calendar.session_close(day).to_pydatetime():
        raise ValueError(f"Trading session has not closed: {day}")

    return day.isoformat(), data.get("daily_updated_at")


def check_number(value, name, ticker, day):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise ValueError(f"Invalid {name}: {ticker} on {day}")


def parse_day(path):
    day = date.fromisoformat(path.stem)
    data = orjson.loads(path.read_bytes())
    if data.get("status") != "OK" or data.get("adjusted") is not False:
        raise ValueError(f"Expected successful unadjusted daily data: {path}")
    results = data["results"]
    if not results or data.get("resultsCount") != len(results):
        raise ValueError(f"Invalid daily result count: {path}")

    dates = [day.isoformat()] * len(results)
    tickers = []
    opens = []
    highs = []
    lows = []
    closes = []
    volumes = []
    vwaps = []
    transactions = []

    seen = set()
    for item in results:
        ticker = item["T"]
        if not isinstance(ticker, str) or not ticker or ticker != ticker.strip():
            raise ValueError(f"Invalid ticker: {path}")
        if ticker in seen:
            raise ValueError(f"Duplicate ticker: {ticker} on {day}")
        seen.add(ticker)

        for name in ("o", "h", "l", "c", "v"):
            check_number(item[name], name, ticker, day)
        if any(item[name] <= 0 for name in ("o", "h", "l", "c")):
            raise ValueError(f"Nonpositive OHLC: {ticker} on {day}")
        if item["v"] < 0:
            raise ValueError(f"Negative volume: {ticker} on {day}")
        if isinstance(item["t"], bool) or not isinstance(item["t"], int):
            raise ValueError(f"Invalid timestamp: {ticker} on {day}")
        row_day = datetime.fromtimestamp(item["t"] / 1000, UTC).astimezone(NEW_YORK).date()
        if row_day != day:
            raise ValueError(f"Wrong timestamp date: {ticker} on {day}")
        if item.get("vw") is not None:
            check_number(item["vw"], "vw", ticker, day)

        tickers.append(ticker)
        opens.append(float(item["o"]))
        highs.append(float(item["h"]))
        lows.append(float(item["l"]))
        closes.append(float(item["c"]))
        volumes.append(float(item["v"]))

        vwaps.append(
            None if item.get("vw") is None else float(item["vw"])
        )

        transactions.append(
            None if item.get("n") is None else int(item["n"])
        )

    return (
        dates,
        tickers,
        opens,
        highs,
        lows,
        closes,
        volumes,
        vwaps,
        transactions,
    )


def read_days(completed_date):
    if not (DAY_DIR / f"{completed_date}.json").is_file():
        raise ValueError(f"Missing completed daily file: {completed_date}")
    paths = sorted(
        path for path in DAY_DIR.glob("*.json")
        if date.fromisoformat(path.stem).isoformat() <= completed_date
    )

    cols = [[] for _ in range(9)]

    with ProcessPoolExecutor() as executor:
        results = executor.map(
            parse_day,
            paths,
        )

        for result in results:
            for i in range(9):
                cols[i].extend(result[i])

    return pd.DataFrame(
        {
            "date": cols[0],
            "ticker": cols[1],
            "open": cols[2],
            "high": cols[3],
            "low": cols[4],
            "close": cols[5],
            "volume": cols[6],
            "vwap": cols[7],
            "transactions": cols[8],
        }
    )


def read_splits():
    data = orjson.loads(SPLIT_FILE.read_bytes())

    split_map = {}

    for item in data["results"]:
        factor = (
            float(item["split_from"])
            /
            float(item["split_to"])
        )

        split_map.setdefault(
            item["ticker"],
            [],
        ).append(
            (
                item["execution_date"],
                factor,
            )
        )

    for ticker in split_map:
        split_map[ticker].sort()

    return split_map


def apply_splits(bars, split_map):
    if not split_map:
        return bars

    split_tickers = set(split_map)

    mask = bars["ticker"].isin(split_tickers)

    bars_clean = bars[~mask]
    bars_to_adjust = bars[mask]

    if bars_to_adjust.empty:
        return bars

    def adjust_group(group):
        group["ticker"] = group.name

        factors = np.ones(
            len(group),
            dtype=np.float64,
        )

        dates = group["date"].values

        for event_date, factor in split_map[group.name]:
            factors[dates < event_date] *= factor

        group["open"] *= factors
        group["high"] *= factors
        group["low"] *= factors
        group["close"] *= factors
        group["vwap"] *= factors
        group["volume"] /= factors

        return group

    bars_adjusted = (
        bars_to_adjust
        .groupby(
            "ticker",
            group_keys=False,
        )
        .apply(adjust_group)
    )

    return pd.concat(
        [
            bars_clean,
            bars_adjusted,
        ],
        ignore_index=True,
    )


def round_volume(volume):
    if not math.isfinite(volume) or volume < 0:
        raise ValueError(f"Invalid adjusted volume: {volume}")
    result = int(Decimal(str(volume)).to_integral_value(rounding=ROUND_HALF_UP))
    if result > 2**63 - 1:
        raise ValueError(f"Volume exceeds SQLite INTEGER range: {volume}")
    return result


def build_rows(bars):
    timestamps = {
        day: int(datetime.combine(day, clock_time.min, NEW_YORK).timestamp())
        for day in bars["date"].unique()
    }
    for (
        day, ticker, open_price, high, low, close, volume, vwap, transactions,
    ) in bars.itertuples(index=False, name=None):
        symbol = f"{ticker}.US"
        ts = timestamps[day]
        if not all(math.isfinite(price) and price > 0 for price in (open_price, high, low, close)):
            raise ValueError(f"Invalid adjusted OHLC: {symbol} on {day}")

        rounded_volume = round_volume(volume)
        turnover = None
        if not pd.isna(vwap) and math.isfinite(vwap) and vwap > 0:
            amount = vwap * volume
            if math.isfinite(amount):
                turnover = amount

        if high < max(open_price, low, close) or low > min(open_price, high, close):
            record = {
                "symbol": symbol, "timeframe": TIMEFRAME, "ts": ts,
                "open": open_price, "high": high, "low": low, "close": close,
                "reason": "bounds_conflict",
            }
            with INVALID_FILE.open("ab") as output:
                output.write(orjson.dumps(record) + b"\n")

        yield (
            symbol, TIMEFRAME, ts, open_price, high, low, close,
            rounded_volume, turnover,
        )


def save_bars(bars, status):
    temp_file = OUT_FILE.with_suffix(".sqlite3.tmp")
    bars = (
        bars.sort_values(["ticker", "date"], ignore_index=True)
        .groupby("ticker", group_keys=False)
        .tail(MAX_HISTORY)
        .reset_index(drop=True)
    )
    bars["date"] = pd.to_datetime(bars["date"]).dt.date
    temp_file.unlink(missing_ok=True)

    try:
        with closing(sqlite3.connect(temp_file)) as connection:
            with connection:
                connection.execute(SCHEMA)
                connection.executemany(
                    "INSERT INTO bars VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    build_rows(bars),
                )
                connection.execute(
                    "CREATE INDEX bars_by_time ON bars(timeframe, ts, symbol)"
                )
                connection.execute(
                    "CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
                )
                connection.executemany(
                    "INSERT INTO metadata VALUES (?, ?)",
                    [
                        ("completed_date", status[0]),
                        ("adjustment", "split_adjusted"),
                        ("volume_rounding", "half_up"),
                        ("source", "massive_grouped_daily"),
                        ("session", "massive_daily"),
                        ("turnover", "vwap_times_unrounded_volume"),
                    ],
                )

        if read_status() != status:
            raise ValueError("Daily update changed during build; keep the previous database")
        os.replace(temp_file, OUT_FILE)
    finally:
        temp_file.unlink(missing_ok=True)

    return len(bars)


def main():
    start = time.perf_counter()

    status = read_status()

    step = time.perf_counter()
    bars = read_days(status[0])
    print(f"read_days: {time.perf_counter() - step:.2f}s")

    step = time.perf_counter()
    split_map = read_splits()
    print(f"read_splits: {time.perf_counter() - step:.2f}s")

    step = time.perf_counter()
    bars = apply_splits(
        bars,
        split_map,
    )
    print(f"apply_splits: {time.perf_counter() - step:.2f}s")

    step = time.perf_counter()
    saved = save_bars(bars, status)
    print(f"save_bars: {time.perf_counter() - step:.2f}s")

    print(
        f"Saved {saved} rows through {status[0]}: {OUT_FILE}"
    )
    print(
        f"total: {time.perf_counter() - start:.2f}s"
    )


if __name__ == "__main__":
    main()
