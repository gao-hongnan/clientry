"""Generic Request Pattern implementation for type-safe API clients."""

from clientry.base import BaseClient
from clientry.errors import ClientError, PermanentError, RetryableError
from clientry.types import EmptyRequest, EndpointConfig

__all__ = [
    "BaseClient",
    "EmptyRequest",
    "EndpointConfig",
    "ClientError",
    "PermanentError",
    "RetryableError",
]
