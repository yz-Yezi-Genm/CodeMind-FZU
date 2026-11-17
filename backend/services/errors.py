"""Internal service exceptions mapped to the public API error envelope."""
from __future__ import annotations


class ServiceError(RuntimeError):
    """A sanitized service failure that can be returned to an API caller."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "INTERNAL_ERROR",
        http_status: int = 500,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.http_status = http_status
        self.retryable = retryable


class ServiceContractError(ServiceError):
    """A collaborator returned a value that violates the Python contract."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            code="INTERNAL_ERROR",
            http_status=500,
            retryable=False,
        )


class LLMConfigurationError(ServiceError):
    """The model adapter is missing required configuration."""

    def __init__(self, message: str) -> None:
        super().__init__(
            message,
            code="SERVICE_NOT_CONFIGURED",
            http_status=503,
            retryable=True,
        )


class LLMTimeoutError(ServiceError):
    """The upstream model service timed out."""

    def __init__(self, message: str = "模型服务响应超时，请稍后重试。") -> None:
        super().__init__(
            message,
            code="MODEL_TIMEOUT",
            http_status=504,
            retryable=True,
        )


class LLMUnavailableError(ServiceError):
    """The upstream model service is temporarily unavailable."""

    def __init__(self, message: str = "模型服务暂时不可用，请稍后重试。") -> None:
        super().__init__(
            message,
            code="MODEL_UNAVAILABLE",
            http_status=503,
            retryable=True,
        )


class LLMResponseError(ServiceError):
    """The upstream model returned a response outside the adapter contract."""

    def __init__(self, message: str = "模型服务返回了无法识别的响应。") -> None:
        super().__init__(
            message,
            code="MODEL_UNAVAILABLE",
            http_status=502,
            retryable=False,
        )


class LLMRateLimitedError(ServiceError):
    """The upstream model service rejected requests due to rate limiting."""

    def __init__(self, message: str = "模型调用频率过高，请稍后重试。") -> None:
        super().__init__(
            message,
            code="RATE_LIMITED",
            http_status=429,
            retryable=True,
        )
