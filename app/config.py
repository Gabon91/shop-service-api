import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values

from app.errors import ConfigurationError


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ORIGINS = (
    "http://localhost:5173",
    "http://localhost:3000",
    "https://shop-ui-react.vercel.app",
)


@dataclass(frozen=True)
class Settings:
    supabase_url: str = ""
    supabase_key: str = field(default="", repr=False)
    cors_origins: tuple[str, ...] = DEFAULT_ORIGINS

    @classmethod
    def from_env(cls, env_file: str | Path | None = None) -> "Settings":
        selected = env_file if env_file is not None else os.environ.get("ENV_FILE")
        if selected is None:
            local = Path.cwd() / ".env"
            selected = local if local.is_file() else PROJECT_ROOT / ".env"
        try:
            # Read without mutating process environment or interpolating other secrets.
            values = {**dotenv_values(selected, interpolate=False), **os.environ}
        except OSError:
            raise ConfigurationError("Unable to read the configured environment file") from None
        origins = values.get("CORS_ORIGINS", ",".join(DEFAULT_ORIGINS)) or ""
        return cls(
            supabase_url=(values.get("SUPABASE_URL") or "").strip(),
            supabase_key=(values.get("SUPABASE_KEY") or "").strip(),
            cors_origins=tuple(origin.strip() for origin in origins.split(",") if origin.strip()),
        )

    def validate_database(self) -> None:
        if not self.supabase_url or not self.supabase_key:
            raise ConfigurationError("SUPABASE_URL and SUPABASE_KEY must be configured")
        try:
            url = urlsplit(self.supabase_url)
            valid = (
                url.scheme in {"http", "https"}
                and bool(url.hostname)
                and not url.username
                and not url.password
                and not url.query
                and not url.fragment
            )
            url.port
        except ValueError:
            valid = False
        if not valid:
            raise ConfigurationError("SUPABASE_URL must be a valid HTTP(S) project URL")
