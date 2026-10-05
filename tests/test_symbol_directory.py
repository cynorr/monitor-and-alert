"""Offline checks for the two official files and atomic cache publication."""
import asyncio

import pytest

from data_service import symbol_directory as directory
from data_service.paths import RuntimePaths
from data_service.store import atomic_json
from scripts.pull_symbol_directory import main

NASDAQ_HEADER = 'Symbol|Security Name|Market Category|Test Issue|Financial Status|Round Lot Size|ETF|NextShares'
OTHER_HEADER = 'ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol'
CREATED = '1005202608:46'


def nasdaq(*rows):
    rows = rows or ('AAPL|Apple Inc. - Common Stock|Q|N|N|100|N|N',)
    return '\n'.join((NASDAQ_HEADER, *rows, f'File Creation Time: {CREATED}|||||||')) + '\n'


def other(*rows):
    rows = rows or ('SPY|SPDR S&P 500 ETF Trust|P|SPY|Y|100|N|SPY',)
    return '\n'.join((OTHER_HEADER, *rows, f'File Creation Time: {CREATED}||||||')) + '\n'


def test_primary_symbols_etf_flags_optional_names_and_source_footer():
    result = directory.combine(
        nasdaq('AAPL|Apple Inc. - Common Stock |Q|N|N|100|N|N', 'AAPLX|Leveraged ETF|Q|N|N|100|Y|N',
               'MISSING| |Q|N|N|100|N|N'),
        other('BRK.B|Berkshire Hathaway Class B|N|BRK.B|N|100|N|BRK/B',
              'UWMC.V|UWM Holdings Corporation Rights when issued|N|UWMCrw|N|100|N|UWMC^#'))
    assert result['symbols']['AAPL.US'] == {'name': 'Apple Inc. - Common Stock', 'etf': False}
    assert result['symbols']['AAPLX.US']['etf']
    assert result['symbols']['MISSING.US'] == {'name': None, 'etf': False}
    assert 'BRK.B.US' in result['symbols'] and 'BRK/B.US' not in result['symbols']
    assert 'UWMC.V.US' in result['symbols'] and 'UWMC^#.US' not in result['symbols']
    assert result['sources']['files']['otherlisted.txt']['creation_time'] == CREATED
    assert result['sources']['files']['nasdaqlisted.txt']['row_count'] == 3


@pytest.mark.parametrize('bad', [
    NASDAQ_HEADER + '\n',
    nasdaq().replace('ETF|', 'Fund|'),
    nasdaq().replace('|100|N|N', '|100|?|N'),
    nasdaq().replace('File Creation Time:', 'Incomplete:'),
    nasdaq().replace('|||||||\n', '||\n'),
    nasdaq().replace('|Q|N|N|100|N|N', '|Q|N|N|100|N'),
    nasdaq('AAPL|Apple|Q|N|N|100|N|N', 'AAPL|Apple|Q|N|N|100|N|N'),
])
def test_parser_rejects_incomplete_data_and_unknown_etf_classification(bad):
    with pytest.raises(ValueError):
        directory.parse_text(bad, 'nasdaqlisted.txt')


def test_failed_second_file_preserves_previous_cache_without_retry(tmp_path):
    path = RuntimePaths(tmp_path).symbol_directory
    atomic_json(path, directory.combine(nasdaq(), other()))
    before, calls = path.read_bytes(), []
    async def fetch(url):
        calls.append(url)
        return nasdaq() if url == directory.SOURCES['nasdaqlisted.txt'] else OTHER_HEADER + '\n'
    with pytest.raises(ValueError):
        asyncio.run(directory.update(path, fetch))
    assert calls == list(directory.SOURCES.values())
    assert path.read_bytes() == before


def test_pull_requests_two_free_files_and_cache_reader_supports_plain_mock(tmp_path):
    calls = []
    async def fetch(url):
        calls.append(url)
        return nasdaq() if url == directory.SOURCES['nasdaqlisted.txt'] else other()
    path = RuntimePaths(tmp_path).symbol_directory
    result = asyncio.run(directory.update(path, fetch))
    assert calls == list(directory.SOURCES.values())
    assert directory.read_directory(path) == result
    atomic_json(path, directory.make_snapshot({'MOCK.US': {'name': None, 'etf': False}}))
    assert directory.read_directory(path)['symbols']['MOCK.US']['name'] is None
    path.unlink()
    with pytest.raises(ValueError, match='pull_symbol_directory'):
        directory.read_directory(path)


def test_network_uses_shared_proxy_and_reports_http_failure(tmp_path, monkeypatch):
    monkeypatch.setenv('MARKET_PROXY', 'http://127.0.0.1:7899')
    class Response:
        status = 200
        def __init__(self, url): self.url = url
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def read(self):
            return (nasdaq() if self.url == directory.SOURCES['nasdaqlisted.txt'] else other()).encode()
    class Session:
        status = 200
        def __init__(self): self.requests = []
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        def get(self, url, **kwargs):
            self.requests.append((url, kwargs))
            response = Response(url)
            response.status = self.status
            return response
    session = Session()
    monkeypatch.setattr(directory, 'create_session', lambda timeout: session)
    asyncio.run(directory.update(RuntimePaths(tmp_path).symbol_directory))
    assert session.requests == [(url, {'proxy': 'http://127.0.0.1:7899'}) for url in directory.SOURCES.values()]
    session.status = 503
    with pytest.raises(directory.RequestFailure, match='^Nasdaq directory HTTP 503$'):
        asyncio.run(directory.update(RuntimePaths(tmp_path).symbol_directory))


def test_local_import_keeps_massive_independent_and_reports_parse_failure(tmp_path, capsys):
    first, second = tmp_path / 'nasdaq.txt', tmp_path / 'other.txt'
    first.write_text(nasdaq())
    second.write_text(other())
    runtime = tmp_path / 'runtime'
    args = ['--runtime', str(runtime), '--nasdaq-file', str(first), '--other-file', str(second)]
    assert main(args) == 0
    assert directory.read_directory(RuntimePaths(runtime).symbol_directory)['symbols']['SPY.US']['etf']
    assert not (runtime / 'massive').exists()
    assert 'Symbol directory ready' in capsys.readouterr().out
    second.write_text(OTHER_HEADER)
    assert main(args) == 2
    assert 'update failed' in capsys.readouterr().err
