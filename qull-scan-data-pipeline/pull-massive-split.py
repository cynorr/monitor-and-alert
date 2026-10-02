"""
Pull Massive stock splits and keep one complete local split history.

Input:
- Massive API: https://api.massive.com/stocks/v1/splits returns stock split events.
- massive/splits.json, example: massive/splits.json, if a local snapshot already exists.
- Date: Auto uses today after 18:00 ET, otherwise yesterday.
- Environment: MASSIVE_API_KEY.

Output:
- massive/splits.json, example: massive/splits.json.
- Fields: status, start_date, end_date, resultsCount, results.
- Keeps older local history and replaces the latest two-year window with fresh Massive data.

Run:
- Auto (default): python pull-massive-split.py
- Auto refreshes all split data still available from the Massive Free plan.

Notes:
- Refresh the latest two years so late Massive fixes or added split events are picked up.
- Drop old rows in the refresh window before adding fresh rows so updates do not need ID matching.
- Keep rows before the refresh window so local history can grow past the two-year API limit.
- Require unique IDs so duplicate split events fail instead of being hidden.
- Validate every API page before replacing splits.json so a failed pull cannot damage the last good file.
- Fail if old coverage cannot join the current refresh window without a gap.
"""

import json
import os
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import ProxyHandler, Request, build_opener
from zoneinfo import ZoneInfo

BASE_URL = "https://api.massive.com/stocks/v1/splits"
OUT_FILE = Path(__file__).resolve().parent / "massive" / "splits.json"
MASSIVE_TOKEN = "wpl22mfUYfIxvXlitvvVvrdS1w_0LRgH"  # os.getenv("MASSIVE_API_KEY", "").strip()

USE_PROXY = True
HTTP_PROXY = "http://127.0.0.1:7899"
HTTPS_PROXY = "http://127.0.0.1:7899"

ET_ZONE = "America/New_York"
MATURE_HOUR_ET = 18
REFRESH_YEARS = 2
LIMIT = 5000
WAIT_SECONDS = 15
RETRY_COUNT = 3
RETRY_SECONDS = 30
TIMEOUT_SECONDS = 60

FIELDS = {
    "id",
    "ticker",
    "execution_date",
    "adjustment_type",
    "split_from",
    "split_to",
}


def read_date(value, name):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Invalid {name}: {value}") from error


def check_rows(results, start_date, end_date):
    ids = set()

    for row in results:
        if not isinstance(row, dict) or not FIELDS.issubset(row):
            raise ValueError("A split row is missing a required field.")

        split_id = row["id"]
        if not isinstance(split_id, str) or not split_id:
            raise ValueError("A split row has an invalid id.")
        if split_id in ids:
            raise ValueError(f"Duplicate split id: {split_id}")
        ids.add(split_id)

        execution_date = read_date(row["execution_date"], "execution_date")
        if not start_date <= execution_date <= end_date:
            raise ValueError(f"Split date is outside the covered range: {execution_date}")

        if not isinstance(row["ticker"], str) or not row["ticker"]:
            raise ValueError("A split row has an empty ticker.")
        if not isinstance(row["split_from"], (int, float)) or row["split_from"] <= 0:
            raise ValueError(f"Invalid split_from for {row['ticker']}.")
        if not isinstance(row["split_to"], (int, float)) or row["split_to"] <= 0:
            raise ValueError(f"Invalid split_to for {row['ticker']}.")

    return sorted(
        results,
        key=lambda row: (row["execution_date"], row["ticker"], row["id"]),
    )


def read_existing():
    if not OUT_FILE.exists():
        return None

    try:
        data = json.loads(OUT_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Invalid local split file: {OUT_FILE}") from error

    if not isinstance(data, dict) or data.get("status") != "OK":
        raise RuntimeError(f"Invalid local split file: {OUT_FILE}")

    start_date = read_date(data.get("start_date"), "start_date")
    end_date = read_date(data.get("end_date"), "end_date")
    if start_date > end_date:
        raise RuntimeError("Local split start_date is after end_date.")

    results = data.get("results")
    if not isinstance(results, list):
        raise RuntimeError("Local split results is not a list.")
    if data.get("resultsCount") != len(results):
        raise RuntimeError("Local split resultsCount does not match results.")

    try:
        results = check_rows(results, start_date, end_date)
    except ValueError as error:
        raise RuntimeError(f"Invalid local split data: {error}") from error

    return {
        "start_date": start_date,
        "end_date": end_date,
        "results": results,
    }


def get_target_date():
    now = datetime.now(ZoneInfo(ET_ZONE))
    if now.hour < MATURE_HOUR_ET:
        return now.date() - timedelta(days=1)
    return now.date()


def shift_year(value, years):
    try:
        return value.replace(year=value.year + years)
    except ValueError:
        return value.replace(year=value.year + years, day=28)


def build_url(start_date, end_date):
    query = urlencode(
        {
            "execution_date.gte": start_date.isoformat(),
            "execution_date.lte": end_date.isoformat(),
            "limit": LIMIT,
            "sort": "execution_date.asc",
        }
    )
    return f"{BASE_URL}?{query}"


def build_http():
    if not USE_PROXY:
        return build_opener(ProxyHandler({}))

    return build_opener(
        ProxyHandler(
            {
                "http": HTTP_PROXY,
                "https": HTTPS_PROXY,
            }
        )
    )


def build_request(url, key):
    return Request(
        url,
        headers={
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
            "User-Agent": "qull-scan/1.0",
        },
    )


def wait_call(last_call):
    wait = WAIT_SECONDS - (time.monotonic() - last_call)
    if wait > 0:
        time.sleep(wait)
    return time.monotonic()


def read_error(error):
    try:
        return error.read().decode("utf-8", errors="replace")[:500]
    except Exception:
        return ""


def read_delay(error):
    value = error.headers.get("Retry-After") if error.headers else None
    try:
        return max(RETRY_SECONDS, int(value))
    except (TypeError, ValueError):
        return RETRY_SECONDS


def check_page(data, start_date, end_date):
    if not isinstance(data, dict):
        raise ValueError("API response is not a JSON object.")
    if data.get("status") != "OK":
        raise ValueError(f"API status is not OK: {data.get('status')}")

    results = data.get("results", [])
    if not isinstance(results, list):
        raise ValueError("API results is not a list.")

    for row in results:
        if not isinstance(row, dict) or not FIELDS.issubset(row):
            raise ValueError("A split row is missing a required field.")

        execution_date = read_date(row["execution_date"], "execution_date")
        if not start_date <= execution_date <= end_date:
            raise ValueError(f"Split date is outside the requested range: {execution_date}")

        if not isinstance(row["id"], str) or not row["id"]:
            raise ValueError("A split row has an invalid id.")
        if not isinstance(row["ticker"], str) or not row["ticker"]:
            raise ValueError("A split row has an empty ticker.")
        if not isinstance(row["split_from"], (int, float)) or row["split_from"] <= 0:
            raise ValueError(f"Invalid split_from for {row['ticker']}.")
        if not isinstance(row["split_to"], (int, float)) or row["split_to"] <= 0:
            raise ValueError(f"Invalid split_to for {row['ticker']}.")

    next_url = data.get("next_url")
    if next_url is not None and not isinstance(next_url, str):
        raise ValueError("API next_url is not a string.")

    return results, next_url


def pull_page(http, url, key, start_date, end_date, last_call):
    for attempt in range(1, RETRY_COUNT + 1):
        last_call = wait_call(last_call)

        try:
            with http.open(build_request(url, key), timeout=TIMEOUT_SECONDS) as response:
                data = json.loads(response.read())

            results, next_url = check_page(data, start_date, end_date)
            return results, next_url, last_call

        except HTTPError as error:
            detail = read_error(error)

            if (error.code == 429 or error.code >= 500) and attempt < RETRY_COUNT:
                delay = read_delay(error)
                print(f"Retry HTTP {error.code}, wait {delay}s")
                time.sleep(delay)
                continue

            raise RuntimeError(f"HTTP {error.code}: {detail}") from error

        except (URLError, TimeoutError, json.JSONDecodeError, ValueError) as error:
            if attempt < RETRY_COUNT:
                print(f"Retry request, wait {RETRY_SECONDS}s: {error}")
                time.sleep(RETRY_SECONDS)
                continue

            raise RuntimeError(f"Request failed: {error}") from error

    raise RuntimeError("Request failed.")


def pull_split(start_date, end_date, key):
    http = build_http()
    url = build_url(start_date, end_date)
    results = []
    seen_urls = set()
    last_call = 0.0
    page_count = 0

    while url:
        if url in seen_urls:
            raise RuntimeError("API pagination repeated the same next_url.")
        seen_urls.add(url)

        rows, url, last_call = pull_page(
            http,
            url,
            key,
            start_date,
            end_date,
            last_call,
        )
        results.extend(rows)
        page_count += 1
        print(f"Read page {page_count}: {len(rows)}")

    try:
        return check_rows(results, start_date, end_date)
    except ValueError as error:
        raise RuntimeError(f"Invalid downloaded split data: {error}") from error


def merge_split(existing, fresh, refresh_start, target_end):
    if existing is None:
        start_date = refresh_start
        old_results = []
    else:
        if existing["end_date"] < refresh_start - timedelta(days=1):
            raise RuntimeError(
                "Local split coverage is too old for the current two-year refresh window. "
                "Restore an older splits.json backup."
            )
        if existing["end_date"] > target_end:
            raise RuntimeError("Local split end_date is later than the current mature ET date.")

        start_date = min(existing["start_date"], refresh_start)
        old_results = [
            row
            for row in existing["results"]
            if read_date(row["execution_date"], "execution_date") < refresh_start
        ]

    results = old_results + fresh

    try:
        results = check_rows(results, start_date, target_end)
    except ValueError as error:
        raise RuntimeError(f"Invalid merged split data: {error}") from error

    return {
        "status": "OK",
        "start_date": start_date.isoformat(),
        "end_date": target_end.isoformat(),
        "resultsCount": len(results),
        "results": results,
    }


def save_file(data):
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp_file = OUT_FILE.with_suffix(".json.tmp")

    temp_file.write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    os.replace(temp_file, OUT_FILE)


def main():
    existing = read_existing()
    target_end = get_target_date()
    refresh_start = shift_year(target_end, -REFRESH_YEARS)

    print(f"Refresh {refresh_start} to {target_end}")
    print(f"Save to {OUT_FILE}")

    fresh = pull_split(refresh_start, target_end, MASSIVE_TOKEN)
    data = merge_split(existing, fresh, refresh_start, target_end)
    save_file(data)

    ticker_count = len({row["ticker"] for row in data["results"]})
    print(f"Saved {data['resultsCount']} split events for {ticker_count} tickers.")
    print(f"Coverage {data['start_date']} to {data['end_date']}")


if __name__ == "__main__":
    main()
