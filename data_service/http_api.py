from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from urllib.parse import urlsplit

from aiohttp import web, WSMsgType

UI_ROOT = Path(__file__).resolve().parents[1] / 'ui' / 'public'
log = logging.getLogger(__name__)


def create_app(service, cors_origin=None):
    @web.middleware
    async def errors(request, handler):
        try:
            response = await handler(request)
        except (ValueError, TypeError) as exc:
            response = web.json_response({'error': str(exc)}, status=400)
        except KeyError:
            response = web.json_response({'error': 'Not found'}, status=404)
        except (OSError, RuntimeError) as exc:
            log.warning('Request failed: %s', exc)
            response = web.json_response({'error': 'Request failed; please try again'}, status=503)
        response.headers['Cache-Control'] = 'no-store'
        if cors_origin and request.headers.get('Origin') == cors_origin:
            response.headers['Access-Control-Allow-Origin'] = cors_origin
        return response

    app = web.Application(middlewares=[errors], client_max_size=8192)
    sockets = set()

    async def shutdown(_app):
        await asyncio.gather(*(ws.close(code=1001, message=b'Service stopping') for ws in list(sockets)))

    app.on_shutdown.append(shutdown)

    async def api(request):
        query = {k: request.query.getall(k) for k in request.query}
        return web.json_response(await service.api(request.path, query), dumps=lambda v: json.dumps(v, allow_nan=False))

    async def mutate_list(request):
        origin = request.headers.get('Origin')
        if origin and origin != cors_origin and urlsplit(origin).netloc != request.host:
            raise web.HTTPForbidden(text='Origin not allowed')
        if request.content_type != 'application/json':
            raise web.HTTPUnsupportedMediaType()
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValueError('Expected a list action')
        return web.json_response(await service.mutate_list(payload))

    async def socket(request):
        origin = request.headers.get('Origin')
        if origin and origin != cors_origin and urlsplit(origin).netloc != request.host:
            raise web.HTTPForbidden(text='Origin not allowed')
        ws = web.WebSocketResponse(heartbeat=10, max_msg_size=8192)
        await ws.prepare(request)
        sockets.add(ws)
        symbol, tf = service.focus
        request_id = 0
        revisions = {}

        async def publish():
            nonlocal revisions
            last_board = 0
            try:
                while not ws.closed:
                    if asyncio.get_running_loop().time() - last_board >= 1:
                        await ws.send_json({'type': 'list', **service.list_state()})
                        last_board = asyncio.get_running_loop().time()
                    if symbol in service.symbols:
                        view = service.view(symbol, tf, revisions)
                        revisions = {period: chart['revision'] for period, chart in view['charts'].items()}
                        message = {'type': 'view', 'request_id': request_id, **view}
                        await ws.send_json(message, dumps=lambda v: json.dumps(v, allow_nan=False))
                    else:
                        revisions = {}
                    await asyncio.sleep(0.2)
            except (ConnectionError, RuntimeError):
                await ws.close()
            except Exception:
                log.exception('Chart stream failed')
                await ws.close(code=1011)

        sender = asyncio.create_task(publish())
        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        payload = json.loads(msg.data)
                        if payload.get('type') != 'select':
                            raise ValueError('Expected select message')
                        new_symbol, new_tf = payload['symbol'], payload['timeframe']
                        new_id = int(payload['request_id'])
                        service.select(new_symbol, new_tf)
                        symbol, tf, request_id = new_symbol, new_tf, new_id
                        revisions = {}
                    except (ValueError, TypeError, KeyError, AttributeError) as exc:
                        await ws.send_json({'type': 'error', 'error': str(exc)})
                elif msg.type == WSMsgType.ERROR:
                    break
        finally:
            sockets.discard(ws)
            sender.cancel()
            await asyncio.gather(sender, return_exceptions=True)
        return ws

    async def index(request):
        return web.FileResponse(UI_ROOT / 'index.html')

    app.router.add_get('/v1/stream', socket)
    app.router.add_post('/v1/list', mutate_list)
    app.router.add_get('/v1/{resource}', api)
    app.router.add_get('/health', api)
    app.router.add_get('/', index)
    app.router.add_static('/', UI_ROOT, show_index=False)
    return app


async def start_http(service, port: int, cors_origin: str | None = None):
    runner = web.AppRunner(create_app(service, cors_origin))
    await runner.setup()
    try:
        site = web.TCPSite(runner, '127.0.0.1', port)
        await site.start()
    except BaseException:
        await runner.cleanup()
        raise
    return runner
