#!/usr/bin/env python3
"""Generate bounded, read-only real-data parity cases for the Kotlin translation."""
import json
import math
import sqlite3
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from data_service.features.snapshot import feature_row
from data_service.list_rules import apply_rules


def clean(value):
    if isinstance(value, dict):
        return {k: clean(v) for k,v in value.items()}
    if isinstance(value, list):
        return [clean(v) for v in value]
    if isinstance(value, (float, int)):
        return value if math.isfinite(value) else None
    if value is None or value is pd.NA:
        return None
    if hasattr(value, 'isoformat'):
        return value.isoformat()[:10]
    if hasattr(value, 'item'):
        return clean(value.item())
    return value


def main():
    output = ROOT/'android/.tools/reference'
    output.mkdir(parents=True,exist_ok=True)
    day = max((ROOT/'runtime/days').glob('*/scan.json')).parent.name
    snapshot = json.loads((ROOT/f'runtime/days/{day}/scan.json').read_text())
    workspace = json.loads((ROOT/f'runtime/days/{day}/workspace.json').read_text())
    preferences = json.loads((ROOT/'runtime/preferences.json').read_text())
    tickers = sorted({r['symbol'] for r in snapshot['rows'] if r.get('candidate')})[:15]
    tickers += [f'{t}.US' for t in list(workspace['statuses'])[:10]]+['AAPL.US','NVDA.US','TSLA.US']
    cases=[]
    with sqlite3.connect((ROOT/'runtime/massive/daily.sqlite3').as_uri()+'?mode=ro',uri=True) as db:
        for symbol in dict.fromkeys(tickers):
            records=db.execute("SELECT ts,open,high,low,close,volume,turnover FROM bars WHERE symbol=? AND timeframe='1d' ORDER BY ts DESC LIMIT 1000",(symbol,)).fetchall()[::-1]
            for length in ([len(records),1,4,19,20,49,50,54] if symbol=='AAPL.US' else [len(records)]):
                rows=records[:length]
                frame=pd.DataFrame(rows,columns=['ts','open','high','low','close','volume','turnover'])
                frame['date']=pd.to_datetime(frame['ts'],unit='s',utc=True).dt.tz_convert('America/New_York').dt.tz_localize(None).dt.normalize()
                frame['symbol']=symbol
                expected=clean(feature_row(frame))
                cases.append({'symbol':symbol,'bars':rows,'expected':expected})
    (output/'features.json').write_text(json.dumps(cases,allow_nan=False))
    # Rules are compared without live earnings enrichment; the same feature rows enter both implementations.
    result=apply_rules(workspace,snapshot,preferences,day)
    (output/'rules.json').write_text(json.dumps({'date':day,'snapshot':snapshot,'workspace':workspace,'preferences':preferences,'expected':result},allow_nan=False))
    device = ROOT/'android/app/src/androidTest/assets'
    device.mkdir(parents=True,exist_ok=True)
    fields=['symbol','close','adr20','mdv20','eligible','candidate','rfl1m_rank','rfl3m_rank','rfl6m_rank']
    (device/'scan-reference.json').write_text(json.dumps({'date':day,'rows':[{k:r.get(k) for k in fields} for r in snapshot['rows']]},allow_nan=False))
    print(f'Reference: {len(cases)} real-data histories; current three-list classification')


if __name__=='__main__':
    main()
