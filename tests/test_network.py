"""Offline shared HTTP configuration checks."""
import asyncio

import pytest

from data_service.network import create_session, proxy_url, read_massive_token


def test_explicit_proxy_default_override_and_direct_connection(monkeypatch):
    monkeypatch.delenv('MARKET_PROXY', raising=False)
    monkeypatch.setenv('HTTPS_PROXY', 'http://127.0.0.1:18081')
    assert proxy_url() == 'http://127.0.0.1:7899'
    monkeypatch.setenv('MARKET_PROXY', ' http://127.0.0.1:18080 ')
    assert proxy_url() == 'http://127.0.0.1:18080'
    monkeypatch.setenv('MARKET_PROXY', '')
    assert proxy_url() is None


def test_http_session_uses_source_timeout_and_ignores_environment_proxy():
    async def scenario():
        async with create_session(45) as session:
            assert session.timeout.total == 45
            assert session.trust_env is False
    asyncio.run(scenario())


def test_massive_token_prefers_environment_and_missing_config_is_clear(tmp_path, monkeypatch):
    path = tmp_path / 'massive-token.txt'
    path.write_text('file-test-token\n')
    monkeypatch.setenv('MASSIVE_API_KEY', ' environment-test-token ')
    assert read_massive_token(path) == 'environment-test-token'
    monkeypatch.delenv('MASSIVE_API_KEY')
    assert read_massive_token(path) == 'file-test-token'
    with pytest.raises(ValueError, match='^Massive credentials missing:'):
        read_massive_token(tmp_path / 'missing-token.txt')


@pytest.mark.parametrize('configured_proxy,expected', [('http://127.0.0.1:7899', 'http://127.0.0.1:7899'), ('', None)])
def test_massive_request_uses_shared_proxy_and_safe_http_errors(tmp_path, monkeypatch, configured_proxy, expected):
    from data_service import pipeline
    from data_service.paths import RuntimePaths
    monkeypatch.setenv('MARKET_PROXY', configured_proxy)
    monkeypatch.setattr(pipeline, 'read_massive_token', lambda path: 'test-secret')
    monkeypatch.setattr(pipeline, 'REQUEST_INTERVAL', 0)
    class Response:
        status = 200
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def read(self): return b'{"status":"OK"}'
    class Session:
        closed = False
        def __init__(self): self.response, self.requests = Response(), []
        def get(self, url, **kwargs):
            self.requests.append((url, kwargs))
            return self.response
        async def close(self): self.closed = True
    session = Session()
    monkeypatch.setattr(pipeline, 'create_session', lambda timeout: session)
    async def scenario():
        app = pipeline.MassivePipeline(RuntimePaths(tmp_path))
        assert await app._fetch_json('https://api.massive.com/example') == {'status': 'OK'}
        assert session.requests[0][1]['proxy'] == expected
        assert session.requests[0][1]['headers']['Authorization'] == 'Bearer test-secret'
        session.response.status = 503
        with pytest.raises(pipeline.RequestFailure, match='^Massive HTTP 503$'):
            await app._fetch_json('https://api.massive.com/private?cursor=sensitive')
        await app.close()
        assert session.closed
    asyncio.run(scenario())
