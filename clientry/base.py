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
from typing import Any, Self
from urllib.parse import urlparse

import httpx
from tenacity import (
    AsyncRetrying,
    RetryCallState,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

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
    ...         return await self._request(self.ENDPOINT, request)
    >>>
    >>> async with MyAPIClient(base_url="https://api.example.com") as client:
    ...     result = await client.call_api(request)

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
        max_retry_attempts: int = 3,
        retry_min_wait: float = 1.0,
        retry_max_wait: float = 10.0,
        retry_multiplier: float = 2.0,
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
        self.max_retry_attempts = max_retry_attempts
        self.retry_min_wait = retry_min_wait
        self.retry_max_wait = retry_max_wait
        self.retry_multiplier = retry_multiplier
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
        max_attempts: int | None = None,
        min_wait: float | None = None,
        max_wait: float | None = None,
        multiplier: float | None = None,
        retry_on_status: frozenset[int] | None = None,
    ) -> AsyncRetrying:
        """Create a tenacity retry decorator with the given configuration.

        Parameters
        ----------
        max_attempts : int | None, optional
            Maximum number of retry attempts (default: uses instance default).
        min_wait : float | None, optional
            Minimum wait time in seconds between retries (default: uses instance default).
        max_wait : float | None, optional
            Maximum wait time in seconds between retries (default: uses instance default).
        multiplier : float | None, optional
            Exponential backoff multiplier (default: uses instance default).
        retry_on_status : frozenset[int] | None, optional
            HTTP status codes that trigger retries (default: uses instance default).

        Returns
        -------
        AsyncRetrying
            Configured AsyncRetrying instance. Returns a single-attempt instance
            when retries are disabled.

        Examples
        --------
        >>> retrying = self._retryer(max_attempts=5, max_wait=30.0)
        >>> async for attempt in retrying:
        ...     with attempt:
        ...         result = await self._make_request()
        """
        max_attempts = max_attempts if max_attempts is not None else self.max_retry_attempts
        min_wait = min_wait if min_wait is not None else self.retry_min_wait
        max_wait = max_wait if max_wait is not None else self.retry_max_wait
        multiplier = multiplier if multiplier is not None else self.retry_multiplier
        retry_on_status = retry_on_status if retry_on_status is not None else self.retry_on_status

        if max_attempts == 0:
            return AsyncRetrying(
                stop=stop_after_attempt(1),
                retry=retry_if_exception(lambda _: False),  # NOTE: Never retry
                reraise=True,
            )

        def should_retry_exception(exc: BaseException) -> bool:
            """Determine if an exception should trigger a retry."""
            if isinstance(exc, RetryableError):
                return True

            if isinstance(exc, ClientError) and exc.status_code is not None:
                return exc.status_code in retry_on_status

            return False

        def log_retry(retry_state: RetryCallState) -> None:
            """Log retry attempts."""
            if retry_state.attempt_number > 1:
                logger.warning(
                    f"Retry {retry_state.attempt_number}/{max_attempts}: "
                    f"{retry_state.outcome.exception() if retry_state.outcome else 'Unknown error'}"
                )

        return AsyncRetrying(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(
                multiplier=multiplier,
                min=min_wait,
                max=max_wait,
            ),
            retry=retry_if_exception(should_retry_exception),
            reraise=True,
            before_sleep=log_retry,
        )

    async def _arequest(
        self,
        endpoint: EndpointConfig[RequestT, ResponseT],
        request_data: RequestT | None = None,
        *,
        files: FilesParam | None = None,
        content: StreamContent | None = None,
        headers: Headers | None = None,
        max_retry_attempts: int | None = None,
        retry_min_wait: float | None = None,
        retry_max_wait: float | None = None,
        retry_multiplier: float | None = None,
        retry_on_status: frozenset[int] | None = None,
        **kwargs: Any,
    ) -> ResponseT:
        """Make a request to an endpoint with configurable retry and error handling.

        This is the core method that all API calls go through. It provides:
        request serialization, HTTP communication, error classification,
        configurable retry with exponential backoff, and response deserialization.

        Parameters
        ----------
        endpoint : EndpointConfig[RequestT, ResponseT]
            Endpoint configuration containing path, method, and types.
        request_data : RequestT | None, optional
            Request data model for POST/PUT/PATCH methods (default: None).
        files : Mapping[str, Any] | None, optional
            Files to upload as multipart/form-data (default: None).
        content : bytes | str | Iterable[bytes] | AsyncIterable[bytes] | None, optional
            Raw content for streaming or binary uploads (default: None).
        headers : Mapping[str, str] | None, optional
            Per-request headers to override/extend default headers (default: None).
        max_retry_attempts : int | None, optional
            Override maximum retry attempts for this request (default: None).
        retry_min_wait : float | None, optional
            Override minimum retry wait for this request (default: None).
        retry_max_wait : float | None, optional
            Override maximum retry wait for this request (default: None).
        retry_multiplier : float | None, optional
            Override retry multiplier for this request (default: None).
        retry_on_status : frozenset[int] | None, optional
            Override retry status codes for this request (default: None).
        **kwargs : Any
            Additional request options passed to httpx.

        Returns
        -------
        ResponseT
            Deserialized and validated response object.

        Raises
        ------
        RetryableError
            For transient failures (will be automatically retried based on config).
        PermanentError
            For non-retryable failures (e.g., authentication errors).
        ClientError
            For other errors (e.g., parsing failures).
        """
        retrying = self._retryer(
            max_attempts=max_retry_attempts,
            min_wait=retry_min_wait,
            max_wait=retry_max_wait,
            multiplier=retry_multiplier,
            retry_on_status=retry_on_status,
        )

        async def _amake_request() -> ResponseT:
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
                            return endpoint.response_type.model_validate(response_data)
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

        async for attempt in retrying:
            with attempt:
                return await _amake_request()
        raise RuntimeError("Retry decorator did not execute")

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
