"""Local same-origin API policy; absent browser headers remain usable by CLI clients."""
from urllib.parse import urlsplit

from starlette.datastructures import Headers

JSON_LIMIT = 256 * 1024
WRITE_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}


def same_origin(origin: str, scheme: str, host: str) -> bool:
    try:
        if any(ord(character) <= 32 or ord(character) == 127 for character in origin):
            return False
        source, target = urlsplit(origin), urlsplit(f'{scheme}://{host}')
        if source.scheme not in {'http', 'https'} or not source.hostname or source.username is not None:
            return False
        if source.path or source.query or source.fragment:
            return False
        def default(value):
            return value.port if value.port is not None else (443 if value.scheme == 'https' else 80)
        return (source.scheme, source.hostname, default(source)) == (target.scheme, target.hostname, default(target))
    except ValueError:
        return False


def policy_error(scope, headers: Headers):
    origins = headers.getlist('origin')
    if origins and (len(origins) != 1 or not same_origin(origins[0], scope['scheme'], headers.get('host', ''))):
        return 403, 'CSRF_REJECTED', '请求来源不受支持，请从本机页面操作。'
    fetch_site = headers.get('sec-fetch-site')
    if fetch_site is not None and fetch_site not in {'same-origin', 'none'}:
        return 403, 'CSRF_REJECTED', '请求来源不受支持，请从本机页面操作。'
    if scope['method'] in WRITE_METHODS:
        if headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
            return 400, 'INVALID_INPUT', '写入请求须使用application/json。'
    length = headers.get('content-length')
    if length is not None:
        if not length.isascii() or not length.isdigit():
            return 400, 'INVALID_INPUT', '请求长度无效。'
        if len(length) > 10 or int(length) > JSON_LIMIT:
            return 413, 'PAYLOAD_TOO_LARGE', '请求内容超过256KiB限制。'
    return None


async def bounded_body(receive):
    chunks, total = [], 0
    while True:
        message = await receive()
        if message['type'] == 'http.disconnect':
            return None
        body = message.get('body', b'')
        total += len(body)
        if total > JSON_LIMIT:
            return None
        chunks.append(body)
        if not message.get('more_body', False):
            return b''.join(chunks)
