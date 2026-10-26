import logging
import re
from time import perf_counter
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.common.responses import error_response

logger = logging.getLogger('meetflow.requests')


class RequestContextMiddleware:
    """Server-generated correlation IDs and logs without request values."""
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return
        identity = uuid4().hex
        scope.setdefault('state', {})['request_id'] = identity
        started, status, began = False, 500, perf_counter()

        async def send_with_context(message: Message):
            nonlocal started, status
            if message['type'] == 'http.response.start':
                started, status = True, message['status']
                MutableHeaders(scope=message)['X-Request-ID'] = identity
            await send(message)

        try:
            host = Headers(scope=scope).get('host', '')
            if not re.fullmatch(r'(127\.0\.0\.1|localhost)(:\d{1,5})?', host, re.I):
                await error_response(identity, 400, 'INVALID_INPUT', '访问地址不受支持。')(scope, receive, send_with_context)
            else:
                await self.app(scope, receive, send_with_context)
        except Exception:
            # An exception string can itself contain a password or body value.
            logger.error('request_id=%s code=INTERNAL_ERROR', identity)
            if started:
                raise RuntimeError('Response failed after headers were sent.') from None
            await error_response(identity, 500, 'INTERNAL_ERROR', '服务暂时无法完成请求。')(scope, receive, send_with_context)
        finally:
            route = getattr(scope.get('route'), 'path', '<unmatched>')
            method = scope['method'] if scope['method'] in {'GET','POST','PUT','PATCH','DELETE','HEAD','OPTIONS'} else 'OTHER'
            logger.info('request_id=%s method=%s route=%s status=%s elapsed_ms=%.2f',
                        identity, method, route, status, (perf_counter() - began) * 1000)
