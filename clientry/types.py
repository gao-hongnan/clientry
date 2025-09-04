"""Type definitions for the generic client pattern."""

from __future__ import annotations

from collections.abc import AsyncIterable, Iterable
from typing import Any, Generic, Literal, Mapping, TypeVar

from pydantic import BaseModel, ConfigDict

RequestT = TypeVar("RequestT", bound=BaseModel)
ResponseT = TypeVar("ResponseT", bound=BaseModel)

HTTPMethod = Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
StatusCode = int
Headers = Mapping[str, str]
RequestID = str | None
ResponseBody = str | bytes | None

FilesParam = Mapping[str, Any]
StreamContent = bytes | str | Iterable[bytes] | AsyncIterable[bytes]


class EmptyRequest(BaseModel):
    """Canonical empty request for endpoints with no request body.

    Use this for GET, DELETE, HEAD endpoints that don't accept request data.
    This ensures type consistency across the Generic Request Pattern.

    Examples
    --------
    >>> GET_ENDPOINT = EndpointConfig[EmptyRequest, UserResponse](
    ...     path="/users/{id}",
    ...     method="GET",
    ...     request_type=EmptyRequest,
    ...     response_type=UserResponse,
    ... )
    """

    model_config = ConfigDict(frozen=True, extra="forbid")


class EndpointConfig(BaseModel, Generic[RequestT, ResponseT]):
    """Configuration for a type-safe API endpoint.

    This class encapsulates all the information needed to make a request to an endpoint
    while preserving full type information. The generic parameters ensure that the
    request and response types flow through to the client methods.

    Parameters
    ----------
    RequestT : type[BaseModel]
        The type of the request data model.
    ResponseT : type[BaseModel]
        The type of the response data model.

    Attributes
    ----------
    path : str
        The URL path for the endpoint (relative to base_url).
    request_type : type[RequestT]
        The Pydantic model class for request validation.
    response_type : type[ResponseT]
        The Pydantic model class for response validation.
    method : HTTPMethod
        The HTTP method to use for this endpoint (default: "POST").

    Examples
    --------
    >>> from pydantic import BaseModel
    >>> class GenerationRequest(BaseModel):
    ...     prompt: str
    ...     max_tokens: int
    >>> class GenerationResponse(BaseModel):
    ...     text: str
    ...     tokens_used: int
    >>>
    >>> # Standard endpoint definition
    >>> GENERATION_ENDPOINT = EndpointConfig[GenerationRequest, GenerationResponse](
    ...     path="/api/v1/generation",
    ...     method="POST",
    ...     request_type=GenerationRequest,
    ...     response_type=GenerationResponse,
    ... )

    Notes
    -----
    The configuration is frozen (immutable) to prevent accidental modification
    after initialization.
    """

    model_config = ConfigDict(frozen=True)

    path: str
    request_type: type[RequestT]
    response_type: type[ResponseT]
    method: HTTPMethod = "POST"
