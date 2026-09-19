"""Bounded, read-only design probe; only workspace focus/wait symbols are eligible."""
import json
import asyncio
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from longbridge.openapi import AdjustType, Config, Period, AsyncQuoteContext, SubType, TradeSessions

ROOT = Path(__file__).resolve().parents[1]
ET = ZoneInfo('America/New_York')


async def main():
    os.environ['LONGBRIDGE_REGION'] = 'cn'
    workspace = json.loads((ROOT / 'workspace.json').read_text())
    allowed = {f'{symbol}.US' for symbol, entry in workspace['statuses'].items()
               if entry.get('status') in {'focus', 'wait'}}
    symbols = [s for s in ['PAYS.US', 'BLSH.US'] if s in allowed]
    if not symbols:
        raise ValueError('No eligible probe symbols; no API calls made')
    lines = [s.strip() for s in (ROOT / 'longbridge-token.txt').read_text().splitlines() if s.strip()]
    expected = ['App Key', 'App Secret', 'App Token']
    if len(lines) != 6 or lines[::2] != expected:
        raise ValueError('Unexpected credential file structure')
    secrets = lines[1::2]
    report = {'tested_at': datetime.now(timezone.utc).isoformat(),
              'allowed_count': len(allowed), 'symbols_requested': symbols, 'bars': [], 'quotes': [], 'pushes': []}

    def safe_error(exc):
        message = str(exc)
        for value in secrets:
            message = message.replace(value, '[REDACTED]')
        return message

    def quote_data(symbol, event):
        return {'symbol': symbol, 'timestamp': event.timestamp.astimezone(timezone.utc).isoformat(),
                'volume': event.volume, 'last_done': str(event.last_done),
                'trade_session': str(getattr(event, 'trade_session', 'snapshot regular fields'))}

    def on_quote(symbol, event):
        if symbol in symbols and len(report['pushes']) < 20:
            report['pushes'].append(quote_data(symbol, event))

    try:
        config = Config.from_apikey(*secrets, enable_print_quote_packages=False,
                                   http_url='https://openapi.longbridge.cn',
                                   quote_ws_url='wss://openapi-quote.longbridge.cn/v2')
        print('Connecting to official .cn endpoint', flush=True)
        ctx = AsyncQuoteContext.create(config)
        ctx.set_on_quote(on_quote)
        await asyncio.wait_for(ctx.subscribe(symbols, [SubType.Quote]), 15)
        report['quotes'] = [quote_data(q.symbol, q) for q in await asyncio.wait_for(ctx.quote(symbols), 15)]
        for symbol in symbols:
            periods = [('1d', Period.Day), ('5m', Period.Min_5), ('15m', Period.Min_15),
                       ('30m', Period.Min_30), ('1h', Period.Min_60)] if symbol == symbols[0] else [('1d', Period.Day)]
            for label, period in periods:
                assert symbol in allowed
                await asyncio.sleep(0.6)
                item = {'symbol': symbol, 'timeframe': label, 'requested': 1000}
                try:
                    bars = await asyncio.wait_for(ctx.candlesticks(symbol, period, 1000, AdjustType.NoAdjust, TradeSessions.Intraday), 15)
                    times = [b.timestamp.astimezone(ET) for b in bars]
                    counts = Counter(t.date().isoformat() for t in times)
                    item.update({'returned': len(bars), 'first': times[0].isoformat() if times else None,
                                 'last': times[-1].isoformat() if times else None,
                                 'recent_day_counts': dict(sorted(counts.items())[-15:]),
                                 'last_timestamps': [t.isoformat() for t in times[-14:]],
                                 'sessions': sorted({str(b.trade_session) for b in bars})})
                except Exception as exc:
                    item['error'] = safe_error(exc)
                report['bars'].append(item)
                print(json.dumps(item), flush=True)
                month = datetime.now(ET).strftime('%Y-%m')
                usage_path = ROOT / 'runtime/history_symbol_usage.json'
                usage = json.loads(usage_path.read_text()) if usage_path.exists() else {}
                usage[month] = sorted(set(usage.get(month, [])) | {symbol})
                usage_path.write_text(json.dumps(usage, indent=2) + '\n')
        await asyncio.sleep(15)
        await asyncio.wait_for(ctx.unsubscribe(symbols, [SubType.Quote]), 10)
    except Exception as exc:
        report['error'] = safe_error(exc)
    finally:
        output = ROOT / 'runtime/design_probe.json'
        output.write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps({'report': str(output), 'push_count': len(report['pushes']),
                          'error': report.get('error'), 'quotes': report['quotes']}), flush=True)


if __name__ == '__main__':
    if '--worker' in sys.argv:
        asyncio.run(main())
    else:
        try:
            result = subprocess.run([sys.executable, __file__, '--worker'], timeout=75)
            sys.exit(result.returncode)
        except subprocess.TimeoutExpired:
            print('Probe timed out after 75 seconds; worker stopped', flush=True)
            sys.exit(1)
