# Chart and Quote simulator

An isolated, continuous market for chart development: historical candles, live Quotes and new closed bars. No credentials or broker connection.

## Start

```bash
./simulator/start.command
```

The script uses the repository Python environment and installs the two simulator dependencies if needed. Open **http://127.0.0.1:18765/**. The regular production UI shows a small **SIM** badge. Ctrl+C stops both endpoints and removes the temporary database.

```bash
# Faster closed-bar testing: 10 exchange seconds per real second
./simulator/start.command --speed 10

# A chosen regular-session instant in New York time
./simulator/start.command --start 2026-09-18T13:44:45 --speed 30
```

Options: `--workspace`, `--symbols` (a subset of that workspace), `--port` (chart, default 18765), `--quote-port` (raw Quote, default 18766), `--speed` and `--start`.

## Data flow

```text
Synthetic session price path
  ├─ Quote → in-memory current candle
  └─ closed bar API → actual downloader / validator / BarScheduler
                         ↓
                    temporary SQLite
                         ↓
                 Data HTTP + WebSocket → UI
```

- Startup reads workspace focus/wait and its order, using the same loader as production.
- Every period has up to 1000 consistent closed bars: Daily, 5m, 15m, 30m and 1h. Count=2 and history-offset calls use the same market path.
- OHLC, volume and turnover across periods come from a deterministic session path. Quote cumulative volume is the same day's integral, not volume since process startup.
- The actual DataService scheduler initializes history and fetches closed bars after each boundary. Validation is enabled; READY is calculated, not forced.
- The exchange clock starts on the latest trading date in regular hours. It advances at the chosen speed and skips nights/weekends/holidays. Early closes follow the calendar. macOS time is unchanged.
- Quotes refresh five times per real second for the chart. The browser uses the normal snapshot and stream endpoints, with no simulation rendering branch.
- On restart, history regenerates in a new temporary directory. No simulated bars enter runtime/bars.sqlite3.

## Raw Quote WebSocket

**ws://127.0.0.1:18766/** remains available. Connect without a subscription message to receive one JSON per symbol per second. All clients share the same market and sequence.

Fields retain the Longbridge Quote JSON shape: symbol, sequence, last_done, open, high, low, timestamp, volume, turnover, trade_status, trade_session, current_volume, current_turnover, tag. Prices/turnover are strings; timestamp/volumes/status are integers. Session/status/tag are zero. Timestamps use the simulator exchange clock. This is not the Longbridge binary protocol.

## Maintenance

- market.py: price path, generated history, exchange clock and Quotes.
- server.py: isolated DataService instance, UI/API and raw Quote WebSocket lifecycle.
- start.command / requirements.txt: startup and dependencies.
- ../tests/test_simulator.py: period consistency, all-history completeness, actual scheduling across boundaries/session rollover, raw WebSocket and clock checks.
- ../tests/preview_fixture.py: compatibility entry point for this simulator; no separate fake data generator.

Production never imports simulator. The simulator imports the generic data workflow, without importing Broker or reading credentials. No fault-injection engine, replay, trading or Alert implementation is included. Offline simulation is not live broker evidence.
