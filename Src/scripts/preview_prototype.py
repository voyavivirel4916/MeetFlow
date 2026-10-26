"""Serve only the T02 prototype on localhost, optionally opening the browser."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import webbrowser

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description='Preview the MeetFlow T02 prototype.')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    SimpleHTTPRequestHandler.extensions_map['.mjs'] = 'text/javascript; charset=utf-8'
    handler = partial(SimpleHTTPRequestHandler, directory=str(ROOT / 'Src/prototype'))
    try:
        server = ThreadingHTTPServer(('127.0.0.1', args.port), handler)
    except OSError as error:
        parser.exit(1, f'Cannot start preview: {error}. Try --port 8766.\n')
    url = f'http://127.0.0.1:{server.server_port}/'
    print(f'MeetFlow T02 prototype: {url}', flush=True)
    print('Keep this window open. Press Ctrl+C to stop.', flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
