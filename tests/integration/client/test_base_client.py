from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import pytest_asyncio

from clientry import PermanentError, RetryableError, RetryConfig
from tests.fixtures.httpbin_client import HTTPBinClient
from tests.fixtures.httpbin_models import HTTPBinResponse


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[HTTPBinClient]:
    async with HTTPBinClient(timeout=10.0) as client:
        yield client


@pytest.mark.asyncio
async def test_generic_request_pattern_type_safety(client: HTTPBinClient) -> None:
    test_data = {"test": "data", "number": 42}
    response = await client.echo_json(test_data)

    assert isinstance(response, HTTPBinResponse)
    assert response.json_data == {"data": test_data}
    assert response.url == "https://httpbin.org/post"


@pytest.mark.asyncio
async def test_retry_configuration_precedence() -> None:
    client = HTTPBinClient(
        timeout=5.0,
        retry_config=RetryConfig(max_attempts=3, wait_min=0.1, wait_max=0.5),
    )

    mock_http_client = AsyncMock()
    mock_response = MagicMock()
    mock_response.status_code = 503
    mock_response.text = "Service Unavailable"
    mock_response.headers = {}

    mock_http_client.request.return_value = mock_response

    call_count = 0

    async def mock_request(*_args: Any, **_kwargs: Any) -> MagicMock:
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            return mock_response
        else:
            success_response = MagicMock()
            success_response.status_code = 200
            success_response.json = lambda: {"json": {"success": True}, "data": ""}
            success_response.headers = {}
            success_response.text = '{"json": {"success": true}, "data": ""}'
            return success_response

    mock_http_client.request.side_effect = mock_request

    with patch.object(client, "_client", mock_http_client):
        response = await client.echo_json({"test": "retry"})
        assert response.json_data == {"success": True}
        assert call_count == 3

    mock_http_client.reset_mock()
    mock_http_client.request.side_effect = [mock_response] * 5

    with patch.object(client, "_client", mock_http_client):
        with pytest.raises(RetryableError) as exc_info:
            await client.echo_json({"test": "no-retry"}, retry_config=RetryConfig(max_attempts=1))
        assert exc_info.value.status_code == 503
        assert mock_http_client.request.call_count == 1

    await client.aclose()


@pytest.mark.asyncio
async def test_error_classification(client: HTTPBinClient) -> None:
    with pytest.raises(PermanentError) as exc_info_perm:
        await client.test_status(404, retry_config=RetryConfig(max_attempts=1))
    assert exc_info_perm.value.status_code == 404
    assert "Permanent error: 404" in str(exc_info_perm.value)

    with pytest.raises(RetryableError) as exc_info_retry:
        await client.test_status(503, retry_config=RetryConfig(max_attempts=1))
    assert exc_info_retry.value.status_code == 503
    assert "Retryable error: 503" in str(exc_info_retry.value)


@pytest.mark.asyncio
async def test_return_raw_response(client: HTTPBinClient) -> None:
    """Test that return_raw parameter works correctly."""
    test_data = {"test": "data", "number": 42}

    # Test default behavior (return_raw=False)
    response = await client.echo_json(test_data)
    assert isinstance(response, HTTPBinResponse)
    assert response.json_data == {"data": test_data}

    # Test return_raw=True - returns tuple
    from clientry import EmptyRequest, EndpointConfig

    endpoint = EndpointConfig[EmptyRequest, HTTPBinResponse](
        path="/get",
        method="GET",
        request_type=EmptyRequest,
        response_type=HTTPBinResponse,
    )

    # Call with return_raw=True
    parsed, raw = await client._arequest(endpoint, EmptyRequest(), return_raw=True)

    # Verify both parts of the tuple
    assert isinstance(parsed, HTTPBinResponse)
    assert isinstance(raw, httpx.Response)
    assert raw.status_code == 200
    assert "x-amzn-trace-id" in raw.headers or "date" in raw.headers  # Common headers

    # Verify that the parsed response matches what we'd get from raw
    assert parsed.url == "https://httpbin.org/get"


@pytest.mark.asyncio
async def test_context_manager_lifecycle() -> None:
    async with HTTPBinClient(timeout=5.0) as client:
        assert client._client is not None
        response = await client.echo_json({"test": "data"})
        assert isinstance(response, HTTPBinResponse)

    client2 = HTTPBinClient(timeout=5.0)
    await client2.__aenter__()
    response = await client2.echo_json({"test": "data"})
    assert isinstance(response, HTTPBinResponse)
    await client2.__aexit__(None, None, None)


@pytest.mark.asyncio
async def test_arequest_bytes_returns_binary_body(client: HTTPBinClient) -> None:
    """Binary endpoints (image/png) must return raw bytes, not JSON-parsed."""
    body = await client.get_image_png()

    assert isinstance(body, bytes)
    assert body.startswith(b"\x89PNG\r\n\x1a\n"), "expected PNG magic bytes"
    assert len(body) > 0


@pytest.mark.asyncio
async def test_arequest_bytes_exact_length(client: HTTPBinClient) -> None:
    """Bytes endpoint should return exactly the requested number of bytes."""
    body = await client.get_random_bytes(1024)

    assert isinstance(body, bytes)
    assert len(body) == 1024


@pytest.mark.asyncio
async def test_arequest_bytes_return_raw(client: HTTPBinClient) -> None:
    """return_raw=True should surface both bytes and the raw httpx.Response."""
    from clientry import EmptyRequest, EndpointConfig

    endpoint = EndpointConfig[EmptyRequest, EmptyRequest](
        path="/image/png",
        method="GET",
        request_type=EmptyRequest,
        response_type=EmptyRequest,
    )

    body, raw = await client._arequest_bytes(endpoint, EmptyRequest(), return_raw=True)

    assert isinstance(body, bytes)
    assert isinstance(raw, httpx.Response)
    assert raw.status_code == 200
    assert raw.headers.get("content-type") == "image/png"
    assert body == raw.content


@pytest.mark.asyncio
async def test_arequest_bytes_error_classification() -> None:
    """Errors on binary endpoints must classify like _arequest (permanent vs retryable)."""
    from clientry import EmptyRequest, EndpointConfig

    async with HTTPBinClient(timeout=10.0) as client:
        permanent_endpoint = EndpointConfig[EmptyRequest, EmptyRequest](
            path="/status/404",
            method="GET",
            request_type=EmptyRequest,
            response_type=EmptyRequest,
        )
        with pytest.raises(PermanentError) as perm_exc:
            await client._arequest_bytes(permanent_endpoint, EmptyRequest(), retry_config=RetryConfig(max_attempts=1))
        assert perm_exc.value.status_code == 404

        retry_endpoint = EndpointConfig[EmptyRequest, EmptyRequest](
            path="/status/503",
            method="GET",
            request_type=EmptyRequest,
            response_type=EmptyRequest,
        )
        with pytest.raises(RetryableError) as retry_exc:
            await client._arequest_bytes(retry_endpoint, EmptyRequest(), retry_config=RetryConfig(max_attempts=1))
        assert retry_exc.value.status_code == 503


@pytest.mark.asyncio
async def test_concurrent_requests(client: HTTPBinClient) -> None:
    tasks = [client.echo_json({"request_id": i}) for i in range(5)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    assert all(not isinstance(r, Exception) for r in results)
    assert all(isinstance(r, HTTPBinResponse) for r in results)

    for i, result in enumerate(results):
        assert isinstance(result, HTTPBinResponse)
        assert result.json_data == {"data": {"request_id": i}}


@pytest.mark.asyncio
async def test_injected_client_not_closed() -> None:
    """Test that injected clients are not closed by BaseClient."""
    import httpx

    custom_client = httpx.AsyncClient(base_url="https://httpbin.org")

    client = HTTPBinClient(http_client=custom_client)

    assert client._client is custom_client
    assert client._owns_client is False

    response = await client.echo_json({"test": "injected"})
    assert isinstance(response, HTTPBinResponse)

    await client.aclose()

    raw_response = await custom_client.get("/get")
    assert raw_response.status_code == 200

    await custom_client.aclose()


@pytest.mark.asyncio
async def test_http_client_kwargs() -> None:
    """Test that http_client_kwargs are passed to httpx.AsyncClient."""
    client = HTTPBinClient(
        http_client_kwargs={
            "follow_redirects": False,
            "timeout": httpx.Timeout(5.0),
        }
    )

    assert client._client is not None
    assert client._owns_client is True
    assert client._client.follow_redirects is False
    assert client._client.timeout.connect == 5.0

    response = await client.echo_json({"test": "kwargs"})
    assert isinstance(response, HTTPBinResponse)

    await client.aclose()
