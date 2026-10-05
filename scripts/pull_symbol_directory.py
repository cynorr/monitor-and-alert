"""One bounded Nasdaq Trader refresh, independent of the Massive downloader."""
import argparse
import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data_service.paths import RuntimePaths
from data_service import symbol_directory
from data_service.store import atomic_json


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, default=Path('runtime'))
    parser.add_argument('--nasdaq-file', type=Path, help='Import a complete local nasdaqlisted.txt')
    parser.add_argument('--other-file', type=Path, help='Import a complete local otherlisted.txt')
    args = parser.parse_args(argv)
    if bool(args.nasdaq_file) != bool(args.other_file):
        parser.error('--nasdaq-file and --other-file must be provided together')
    path = RuntimePaths(args.runtime).symbol_directory
    try:
        if args.nasdaq_file:
            snapshot = symbol_directory.combine(args.nasdaq_file.read_text(encoding='utf-8-sig'),
                                                args.other_file.read_text(encoding='utf-8-sig'))
            atomic_json(path, snapshot)
        else:
            snapshot = asyncio.run(symbol_directory.update(path))
    except (OSError, ValueError, symbol_directory.RequestFailure) as error:
        print(f'Symbol directory update failed: {error}', file=sys.stderr)
        return 2
    print(f"Symbol directory ready: {len(snapshot['symbols'])} symbols")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
