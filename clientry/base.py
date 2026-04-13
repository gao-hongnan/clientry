"""Generic Request Pattern implementation for type-safe API clients.

This module implements the Generic Request Pattern (also known as the Type-Safe Client
Pattern or Parametric API Pattern). This is NOT a classic Gang of Four design pattern,
but rather a modern pattern that emerged from the intersection of functional programming
and advanced type systems.

Pattern Overview
----------------
The Generic Request Pattern uses parametric polymorphism to create a single,
reusable request method that maintains full type safety across different API
endpoints. Instead of writing separate methods for each endpoint (leading to
massive code duplication), we define endpoints as data using EndpointConfig
with generic type parameters.

How It Works
------------
1. EndpointConfig[RequestT, ResponseT] carries type information as data
2. A single _request() method handles all endpoints generically

Notes
-----
-   If this is too simple, just copy OpenAI's base client LOL!
-   If ever we need raw response, we can make the Response class acts like Rust's Result<T, E> pattern or just add param to include raw response with overload.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Literal, Self, overload
from urllib.parse import urlparse

import httpx
from tenacious.retry import Retry, RetryCallState, RetryConfig

from clientry.errors import (
    ClientError,
    PermanentError,
    RetryableError,
)
from clientry.types import (
    EndpointConfig,
    FilesParam,
    Headers,
    RequestID,
    RequestT,
    ResponseT,
    StatusCode,
    StreamContent,
)

logger = logging.getLogger(__name__)


class BaseClient:
    """Base client for building type-safe API clients.

    This class implements the Generic Request Pattern, providing a reusable
    foundation for API clients with automatic retry logic, error handling,
    and full type safety.

    Parameters
    ----------
    base_url : str
        The base URL for all API requests.
    timeout : float, optional
        Default timeout in seconds for requests (default: 30.0).
    connect_timeout : float, optional
        Timeout in seconds for establishing connections (default: 5.0).
    max_keepalive_connections : int, optional
        Maximum number of keepalive connections (default: 5).
    max_connections : int, optional
        Maximum total number of connections (default: 10).
    default_headers : dict[str, str] | None, optional
        Default headers to include in all requests (default: None).
    max_retry_attempts : int, optional
        Maximum number of retry attempts (default: 3).
    retry_min_wait : float, optional
        Minimum wait time in seconds between retries (default: 1.0).
    retry_max_wait : float, optional
        Maximum wait time in seconds between retries (default: 10.0).
    retry_multiplier : float, optional
        Exponential backoff multiplier (default: 2.0).
    retry_on_status : frozenset[int] | None, optional
        HTTP status codes that trigger retries (default: {408, 429, 502, 503, 504}).
    success_status : frozenset[int] | None, optional
        HTTP status codes considered successful (default: {200, 201, 204}).
    permanent_error_status : frozenset[int] | None, optional
        HTTP status codes considered permanent errors (default: {400, 401, 403, 404, 405, 406, 409, 410, 422}).

    Attributes
    ----------
    base_url : str
        The base URL for API requests.
    _client : httpx.AsyncClient | None
        Lazy-initialized HTTP client instance.
    _is_closed : bool
        Flag indicating whether the client has been closed.

    Examples
    --------
    >>> class MyAPIClient(BaseClient):
    ...     ENDPOINT = EndpointConfig[RequestType, ResponseType](
    ...         path="/api/endpoint",
    ...         request_type=RequestType,
    ...         response_type=ResponseType,
    ...     )
    ...
    ...     async def call_api(self, request: RequestType) -> ResponseType:
    ...         return await self._arequest(self.ENDPOINT, request)
    ...
    ...     async def call_api_with_raw(
    ...         self, request: RequestType
    ...     ) -> tuple[ResponseType, httpx.Response]:
    ...         # Get both parsed response and raw httpx.Response
    ...         return await self._arequest(self.ENDPOINT, request, return_raw=True)
    >>>
    >>> async with MyAPIClient(base_url="https://api.example.com") as client:
    ...     # Get only the parsed response (default behavior)
    ...     result = await client.call_api(request)
    ...
    ...     # Get both parsed and raw response
    ...     parsed, raw = await client.call_api_with_raw(request)
    ...     print(parsed.data)  # Access parsed model
    ...     print(raw.headers['x-request-id'])  # Access raw headers
    ...     print(raw.status_code)  # Access status code

    Notes
    -----
    The client uses lazy initialization for the HTTP client to avoid
    creating resources until they're actually needed. Always use the
    client as an async context manager or explicitly call close().
    """

    def __init__(
        self,
        base_url: str,
        *,
        http_client: httpx.AsyncClient | None = None,
        http_client_kwargs: dict[str, Any] | None = None,
        timeout: float = 30.0,
        connect_timeout: float = 5.0,
        max_keepalive_connections: int = 5,
        max_connections: int = 10,
        default_headers: dict[str, str] | None = None,
        retry_config: RetryConfig | None = None,
        retry_on_status: frozenset[int] | None = None,
        success_status: frozenset[int] | None = None,
        permanent_error_status: frozenset[int] | None = None,
    ) -> None:
        """Initialize the base client.

        Parameters
        ----------
        base_url : str
            The base URL for all API requests.
        http_client : httpx.AsyncClient | None, optional
            Pre-configured httpx client to use. If provided, the client will not be
            closed when BaseClient is closed (default: None).
        http_client_kwargs : dict[str, Any] | None, optional
            Additional keyword arguments to pass to httpx.AsyncClient constructor.
            Examples: {"verify": False}, {"http2": True} (default: None).
        timeout : float, optional
            Default timeout in seconds for requests (default: 30.0).
        connect_timeout : float, optional
            Timeout in seconds for establishing connections (default: 5.0).
        max_keepalive_connections : int, optional
            Maximum number of keepalive connections (default: 5).
        max_connections : int, optional
            Maximum total number of connections (default: 10).
        default_headers : dict[str, str] | None, optional
            Default headers to include in all requests (default: None).
        retry_config : RetryConfig | None, optional
            Retry configuration (attempts, backoff, etc.). If None, uses
            defaults: 3 attempts, 1-10s exponential backoff with jitter.
        retry_on_status : frozenset[int] | None, optional
            HTTP status codes that trigger retries (default: {408, 429, 502, 503, 504}).
        success_status : frozenset[int] | None, optional
            HTTP status codes considered successful (default: {200, 201, 204}).
        permanent_error_status : frozenset[int] | None, optional
            HTTP status codes considered permanent errors (default: {400, 401, 403, 404, 405, 406, 409, 410, 422}).

        Raises
        ------
        ValueError
            If base_url is invalid or missing required components.
        """
        parsed = urlparse(base_url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"Invalid base_url: {base_url}. Must include scheme and netloc.")

        self.base_url = base_url
        self.timeout = timeout
        self.connect_timeout = connect_timeout
        self.max_keepalive_connections = max_keepalive_connections
        self.max_connections = max_connections
        self.default_headers = default_headers or {}
        self._retry_config = retry_config or RetryConfig(max_attempts=3, wait_min=1.0, wait_max=10.0, multiplier=2.0)
        self.retry_on_status = retry_on_status or frozenset({408, 429, 502, 503, 504})
        self.success_status = success_status or frozenset({200, 201, 204})
        self.permanent_error_status = permanent_error_status or frozenset({400, 401, 403, 404, 405, 406, 409, 410, 422})

        if http_client:
            self._client = http_client
            self._owns_client = False
        else:
            kwargs = http_client_kwargs or {}
            if "timeout" not in kwargs:
                kwargs["timeout"] = httpx.Timeout(timeout, connect=connect_timeout)

            self._client = httpx.AsyncClient(
                base_url=base_url,
                limits=httpx.Limits(
                    max_keepalive_connections=max_keepalive_connections,
                    max_connections=max_connections,
                ),
                **kwargs,
            )
            self._owns_client = True

    def _classify_error(
        self,
        status_code: StatusCode,
        response_text: str,
        request_id: RequestID = None,
    ) -> ClientError:
        """Classify an HTTP error as retryable or permanent.

        Uses pattern matching to determine the appropriate error type based on
        the HTTP status code.

        Parameters
        ----------
        status_code : int
            The HTTP status code from the response.
        response_text : str
            The raw response body text.
        request_id : str | None, optional
            Request ID from response headers if available (default: None).

        Returns
        -------
        ClientError
            An appropriate error subclass (RetryableError or PermanentError).

        Notes
        -----
        This method determines whether the client should retry the request
        with backoff or fail immediately. The classification follows industry
        best practices for API error handling.
        """
        match status_code:
            case code if code in self.retry_on_status:
                return RetryableError(
                    f"Retryable error: {status_code}",
                    status_code=status_code,
                    response_body=response_text,
                    request_id=request_id,
                )
            case code if code in self.permanent_error_status:
                return PermanentError(
                    f"Permanent error: {status_code}",
                    status_code=status_code,
                    response_body=response_text,
                    request_id=request_id,
                )
            case _:
                return ClientError(
                    f"Unexpected error: {status_code}",
                    status_code=status_code,
                    response_body=response_text,
                    request_id=request_id,
                )

    def _retryer(
        self,
        retry_config: RetryConfig | None = None,
        retry_on_status: frozenset[int] | None = None,
    ) -> Retry:
        """Build a :class:`tenacious.retry.Retry` decorator for one request.

        Parameters
        ----------
        retry_config : RetryConfig | None, optional
            Per-request override. Falls back to the instance default.
        retry_on_status : frozenset[int] | None, optional
            HTTP status codes that trigger retries (default: uses instance default).

        Returns
        -------
        Retry
            Configured retry decorator ready to wrap an async function.
        """
        config = retry_config or self._retry_config
        effective_status = retry_on_status or self.retry_on_status

        def should_retry(exc: BaseException) -> bool:
            if isinstance(exc, RetryableError):
                return True
            if isinstance(exc, ClientError) and exc.status_code is not None:
                return exc.status_code in effective_status
            return False

        def log_retry(retry_state: RetryCallState) -> None:
            if retry_state.attempt_number > 1:
                logger.warning(
                    "Retry %d/%d: %s",
                    retry_state.attempt_number,
                    config.max_attempts,
                    retry_state.outcome.exception() if retry_state.outcome else "Unknown error",
                )

        merged = config.model_copy(update={"retry_if": should_retry})
        return Retry(config=merged, before_sleep=log_retry)

    @overload
    async def _arequest(
        self,
        endpoint: EndpointConfig[RequestT, ResponseT],
        request_data: RequestT | None = None,
        *,
        return_raw: Literal[False] = False,
        files: FilesParam | None = None,
        content: StreamContent | None = None,
        headers: Headers | None = None,
        retry_config: RetryConfig | None = None,
        retry_on_status: frozenset[int] | None = None,
        **kwargs: Any,
    ) -> ResponseT: ...

    @overload
    async def _arequest(
        self,
        endpoint: EndpointConfig[RequestT, ResponseT],
        request_data: RequestT | None = None,
        *,
        return_raw: Literal[True],
        files: FilesParam | None = None,
        content: StreamContent | None = None,
        headers: Headers | None = None,
        retry_config: RetryConfig | None = None,
        retry_on_status: frozenset[int] | None = None,
        **kwargs: Any,
    ) -> tuple[ResponseT, httpx.Response]: ...

    async def _arequest(
        self,
        endpoint: EndpointConfig[RequestT, ResponseT],
        request_data: RequestT | None = None,
        *,
        return_raw: bool = False,
        files: FilesParam | None = None,
        content: StreamContent | None = None,
        headers: Headers | None = None,
        retry_config: RetryConfig | None = None,
        retry_on_status: frozenset[int] | None = None,
        **kwargs: Any,
    ) -> ResponseT | tuple[ResponseT, httpx.Response]:
        """Make a request to an endpoint with configurable retry and error handling.

        Parameters
        ----------
        endpoint : EndpointConfig[RequestT, ResponseT]
            Endpoint configuration containing path, method, and types.
        request_data : RequestT | None, optional
            Request data model for POST/PUT/PATCH methods (default: None).
        return_raw : bool, optional
            If True, returns tuple of (parsed_response, raw_httpx_response).
            If False, returns only the parsed response (default: False).
        files : Mapping[str, Any] | None, optional
            Files to upload as multipart/form-data (default: None).
        content : bytes | str | Iterable[bytes] | AsyncIterable[bytes] | None, optional
            Raw content for streaming or binary uploads (default: None).
        headers : Mapping[str, str] | None, optional
            Per-request headers to override/extend default headers (default: None).
        retry_config : RetryConfig | None, optional
            Per-request retry override (default: uses instance config).
        retry_on_status : frozenset[int] | None, optional
            Override retry status codes for this request (default: None).
        **kwargs : Any
            Additional request options passed to httpx.

        Returns
        -------
        ResponseT | tuple[ResponseT, httpx.Response]
            If return_raw=False: Deserialized and validated response object.
            If return_raw=True: Tuple of (parsed_response, raw_httpx_response).

        Raises
        ------
        RetryableError
            For transient failures (will be automatically retried based on config).
        PermanentError
            For non-retryable failures (e.g., authentication errors).
        ClientError
            For other errors (e.g., parsing failures).
        """
        retry_decorator = self._retryer(retry_config=retry_config, retry_on_status=retry_on_status)

        @retry_decorator
        async def _amake_request() -> ResponseT | tuple[ResponseT, httpx.Response]:
            """Inner function that performs the actual HTTP request."""
            method = endpoint.method.lower()

            request_kwargs: dict[str, Any] = kwargs.copy()

            if headers or self.default_headers:
                request_kwargs["headers"] = {**self.default_headers, **(headers or {})}

            # NOTE: precedence logic: files > content > json
            if files is not None:
                request_kwargs |= {"files": files}
                if request_data:
                    request_kwargs |= {"data": request_data.model_dump(mode="json")}
            elif content is not None:
                request_kwargs |= {"content": content}
            elif request_data is not None:
                request_kwargs |= {"json": request_data.model_dump(by_alias=True, exclude_none=True)}

            try:
                response = await self._client.request(method, endpoint.path, **request_kwargs)

                request_id = response.headers.get("x-request-id")

                match response.status_code:
                    case code if code in self.success_status:
                        try:
                            response_data = response.json()
                            parsed = endpoint.response_type.model_validate(response_data)

                            if return_raw:
                                return parsed, response
                            return parsed
                        except (json.JSONDecodeError, Exception) as e:
                            logger.error(f"Failed to parse response: {e}")
                            raise ClientError(
                                f"Invalid response format: {str(e)}",
                                response_body=response.text,
                                request_id=request_id,
                            ) from e
                    case _:
                        error = self._classify_error(
                            response.status_code,
                            response.text,
                            request_id,
                        )

                        match error:
                            case RetryableError():
                                logger.warning(f"Retryable error for {endpoint}: {response.status_code}")
                            case _:
                                logger.error(f"Permanent error for {endpoint}: {response.status_code}")

                        raise error

            # NOTE: `TimeoutException` & `NetworkError` are subclasses of `TransportError`
            except httpx.TransportError as e:
                logger.warning(f"Transport error for {endpoint}: {e}")
                raise RetryableError(
                    f"Transport error for {endpoint}",
                    response_body=str(e),
                ) from e
            except httpx.HTTPError as e:
                logger.error(f"HTTP error for {endpoint}: {e}")
                raise ClientError(
                    f"HTTP error for {endpoint}: {str(e)}",
                    response_body=str(e),
                ) from e

        return await _amake_request()

    @overload
    async def _arequest_bytes(
        self,
        endpoint: EndpointConfig[RequestT, ResponseT],
        request_data: RequestT | None = None,
        *,
        return_raw: Literal[False] = False,
        files: FilesParam | None = None,
        content: StreamContent | None = None,
        headers: Headers | None = None,
        retry_config: RetryConfig | None = None,
        retry_on_status: frozenset[int] | None = None,
        **kwargs: Any,
    ) -> bytes: ...

    @overload
    async def _arequest_bytes(
        self,
        endpoint: EndpointConfig[RequestT, ResponseT],
        request_data: RequestT | None = None,
        *,
        return_raw: Literal[True],
        files: FilesParam | None = None,
        content: StreamContent | None = None,
        headers: Headers | None = None,
        retry_config: RetryConfig | None = None,
        retry_on_status: frozenset[int] | None = None,
        **kwargs: Any,
    ) -> tuple[bytes, httpx.Response]: ...

    async def _arequest_bytes(
        self,
        endpoint: EndpointConfig[RequestT, ResponseT],
        request_data: RequestT | None = None,
        *,
        return_raw: bool = False,
        files: FilesParam | None = None,
        content: StreamContent | None = None,
        headers: Headers | None = None,
        retry_config: RetryConfig | None = None,
        retry_on_status: frozenset[int] | None = None,
        **kwargs: Any,
    ) -> bytes | tuple[bytes, httpx.Response]:
        """Make a request and return raw response bytes instead of a parsed model.

        Parameters
        ----------
        endpoint : EndpointConfig[RequestT, ResponseT]
            Endpoint configuration. ``response_type`` is ignored.
        request_data : RequestT | None, optional
            Request data model for POST/PUT/PATCH methods (default: None).
        return_raw : bool, optional
            If True, returns tuple of (body_bytes, raw_httpx_response).
            If False, returns only the bytes (default: False).
        files : Mapping[str, Any] | None, optional
            Files to upload as multipart/form-data (default: None).
        content : bytes | str | Iterable[bytes] | AsyncIterable[bytes] | None, optional
            Raw content for streaming or binary uploads (default: None).
        headers : Mapping[str, str] | None, optional
            Per-request headers to override/extend default headers (default: None).
        retry_config : RetryConfig | None, optional
            Per-request retry override (default: uses instance config).
        retry_on_status : frozenset[int] | None, optional
            Override retry status codes for this request (default: None).
        **kwargs : Any
            Additional request options passed to httpx (e.g. ``params=``).

        Returns
        -------
        bytes | tuple[bytes, httpx.Response]
            If return_raw=False: the raw response body bytes.
            If return_raw=True: tuple of (body_bytes, raw_httpx_response).

        Raises
        ------
        RetryableError
            For transient failures (automatically retried based on config).
        PermanentError
            For non-retryable failures (e.g., authentication errors).
        ClientError
            For other errors (e.g., transport-level issues).
        """
        retry_decorator = self._retryer(retry_config=retry_config, retry_on_status=retry_on_status)

        @retry_decorator
        async def _amake_request() -> bytes | tuple[bytes, httpx.Response]:
            """Inner function that performs the actual HTTP request."""
            method = endpoint.method.lower()

            request_kwargs: dict[str, Any] = kwargs.copy()

            if headers or self.default_headers:
                request_kwargs["headers"] = {**self.default_headers, **(headers or {})}

            # NOTE: precedence logic: files > content > json
            if files is not None:
                request_kwargs |= {"files": files}
                if request_data:
                    request_kwargs |= {"data": request_data.model_dump(mode="json")}
            elif content is not None:
                request_kwargs |= {"content": content}
            elif request_data is not None:
                request_kwargs |= {"json": request_data.model_dump(by_alias=True, exclude_none=True)}

            try:
                response = await self._client.request(method, endpoint.path, **request_kwargs)

                request_id = response.headers.get("x-request-id")

                match response.status_code:
                    case code if code in self.success_status:
                        body = response.content
                        if return_raw:
                            return body, response
                        return body
                    case _:
                        error = self._classify_error(
                            response.status_code,
                            response.text,
                            request_id,
                        )

                        match error:
                            case RetryableError():
                                logger.warning(f"Retryable error for {endpoint}: {response.status_code}")
                            case _:
                                logger.error(f"Permanent error for {endpoint}: {response.status_code}")

                        raise error

            # NOTE: `TimeoutException` & `NetworkError` are subclasses of `TransportError`
            except httpx.TransportError as e:
                logger.warning(f"Transport error for {endpoint}: {e}")
                raise RetryableError(
                    f"Transport error for {endpoint}",
                    response_body=str(e),
                ) from e
            except httpx.HTTPError as e:
                logger.error(f"HTTP error for {endpoint}: {e}")
                raise ClientError(
                    f"HTTP error for {endpoint}: {str(e)}",
                    response_body=str(e),
                ) from e

        return await _amake_request()

    async def __aenter__(self) -> Self:
        """Async context manager entry.

        Returns
        -------
        Self
            The client instance for use in async with statements.

        Examples
        --------
        >>> async with MyAPIClient(config) as client:
        ...     response = await client.call_endpoint(request)
        """
        return self

    async def __aexit__(self, *args: object) -> None:
        """Async context manager exit.

        Parameters
        ----------
        *args : object
            Exception information (unused).

        Notes
        -----
        Ensures the HTTP client is properly closed when exiting the context.
        """
        await self.aclose()

    async def aclose(self) -> None:
        """Close the HTTP client and cleanup resources.

        This method should be called when the client is no longer needed.
        Only closes the client if it was created internally (not injected).

        Examples
        --------
        >>> client = MyAPIClient(config)
        >>> try:
        ...     response = await client.call_api(request)
        ... finally:
        ...     await client.aclose()
        """
        if self._owns_client and self._client:
            await self._client.aclose()
