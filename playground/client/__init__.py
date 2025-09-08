"""HTTPBin client example demonstrating the clientry module."""

from playground.client.endpoints import HTTPBinEndpoints
from playground.client.httpbin_client import HTTPBinClient
from playground.client.models import (
    HTTPBinResponse,
    JSONRequest,
    UploadRequest,
)

__all__ = [
    "HTTPBinClient",
    "HTTPBinEndpoints",
    "HTTPBinResponse",
    "JSONRequest",
    "UploadRequest",
]
