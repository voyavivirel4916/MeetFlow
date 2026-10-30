"""Optional conventional WSGI entry; never infer TLS from request headers."""
import ipaddress

from app.common.config import ConfigurationError, load_settings
from app.main import create_app, validate_runtime


class PlatformClientAddress:
    """Only for the platform's WSGI server, which appends the final client IP."""
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        normalized = dict(environ)
        # Missing or malformed address shares the unknown-client rate limit.
        normalized['REMOTE_ADDR'] = ''
        normalized['REMOTE_PORT'] = '0'
        try:
            normalized['REMOTE_ADDR'] = str(ipaddress.ip_address(
                environ.get('HTTP_X_FORWARDED_FOR', '').split(',')[-1].strip()))
        except ValueError:
            pass
        # wsgi.url_scheme belongs to the server environment, not HTTP_* headers.
        # Keep it intact: the ordinary production middleware rejects plaintext.
        return self.app(normalized, start_response)


def create_wsgi_app(settings=None):
    config = settings if settings is not None else load_settings()
    if config.app_env != 'production' or config.trusted_proxies:
        raise ConfigurationError('WSGI hosting requires production settings without TCP proxy overrides.')
    # a2wsgi serves HTTP only; FastAPI lifespan is not run by this adapter.
    # The current lifespan performs this validation and holds no resources.
    validate_runtime(config)
    from a2wsgi import ASGIMiddleware
    return PlatformClientAddress(ASGIMiddleware(create_app(config)))
