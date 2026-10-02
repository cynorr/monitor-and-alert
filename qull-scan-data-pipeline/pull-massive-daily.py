"""
Update raw Massive daily bars from the latest date backward.

Input:
- https://api.massive.com/v2/aggs/grouped/locale/us/market/stocks/{date}
- Start from the latest expected daily date; first run looks back up to two years.

Output:
- massive/daily/2026-08-19.json
- Main fields: T, o, h, l, c, v, vw, n, t

Notes:
- Pull unadjusted non-OTC data.
- Recheck a 14-day repair window on later runs.
- Never save failed or empty responses.
"""

import json
import math
import os
import time
from datetime import UTC, date, datetime, time as clock_time, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener
from zoneinfo import ZoneInfo

MASSIVE_TOKEN = "wpl22mfUYfIxvXlitvvVvrdS1w_0LRgH"  # os.getenv("MASSIVE_API_KEY", "").strip()
PROXY_ENABLED = True
PROXY_URL = "http://127.0.0.1:7899"
REPAIR_DAYS = 14

BASE_URL = "https://api.massive.com/v2/aggs/grouped/locale/us/market/stocks"
OUT_DIR = Path(__file__).resolve().parent / "massive" / "daily"
HISTORY_YEARS = 2
EOD_HOUR = 18
REQUEST_INTERVAL = 13
RETRY_COUNT = 3
RETRY_WAIT = 15
TIMEOUT_SECONDS = 60

NEW_YORK = ZoneInfo("America/New_York")
REQUIRED_FIELDS = {"T", "o", "h", "l", "c", "v", "t"}


def get_end_date():
    now = datetime.now(NEW_YORK)
    day = now.date()

    if now.time() < clock_time(EOD_HOUR):
        day -= timedelta(days=1)

    while day.weekday() > 4:
        day -= timedelta(days=1)

    return day


def get_history_start(end_date):
    try:
        return end_date.replace(year=end_date.year - HISTORY_YEARS)
    except ValueError:
        return end_date.replace(year=end_date.year - HISTORY_YEARS, day=28)


def get_local_dates():
    days = []

    for path in OUT_DIR.glob("????-??-??.json"):
        try:
            days.append(date.fromisoformat(path.stem))
        except ValueError as error:
            raise RuntimeError(f"FILE ERROR: invalid file name {path.name}") from error

    return days


def get_start_date(end_date, local_dates):
    history_start = get_history_start(end_date)

    if not local_dates:
        return history_start

    latest_date = max(local_dates)
    if latest_date > end_date:
        raise RuntimeError(
            f"FILE ERROR: latest local date {latest_date} is after expected date {end_date}"
        )

    return max(history_start, latest_date - timedelta(days=REPAIR_DAYS))


def get_dates(start_date, end_date):
    day = end_date

    while day >= start_date:
        if day.weekday() < 5:
            yield day
        day -= timedelta(days=1)


def get_opener():
    proxies = {"http": PROXY_URL, "https": PROXY_URL} if PROXY_ENABLED else {}
    return build_opener(ProxyHandler(proxies))


def build_request(day):
    query = urlencode({"adjusted": "false", "include_otc": "false"})
    url = f"{BASE_URL}/{day.isoformat()}?{query}"

    return Request(
        url,
        headers={
            "Authorization": f"Bearer {MASSIVE_TOKEN}",
            "Accept": "application/json",
            "User-Agent": "qull-scan/2.0",
        },
    )


def wait_request(last_request):
    wait = REQUEST_INTERVAL - (time.monotonic() - last_request)
    if wait > 0:
        time.sleep(wait)
    return time.monotonic()


def get_http_detail(error):
    try:
        return error.read().decode("utf-8", errors="replace")[:300]
    except Exception:
        return ""


def get_retry_wait(error):
    value = error.headers.get("Retry-After") if error.headers else None
    try:
        return max(RETRY_WAIT, int(value))
    except (TypeError, ValueError):
        return RETRY_WAIT


def check_number(value, name, ticker):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"invalid {name} for {ticker}")
    if not math.isfinite(value):
        raise ValueError(f"invalid {name} for {ticker}")


def check_int(value, name, ticker):
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"invalid {name} for {ticker}")


def check_data(data, day):
    if not isinstance(data, dict):
        raise ValueError("response is not a JSON object")
    if data.get("status") != "OK":
        raise ValueError(f"status is {data.get('status')!r}")
    if data.get("adjusted") is not False:
        raise ValueError("response is not unadjusted")

    count = data.get("resultsCount")
    if isinstance(count, bool) or not isinstance(count, int):
        raise ValueError("resultsCount is missing or invalid")

    results = data.get("results", [])
    if not isinstance(results, list):
        raise ValueError("results is not a list")
    if count != len(results):
        raise ValueError(f"resultsCount={count}, rows={len(results)}")

    tickers = set()

    for row in results:
        if not isinstance(row, dict) or not REQUIRED_FIELDS.issubset(row):
            raise ValueError("a result row is missing a required field")

        ticker = row["T"]
        if not isinstance(ticker, str) or not ticker.strip():
            raise ValueError("a result row has an invalid ticker")
        if ticker in tickers:
            raise ValueError(f"duplicate ticker {ticker}")
        if row.get("otc") is True:
            raise ValueError(f"OTC ticker returned: {ticker}")
        tickers.add(ticker)

        for name in ("o", "h", "l", "c", "v"):
            check_number(row[name], name, ticker)

        check_int(row["t"], "t", ticker)

        if row.get("vw") is not None:
            check_number(row["vw"], "vw", ticker)
        if row.get("n") is not None:
            check_int(row["n"], "n", ticker)

        try:
            row_date = datetime.fromtimestamp(
                row["t"] / 1000, UTC
            ).astimezone(NEW_YORK).date()
        except (OSError, OverflowError, ValueError) as error:
            raise ValueError(f"invalid t for {ticker}") from error

        if row_date != day:
            raise ValueError(f"wrong date for {ticker}: {row_date}")

    return count


def pull_day(day, opener, last_request):
    request = build_request(day)

    for attempt in range(1, RETRY_COUNT + 1):
        last_request = wait_request(last_request)

        try:
            with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
                body = response.read()

        except HTTPError as error:
            if (error.code == 429 or error.code >= 500) and attempt < RETRY_COUNT:
                wait = get_retry_wait(error)
                print(f"Retry {day}: HTTP {error.code}, wait {wait}s")
                time.sleep(wait)
                continue

            detail = get_http_detail(error)
            message = f"HTTP ERROR: {day}: HTTP {error.code}"
            if detail:
                message += f": {detail}"
            raise RuntimeError(message) from error

        except (URLError, TimeoutError, ConnectionError) as error:
            if attempt < RETRY_COUNT:
                print(f"Retry {day}: network error, wait {RETRY_WAIT}s")
                time.sleep(RETRY_WAIT)
                continue

            raise RuntimeError(f"NETWORK ERROR: {day}: {error}") from error

        try:
            data = json.loads(body)
        except json.JSONDecodeError as error:
            raise RuntimeError(f"DATA ERROR: {day}: response is not valid JSON") from error

        try:
            count = check_data(data, day)
        except ValueError as error:
            raise RuntimeError(f"DATA ERROR: {day}: {error}") from error

        return body, count, last_request

    raise RuntimeError(f"NETWORK ERROR: {day}: request failed")


def read_day(path, day):
    try:
        body = path.read_bytes()
        data = json.loads(body)
        count = check_data(data, day)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise RuntimeError(f"FILE ERROR: {path}: {error}") from error

    if count == 0:
        raise RuntimeError(f"FILE ERROR: {path}: saved file has no data")

    return count


def save_day(path, body):
    temp_path = path.with_suffix(".json.tmp")

    try:
        temp_path.write_bytes(body)
        os.replace(temp_path, path)
    except OSError as error:
        raise RuntimeError(f"FILE ERROR: cannot save {path}: {error}") from error


def main():
    if not MASSIVE_TOKEN:
        raise RuntimeError("CONFIG ERROR: set MASSIVE_API_KEY")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    end_date = get_end_date()
    local_dates = get_local_dates()
    start_date = get_start_date(end_date, local_dates)
    days = list(get_dates(start_date, end_date))
    opener = get_opener()

    saved = 0
    skipped = 0
    no_data = 0
    last_request = 0.0

    print(f"Pull {end_date} back to {start_date}")
    print(f"Save to {OUT_DIR}")

    for index, day in enumerate(days, 1):
        path = OUT_DIR / f"{day.isoformat()}.json"

        if path.exists():
            count = read_day(path, day)
            skipped += 1
            print(f"[{index}/{len(days)}] Skip {day}: {count}")
            continue

        body, count, last_request = pull_day(day, opener, last_request)

        if count == 0:
            if day == end_date:
                raise RuntimeError(f"NO DATA: {day}: Massive returned 0 rows")

            no_data += 1
            print(f"[{index}/{len(days)}] No data {day}")
            continue

        save_day(path, body)
        saved += 1
        print(f"[{index}/{len(days)}] Save {day}: {count}")

    print(f"Done: saved={saved}, skipped={skipped}, no_data={no_data}")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as error:
        raise SystemExit(str(error))
