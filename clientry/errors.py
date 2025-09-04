"""Error hierarchy for the generic client pattern."""

from __future__ import annotations

from clientry.types import RequestID, ResponseBody, StatusCode


class ClientError(Exception):
    """Base exception for all client-related errors.

    All client exceptions inherit from this class, making it easy to catch
    all client errors with a single except block when needed.

    Parameters
    ----------
    message : str
        Human-readable error message.
    status_code : int | None, optional
        HTTP status code if available (default: None).
    response_body : Any | None, optional
        Raw response body for debugging (default: None).
    request_id : str | None, optional
        Request ID for tracing and support (default: None).

    Attributes
    ----------
    status_code : int | None
        The HTTP status code associated with the error.
    response_body : Any | None
        The raw response body from the server.
    request_id : str | None
        Unique request identifier for debugging.

    Examples
    --------
    >>> try:
    ...     # API call that might fail
    ...     response = await client.call_api()
    ... except ClientError as e:
    ...     print(f"Error: {e}")
    ...     if e.request_id:
    ...         print(f"Request ID for support: {e.request_id}")
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: StatusCode | None = None,
        response_body: ResponseBody = None,
        request_id: RequestID = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body
        self.request_id = request_id

    def __str__(self) -> str:
        """Return string representation of the error.

        Returns
        -------
        str
            Formatted error message including status code and request ID if available.

        Examples
        --------
        >>> error = ClientError("API failure", status_code=500, request_id="abc-123")
        >>> str(error)
        'API failure | Status: 500 | Request ID: abc-123'
        """
        parts = [super().__str__()]
        if self.status_code is not None:
            parts.append(f"Status: {self.status_code}")
        if self.request_id is not None:
            parts.append(f"Request ID: {self.request_id}")
        return " | ".join(parts)


class RetryableError(ClientError):
    """Errors that should trigger automatic retry with backoff.

    This exception indicates a transient failure that may succeed if retried.
    The client framework will automatically retry these errors using exponential
    backoff with jitter.

    Covered Status Codes
    --------------------
    - 408: Request Timeout
    - 429: Too Many Requests (rate limiting)
    - 502: Bad Gateway
    - 503: Service Unavailable
    - 504: Gateway Timeout

    Also Covers
    -----------
    - Network errors (connection failures, DNS resolution)
    - Timeout errors (read/write timeouts)
    - Temporary server issues

    Examples
    --------
    >>> # This error will be automatically retried
    >>> raise RetryableError(
    ...     "Service temporarily unavailable",
    ...     status_code=503,
    ...     request_id="xyz-789"
    ... )

    Notes
    -----
    The retry behavior is configured in the BaseClient._request method
    using the tenacity library with exponential backoff.
    """

    pass


class PermanentError(ClientError):
    """Errors that should not be retried.

    This exception indicates a permanent failure that will not succeed even if
    retried. The client should handle these errors appropriately, such as by
    prompting for new credentials or fixing request parameters.

    Covered Status Codes
    --------------------
    - 400: Bad Request
    - 401: Unauthorized (authentication required)
    - 403: Forbidden (insufficient permissions)
    - 404: Not Found
    - 405: Method Not Allowed
    - 406: Not Acceptable
    - 409: Conflict
    - 410: Gone
    - 422: Unprocessable Entity (validation error)

    Examples
    --------
    >>> # This error will not be retried
    >>> raise PermanentError(
    ...     "Invalid API key",
    ...     status_code=401,
    ...     response_body={"error": "Invalid authentication credentials"}
    ... )

    Notes
    -----
    These errors typically require user intervention to resolve, such as
    updating authentication credentials or fixing request parameters.
    """

    pass
