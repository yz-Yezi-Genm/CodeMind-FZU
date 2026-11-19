"""Runtime configuration for the FastAPI application."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ALPHA_PACKAGE_DIR = PROJECT_ROOT / "knowledge_base/processed/alpha/approved"

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


def _parse_bounded_int(
    name: str,
    default: int,
    *,
    minimum: int,
    maximum: int,
) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ConfigurationError(f"{name} 必须是整数。") from exc
    if not minimum <= value <= maximum:
        raise ConfigurationError(
            f"{name} 必须在 {minimum} 到 {maximum} 之间。"
        )
    return value


def _parse_package_dir(raw_value: str | None) -> Path:
    if raw_value is None or not raw_value.strip():
        return DEFAULT_ALPHA_PACKAGE_DIR
    path = Path(raw_value.strip()).expanduser()
    return path if path.is_absolute() else (PROJECT_ROOT / path).resolve()


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
    alpha_package_dir: Path = DEFAULT_ALPHA_PACKAGE_DIR
    conversation_max_messages: int = 12
    conversation_history_char_limit: int = 6000

    @classmethod
    def from_env(cls) -> "AppSettings":
        return cls(
            cors_allow_origins=_parse_origins(os.getenv("CORS_ALLOW_ORIGINS")),
            alpha_package_dir=_parse_package_dir(os.getenv("ALPHA_PACKAGE_DIR")),
            conversation_max_messages=_parse_bounded_int(
                "CONVERSATION_MAX_MESSAGES",
                12,
                minimum=2,
                maximum=50,
            ),
            conversation_history_char_limit=_parse_bounded_int(
                "CONVERSATION_HISTORY_CHAR_LIMIT",
                6000,
                minimum=200,
                maximum=50000,
            ),
        )
