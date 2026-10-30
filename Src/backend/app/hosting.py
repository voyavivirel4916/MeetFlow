"""PythonAnywhere entry point: trust headers only on its exact Unix socket."""
import ipaddress
import os
from urllib.parse import urlsplit
from uuid import uuid4

from starlette.datastructures import Headers

from app.common.config import ConfigurationError, load_settings
from app.common.responses import error_response
from app.main import create_app


def protocol_diagnostics(scope, headers):
    """Expose only protocol classifications, never cookies or raw headers."""
    names = ('x-forwarded-proto', 'x-forwarded-protocol', 'x-url-scheme',
             'x-scheme', 'x-forwarded-ssl', 'front-end-https', 'https')
    allowed = {'http', 'https', 'on', 'off', '1', '0'}
    return {
        'scheme': scope.get('scheme') if scope.get('scheme') in {'http', 'https'} else 'other',
        'protocol_headers': {
            name: [value if value in allowed else 'other' for value in headers.getlist(name)]
            for name in names if name in headers
        },
    }


def expected_socket(settings, actual):
    domain = urlsplit(settings.public_origin).hostname
    expected = f'/var/sockets/{domain}/app.sock'
    if settings.app_env != 'production' or not actual or actual != expected:
        raise ConfigurationError('Hosting requires production settings and the exact platform domain socket.')
    return expected


class DomainSocketHeaders:
    def __init__(self, app, socket_path):
        self.app, self.socket_path = app, socket_path

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        # Never reinterpret headers on TCP or already rewritten client addresses.
        if scope.get('server') != (self.socket_path, None) or scope.get('client') is not None:
            return await error_response(uuid4().hex, 400, 'INVALID_TRANSPORT',
                                        '访问通道不受支持。')(scope, receive, send)
        headers = Headers(scope=scope)
        forwarded = headers.getlist('x-forwarded-proto')
        if forwarded != ['https']:
            return await error_response(uuid4().hex, 400, 'HTTPS_REQUIRED',
                                        '请使用HTTPS地址访问。',
                                        protocol_diagnostics(scope, headers))(scope, receive, send)
        normalized = dict(scope, scheme='https')
        addresses = headers.getlist('x-forwarded-for')
        if len(addresses) == 1:
            try:
                # PythonAnywhere guarantees only the final item, never the first.
                address = str(ipaddress.ip_address(addresses[0].split(',')[-1].strip()))
                normalized['client'] = (address, 0)
            except ValueError:
                pass  # Keep aggregate unknown-client limits; do not trust arbitrary text.
        await self.app(normalized, receive, send)


def create_socket_app():
    settings = load_settings()
    socket_path = expected_socket(settings, os.environ.get('DOMAIN_SOCKET'))
    return DomainSocketHeaders(create_app(settings), socket_path)
