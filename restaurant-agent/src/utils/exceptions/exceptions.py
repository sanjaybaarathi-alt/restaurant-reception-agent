"""Domain-specific exceptions handled at the API boundary."""


class AppError(Exception):
    def __init__(self, code: str, message: str, status_code: int, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retryable = retryable


class UpstreamError(AppError):
    """Safe representation of a supplied backend failure."""

    def __init__(self, code: str, message: str, status_code: int = 502, retryable: bool = False) -> None:
        super().__init__(code, message, status_code, retryable)
