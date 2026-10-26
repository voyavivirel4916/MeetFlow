import logging
import sys

import uvicorn

from app.common.config import ConfigurationError, load_settings
from app.main import create_app


def main() -> int:
    try:
        settings = load_settings()
    except ConfigurationError as error:
        print(str(error), file=sys.stderr)
        return 2
    logging.basicConfig(level=settings.log_level, format='%(levelname)s %(name)s %(message)s')
    uvicorn.run(create_app(settings), host=settings.bind_host, port=settings.port,
                workers=1, access_log=False, log_config=None)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
