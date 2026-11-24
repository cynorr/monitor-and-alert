#!/usr/bin/env python3
"""Read-only export from the Mac runtime. Never import a service entry point or credentials."""
import argparse
import json
import re
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from data_service.calendar import TradingCalendar


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', type=Path, default=ROOT / 'runtime')
    args = parser.parse_args()
    assets = ROOT / 'android/app/src/main/assets'
    assets.mkdir(parents=True, exist_ok=True)
    calendar = TradingCalendar()
    from datetime import date
    sessions = {d.isoformat(): calendar.session(d) for d in calendar.days(date(2024, 1, 2), date(2028, 12, 29))}
    (assets / 'sessions.json').write_text(json.dumps(sessions))
    for source, name in [(ROOT / 'config/scan.json', 'scan.json'), (ROOT / 'ui/src/filter-catalog.json', 'filter-catalog.json')]:
        (assets / name).write_bytes(source.read_bytes())
    palette = dict(re.findall(r"(\w+):\s*'(#[0-9a-fA-F]{6})'", (ROOT / 'ui/src/palette.ts').read_text()))
    (assets / 'palette.json').write_text(json.dumps(palette))
    from data_service.additional_info import nasdaq
    (assets / 'company-name-patterns.json').write_text(json.dumps({name: getattr(nasdaq, name).pattern for name in ['PREFERRED_NOTES', 'COUPON_SUFFIX', 'RATE_SUFFIX', 'SECURITY_SUFFIX']}))
    day = max(p.parent.name for p in (args.runtime / 'days').glob('*/workspace.json'))
    output = assets / 'seed.zip'
    with tempfile.TemporaryDirectory(dir=ROOT / 'android/.tools') as temporary, zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=3) as archive:
        for relative in ['massive/daily.sqlite3', 'additional-info/info.sqlite3']:
            source = args.runtime / relative
            if not source.exists():
                continue
            target = Path(temporary) / Path(relative).name
            with sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True) as src, sqlite3.connect(target) as dst:
                src.backup(dst)
            archive.write(target, relative)
        for relative in ['preferences.json', 'symbol-directory.json', 'massive/splits.json']:
            archive.write(args.runtime / relative, relative)
        for directory in sorted((args.runtime / 'days').iterdir()):
            if not directory.is_dir():
                continue
            for name in ['workspace.json', 'scan.json']:
                path = directory / name
                if path.exists():
                    archive.write(path, f'days/{directory.name}/{name}')
        for path in sorted((args.runtime / 'massive/daily').glob('*.json')):
            archive.write(path, f'massive/daily/{path.name}')
        archive.writestr('seed-info.json', json.dumps({'workspace_date': day, 'credentials': False}))
    print(f'Seed ready: {day}; {output.stat().st_size / 1024**2:.1f} MiB; no credentials')


if __name__ == '__main__':
    main()
