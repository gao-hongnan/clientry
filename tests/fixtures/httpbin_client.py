"""Test fixture HTTPBin API client for testing clientry base."""

from __future__ import annotations

from collections.abc import AsyncIterable
from pathlib import Path
from typing import Any

import httpx

from clientry import BaseClient, EmptyRequest, EndpointConfig
from tests.fixtures.httpbin_models import (
    DelayResponse,
    HTTPBinResponse,
    JSONRequest,
    StatusResponse,
)


class HTTPBinClient(BaseClient):
    """HTTPBin API client demonstrating all clientry features.

    This client showcases:
    - File uploads with multipart/form-data
    - Streaming content
    - JSON requests
    - Error handling and retry logic
    - All HTTP methods
    """

    def __init__(
        self,
        base_url: str = "https://httpbin.org",
        *,
        http_client: httpx.AsyncClient | None = None,
        http_client_kwargs: dict[str, Any] | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        **kwargs: Any,
    ) -> None:
        """Initialize HTTPBin client with configuration and base URL.

        Parameters
        ----------
        base_url : str
            Base URL for HTTPBin API (default: https://httpbin.org).
        http_client : httpx.AsyncClient | None, optional
            Pre-configured httpx client to use (default: None).
        http_client_kwargs : dict[str, Any] | None, optional
            Additional kwargs for httpx.AsyncClient (default: None).
        timeout : float
            Request timeout in seconds (default: 30.0).
        max_retries : int
            Maximum retry attempts (default: 3).
        **kwargs : Any
            Additional parameters passed to BaseClient.
        """
        if "max_retries" in kwargs:
            kwargs["max_retry_attempts"] = kwargs.pop("max_retries")

        super().__init__(
            base_url,
            http_client=http_client,
            http_client_kwargs=http_client_kwargs,
            timeout=timeout,
            max_retry_attempts=max_retries,
            **kwargs,
        )

    async def echo_json(
        self,
        data: dict[str, Any],
        max_retry_attempts: int | None = None,
    ) -> HTTPBinResponse:
        """Send JSON data and get echo response.

        Parameters
        ----------
        data : dict[str, Any]
            JSON data to send
        max_retry_attempts : int | None
            Override retry count for this request

        Returns
        -------
        HTTPBinResponse
            Echo response with request details
        """
        endpoint = EndpointConfig[JSONRequest, HTTPBinResponse](
            path="/post",
            method="POST",
            request_type=JSONRequest,
            response_type=HTTPBinResponse,
        )
        request = JSONRequest(data=data)
        return await self._arequest(
            endpoint,
            request,
            max_retry_attempts=max_retry_attempts,
        )

    async def upload_file(
        self,
        file_path: Path,
        metadata: dict[str, Any] | None = None,
    ) -> HTTPBinResponse:
        """Upload a file with optional metadata.

        Parameters
        ----------
        file_path : Path
            Path to file to upload
        metadata : dict[str, Any] | None
            Additional form fields to include

        Returns
        -------
        HTTPBinResponse
            Response with uploaded file details
        """
        endpoint = EndpointConfig[EmptyRequest, HTTPBinResponse](
            path="/post",
            method="POST",
            request_type=EmptyRequest,
            response_type=HTTPBinResponse,
        )

        with open(file_path, "rb") as f:
            files = {"file": (file_path.name, f.read())}

        data = {}
        if metadata:
            for key, value in metadata.items():
                data[key] = str(value)

        return await self._arequest(
            endpoint,
            EmptyRequest(),
            files=files,
            data=data if data else None,
        )

    async def upload_multiple_files(
        self,
        files_data: dict[str, tuple[str, bytes]],
    ) -> HTTPBinResponse:
        """Upload multiple files at once.

        Parameters
        ----------
        files_data : dict[str, tuple[str, bytes]]
            Dictionary mapping field names to (filename, content) tuples

        Returns
        -------
        HTTPBinResponse
            Response with all uploaded files
        """
        endpoint = EndpointConfig[EmptyRequest, HTTPBinResponse](
            path="/post",
            method="POST",
            request_type=EmptyRequest,
            response_type=HTTPBinResponse,
        )
        return await self._arequest(endpoint, EmptyRequest(), files=files_data)

    async def send_stream(
        self,
        content: bytes | str | AsyncIterable[bytes],
    ) -> HTTPBinResponse:
        """Send streaming content.

        Parameters
        ----------
        content : bytes | str | AsyncIterable[bytes]
            Content to stream

        Returns
        -------
        HTTPBinResponse
            Response after processing stream
        """
        endpoint = EndpointConfig[EmptyRequest, HTTPBinResponse](
            path="/post",
            method="POST",
            request_type=EmptyRequest,
            response_type=HTTPBinResponse,
        )
        return await self._arequest(endpoint, EmptyRequest(), content=content)

    async def test_status(
        self,
        status_code: int,
        max_retry_attempts: int | None = None,
    ) -> StatusResponse | None:
        """Test specific status code response.

        Parameters
        ----------
        status_code : int
            HTTP status code to trigger
        max_retry_attempts : int | None
            Override retry count for this request

        Returns
        -------
        StatusResponse | None
            Response if successful, None if error

        Raises
        ------
        PermanentError
            For 4xx errors
        RetryableError
            For 5xx errors (subject to retry config)
        """
        endpoint = EndpointConfig[EmptyRequest, StatusResponse](
            path=f"/status/{status_code}",
            method="GET",
            request_type=EmptyRequest,
            response_type=StatusResponse,
        )
        return await self._arequest(
            endpoint,
            EmptyRequest(),
            max_retry_attempts=max_retry_attempts,
        )

    async def test_delay(
        self,
        seconds: int,
        max_retry_attempts: int | None = None,
    ) -> DelayResponse:
        """Test delayed response.

        Parameters
        ----------
        seconds : int
            Number of seconds to delay
        max_retry_attempts : int | None
            Override retry count for this request

        Returns
        -------
        DelayResponse
            Response after delay
        """
        endpoint = EndpointConfig[EmptyRequest, DelayResponse](
            path=f"/delay/{seconds}",
            method="GET",
            request_type=EmptyRequest,
            response_type=DelayResponse,
        )
        return await self._arequest(
            endpoint,
            EmptyRequest(),
            max_retry_attempts=max_retry_attempts,
        )

    async def get_request(self, params: dict[str, Any] | None = None) -> HTTPBinResponse:
        """Make a GET request with query parameters.

        Parameters
        ----------
        params : dict[str, Any] | None
            Query parameters to include

        Returns
        -------
        HTTPBinResponse
            Response with request details
        """
        endpoint = EndpointConfig[EmptyRequest, HTTPBinResponse](
            path="/get",
            method="GET",
            request_type=EmptyRequest,
            response_type=HTTPBinResponse,
        )
        return await self._arequest(endpoint, EmptyRequest(), params=params)

    async def put_json(self, data: dict[str, Any]) -> HTTPBinResponse:
        """Make a PUT request with JSON data.

        Parameters
        ----------
        data : dict[str, Any]
            JSON data to send

        Returns
        -------
        HTTPBinResponse
            Response with request details
        """
        endpoint = EndpointConfig[JSONRequest, HTTPBinResponse](
            path="/put",
            method="PUT",
            request_type=JSONRequest,
            response_type=HTTPBinResponse,
        )
        request = JSONRequest(data=data)
        return await self._arequest(endpoint, request)

    async def delete_request(self) -> HTTPBinResponse:
        """Make a DELETE request.

        Returns
        -------
        HTTPBinResponse
            Response with request details
        """
        endpoint = EndpointConfig[EmptyRequest, HTTPBinResponse](
            path="/delete",
            method="DELETE",
            request_type=EmptyRequest,
            response_type=HTTPBinResponse,
        )
        return await self._arequest(endpoint, EmptyRequest())

    async def test_headers(self, custom_headers: dict[str, str]) -> HTTPBinResponse:
        """Test custom headers.

        Parameters
        ----------
        custom_headers : dict[str, str]
            Headers to send with request

        Returns
        -------
        HTTPBinResponse
            Response with headers echo
        """
        endpoint = EndpointConfig[EmptyRequest, HTTPBinResponse](
            path="/get",
            method="GET",
            request_type=EmptyRequest,
            response_type=HTTPBinResponse,
        )
        return await self._arequest(endpoint, EmptyRequest(), headers=custom_headers)
