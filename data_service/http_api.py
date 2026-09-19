from __future__ import annotations

import asyncio
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

log = logging.getLogger(__name__)


def start_http(service, port: int, cors_origin: str | None = None):
    loop = asyncio.get_running_loop()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            future = None
            try:
                url = urlsplit(self.path)
                if len(self.path) > 8192:
                    raise ValueError('Request URL too long')
                future = asyncio.run_coroutine_threadsafe(service.api(url.path, parse_qs(url.query)), loop)
                body, status = future.result(timeout=30), 200
            except (ValueError, TypeError) as exc:
                body, status = {'error': str(exc)}, 400
            except KeyError:
                body, status = {'error': 'Not found'}, 404
            except TimeoutError:
                if future:
                    future.cancel()
                body, status = {'error': 'Data service busy'}, 503
            except Exception:
                log.exception('HTTP request failed')
                body, status = {'error': 'Internal data service error'}, 500
            payload = json.dumps(body, ensure_ascii=False, allow_nan=False).encode()
            try:
                self.send_response(status)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(payload)))
                self.send_header('Cache-Control', 'no-store')
                if cors_origin:
                    self.send_header('Access-Control-Allow-Origin', cors_origin)
                self.end_headers()
                self.wfile.write(payload)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, name='local-http', daemon=True)
    thread.start()
    log.info('Data API listening http://127.0.0.1:%d', server.server_port)
    return server
