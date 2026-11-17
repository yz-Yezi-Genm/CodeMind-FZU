"""Runtime configuration for the FastAPI application."""
from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlsplit


DEFAULT_CORS_ALLOW_ORIGINS = (
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5500",
    "http://127.0.0.1:5500",
)


class ConfigurationError(ValueError):
    """Raised when an environment-backed application setting is invalid."""


def _parse_origins(raw_value: str | None) -> tuple[str, ...]:
    if raw_value is None or not raw_value.strip():
        return DEFAULT_CORS_ALLOW_ORIGINS

    origins: list[str] = []
    for item in raw_value.split(","):
        origin = item.strip().rstrip("/")
        if not origin:
            continue
        if origin == "*":
            raise ConfigurationError(
                "CORS_ALLOW_ORIGINS 不允许使用通配符 *，请配置明确的开发来源。"
            )

        parsed = urlsplit(origin)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ConfigurationError(
                f"CORS_ALLOW_ORIGINS 中的来源格式无效: {origin}"
            )
        if origin not in origins:
            origins.append(origin)

    if not origins:
        raise ConfigurationError("CORS_ALLOW_ORIGINS 至少需要配置一个来源。")
    return tuple(origins)


@dataclass(frozen=True)
class AppSettings:
    """Application settings loaded from environment variables."""

    cors_allow_origins: tuple[str, ...] = DEFAULT_CORS_ALLOW_ORIGINS
    cors_allow_methods: tuple[str, ...] = ("GET", "POST", "PATCH", "OPTIONS")
    cors_allow_headers: tuple[str, ...] = ("Content-Type", "Authorization")

    @classmethod
    def from_env(cls) -> "AppSettings":
        return cls(
            cors_allow_origins=_parse_origins(os.getenv("CORS_ALLOW_ORIGINS")),
        )
