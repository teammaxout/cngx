"""Custom exceptions for Cogscope."""


class CogscopeError(Exception):
    """Base exception for all Cogscope errors."""

    pass


# ---- Client errors ----


class ClientError(CogscopeError):
    """Base for errors caused by client input or configuration."""

    pass


class ContractError(ClientError):
    """Raised when a contract is invalid or cannot be loaded."""

    pass


class ValidationError(ClientError):
    """Raised when input validation fails."""

    pass


# ---- Storage / lookup errors ----


class TraceNotFoundError(CogscopeError):
    """Raised when a reasoning trace cannot be found."""

    def __init__(self, trace_id: str):
        self.trace_id = trace_id
        super().__init__(f"Trace not found: {trace_id}")


class BaselineNotFoundError(CogscopeError):
    """Raised when a baseline cannot be found."""

    def __init__(self, baseline_name: str):
        self.baseline_name = baseline_name
        super().__init__(f"Baseline not found: {baseline_name}")


class StorageError(CogscopeError):
    """Raised when a storage operation fails."""

    pass


# ---- Capture / adapter errors ----


class CaptureError(CogscopeError):
    """Raised when trace capture fails."""

    pass


class AdapterError(CogscopeError):
    """Raised when an LLM adapter fails."""

    pass


# ---- Analysis errors ----


class FingerprintError(CogscopeError):
    """Raised when fingerprint extraction fails."""

    pass


class DiffError(CogscopeError):
    """Raised when diff computation fails."""

    pass


class DriftError(CogscopeError):
    """Raised when drift detection fails."""

    pass


class EvalError(CogscopeError):
    """Raised when evaluation fails."""

    pass


# ---- Configuration errors ----


class ConfigError(CogscopeError):
    """Raised when configuration is invalid."""

    pass


# ---- Cloud / auth errors ----


class AuthenticationError(CogscopeError):
    """Raised when API key authentication fails."""

    pass


class RateLimitError(CogscopeError):
    """Raised when rate limit is exceeded."""

    def __init__(self, retry_after: int = 60):
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded. Retry after {retry_after}s.")


class SecurityError(CogscopeError):
    """Raised for security-related failures (regex, input sanitization, etc.)."""

    pass
