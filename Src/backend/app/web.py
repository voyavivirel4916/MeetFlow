"""Install after API routes: SPA documents must never replace API/asset errors."""
from html.parser import HTMLParser
from urllib.parse import unquote, urlsplit

from fastapi import FastAPI, HTTPException
from starlette.responses import FileResponse
from starlette.staticfiles import StaticFiles

from app.common.config import ConfigurationError, Settings


class BuildReferences(HTMLParser):
    def __init__(self):
        super().__init__()
        self.references = []
        self.has_module = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'script' and attrs.get('src'):
            self.references.append(attrs['src'])
            self.has_module |= attrs.get('type') == 'module'
        if tag == 'link' and attrs.get('rel') in {'stylesheet', 'modulepreload'} and attrs.get('href'):
            self.references.append(attrs['href'])


def check_frontend(settings: Settings):
    try:
        index = settings.frontend_dir / 'index.html'
        if not index.is_file() or not (settings.frontend_dir / 'assets').is_dir():
            raise OSError
        parser = BuildReferences()
        parser.feed(index.read_text(encoding='utf-8'))
        if not parser.has_module:
            raise OSError
        for reference in parser.references:
            url = urlsplit(reference)
            asset = (settings.frontend_dir / unquote(url.path).lstrip('/')).resolve()
            if (url.scheme or url.netloc or not asset.is_relative_to(settings.frontend_dir / 'assets')
                    or not asset.is_file()):
                raise OSError
            with asset.open('rb') as source:
                if not source.read(1):
                    raise OSError
    except (OSError, ValueError, UnicodeError):
        raise ConfigurationError('Frontend build missing or unreadable; run npm ci and npm run build in Src/frontend.') from None


def install_frontend(app: FastAPI, settings: Settings):
    app.mount('/assets', StaticFiles(directory=settings.frontend_dir / 'assets', check_dir=False), name='assets')

    @app.api_route('/{path:path}', methods=['GET', 'HEAD'], include_in_schema=False)
    def frontend(path: str):
        # Only the SPA entry is served here; no arbitrary filesystem paths are opened.
        parts = path.split('/')
        if (parts[0] in {'api', 'assets', 'livez', 'openapi.json', 'docs', 'redoc'}
                or any('.' in part or '\\' in part for part in parts)):
            raise HTTPException(404)
        return FileResponse(settings.frontend_dir / 'index.html', media_type='text/html',
                            headers={'Cache-Control': 'no-cache', 'X-Content-Type-Options': 'nosniff'})
