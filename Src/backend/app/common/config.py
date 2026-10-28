from pathlib import Path
from ipaddress import ip_network
from urllib.parse import urlsplit
import tempfile
import re
from typing import Literal

from pydantic import Field, SecretStr, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]


class ConfigurationError(RuntimeError):
    """A startup problem that can be shown without exposing configuration values."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix='MEETFLOW_',
        env_file=BACKEND_ROOT / '.env',
        env_file_encoding='utf-8',
        extra='forbid',
        hide_input_in_errors=True,
    )

    app_env: Literal['local', 'test', 'production'] = 'local'
    bind_host: Literal['127.0.0.1', '0.0.0.0'] = '127.0.0.1'
    public_origin: str = ''
    trusted_proxies: list[str] = Field(default_factory=list)
    smtp_host: str = ''
    smtp_port: int = Field(default=465, ge=1, le=65535)
    smtp_username: str = ''
    smtp_password: SecretStr = SecretStr('')
    smtp_sender: str = ''
    port: int = Field(default=8000, ge=1, le=65535)
    log_level: Literal['DEBUG', 'INFO', 'WARNING', 'ERROR'] = 'INFO'
    data_dir: Path = BACKEND_ROOT / 'data'
    frontend_dir: Path = BACKEND_ROOT.parent / 'frontend' / 'dist'

    @model_validator(mode='after')
    def resolve_data_directory(self):
        # The working directory must not silently select a different database later.
        if not self.data_dir.is_absolute():
            self.data_dir = BACKEND_ROOT / self.data_dir
        self.data_dir = self.data_dir.resolve()
        if not self.frontend_dir.is_absolute():
            self.frontend_dir = BACKEND_ROOT / self.frontend_dir
        self.frontend_dir = self.frontend_dir.resolve()
        if self.app_env != 'production':
            if self.bind_host != '127.0.0.1' or self.public_origin or self.trusted_proxies:
                raise ValueError('Public settings require production mode.')
        else:
            try:
                origin = urlsplit(self.public_origin)
                if (origin.scheme != 'https' or not origin.hostname or origin.username is not None
                        or origin.path or origin.query or origin.fragment
                        or any(ord(c) <= 32 or ord(c) == 127 for c in self.public_origin)):
                    raise ValueError()
                if not re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?', origin.hostname):
                    raise ValueError()
                if origin.port == 0:
                    raise ValueError()
                if origin.hostname in {'localhost', '127.0.0.1', '0.0.0.0'}:
                    raise ValueError()
                for proxy in self.trusted_proxies:
                    network = ip_network(proxy, strict=False)
                    if network.prefixlen == 0:
                        raise ValueError()
            except ValueError:
                raise ValueError('Production requires a fixed HTTPS origin and explicit proxy addresses.') from None
            if self.data_dir == (BACKEND_ROOT / 'data').resolve():
                raise ValueError('Production requires a separate data directory.')
        return self


def load_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as error:
        # Do not print Pydantic's input or exception context from a private .env.
        names = sorted({str(item['loc'][0]) if item['loc'] else 'public_settings' for item in error.errors()})
        raise ConfigurationError('Invalid configuration fields: ' + ', '.join(names)) from None


def prepare_runtime(settings: Settings) -> None:
    """Check the local data directory without creating or opening a database."""
    try:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(prefix='.meetflow-write-check-', dir=settings.data_dir) as probe:
            probe.write(b'check')
            probe.flush()
    except OSError:
        raise ConfigurationError('Data directory is not writable; check configuration and permissions.') from None
