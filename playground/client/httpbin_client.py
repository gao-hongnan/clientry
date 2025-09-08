from __future__ import annotations

from collections.abc import AsyncIterable
from pathlib import Path
from typing import Any

import httpx

from clientry import BaseClient, EmptyRequest, EndpointConfig
from playground.client.models import (
    DelayResponse,
    HTTPBinResponse,
    JSONRequest,
    StatusResponse,
    StreamResponse,
    UploadRequest,
)


class HTTPBinClient(BaseClient):
    def __init__(
        self,
        base_url: str = "https://httpbin.org",
        *,
        http_client: httpx.AsyncClient | None = None,
        http_client_kwargs: dict[str, Any] | None = None,
        timeout: float = 30.0,
        max_retry_attempts: int = 3,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            base_url,
            http_client=http_client,
            http_client_kwargs=http_client_kwargs,
            timeout=timeout,
            max_retry_attempts=max_retry_attempts,
            **kwargs,
        )

    JSON_POST_ENDPOINT = EndpointConfig[JSONRequest, HTTPBinResponse](
        path="/post",
        method="POST",
        request_type=JSONRequest,
        response_type=HTTPBinResponse,
    )

    GET_ENDPOINT = EndpointConfig[EmptyRequest, HTTPBinResponse](
        path="/get",
        method="GET",
        request_type=EmptyRequest,
        response_type=HTTPBinResponse,
    )

    PUT_ENDPOINT = EndpointConfig[JSONRequest, HTTPBinResponse](
        path="/put",
        method="PUT",
        request_type=JSONRequest,
        response_type=HTTPBinResponse,
    )

    DELETE_ENDPOINT = EndpointConfig[EmptyRequest, HTTPBinResponse](
        path="/delete",
        method="DELETE",
        request_type=EmptyRequest,
        response_type=HTTPBinResponse,
    )

    UPLOAD_ENDPOINT = EndpointConfig[UploadRequest, HTTPBinResponse](
        path="/post",
        method="POST",
        request_type=UploadRequest,
        response_type=HTTPBinResponse,
    )

    DELAY_ENDPOINT = EndpointConfig[EmptyRequest, DelayResponse](
        path="/delay/{seconds}",
        method="GET",
        request_type=EmptyRequest,
        response_type=DelayResponse,
    )

    STATUS_ENDPOINT = EndpointConfig[EmptyRequest, StatusResponse](
        path="/status/{code}",
        method="GET",
        request_type=EmptyRequest,
        response_type=StatusResponse,
    )

    STREAM_ENDPOINT = EndpointConfig[EmptyRequest, StreamResponse](
        path="/stream/{n}",
        method="GET",
        request_type=EmptyRequest,
        response_type=StreamResponse,
    )

    async def echo_json(
        self,
        data: dict[str, Any],
        max_retry_attempts: int | None = None,
    ) -> HTTPBinResponse:
        request = JSONRequest(data=data)
        return await self._arequest(
            self.JSON_POST_ENDPOINT,
            request,
            max_retry_attempts=max_retry_attempts,
        )

    async def upload_file(
        self,
        file_path: Path,
        metadata: dict[str, Any] | None = None,
    ) -> HTTPBinResponse:
        with open(file_path, "rb") as f:
            files = {
                "file": (file_path.name, f.read(), "application/octet-stream"),
            }

        data = {}
        if metadata:
            for key, value in metadata.items():
                data[key] = str(value)

        return await self._arequest(
            self.UPLOAD_ENDPOINT,
            files=files,
            data=data if data else None,
        )

    async def upload_multiple_files(
        self,
        files_data: dict[str, tuple[str, bytes, str]],
    ) -> HTTPBinResponse:
        return await self._arequest(self.UPLOAD_ENDPOINT, files=files_data)

    async def send_stream(
        self,
        content: bytes | str | AsyncIterable[bytes],
    ) -> HTTPBinResponse:
        return await self._arequest(
            self.JSON_POST_ENDPOINT,
            content=content,
        )

    async def test_status(
        self,
        status_code: int,
        max_retry_attempts: int | None = None,
    ) -> StatusResponse | None:
        endpoint = self.STATUS_ENDPOINT.model_copy(update={"path": f"/status/{status_code}"})
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
        endpoint = self.DELAY_ENDPOINT.model_copy(update={"path": f"/delay/{seconds}"})
        return await self._arequest(
            endpoint,
            EmptyRequest(),
            max_retry_attempts=max_retry_attempts,
        )

    async def get_request(self, params: dict[str, Any] | None = None) -> HTTPBinResponse:
        return await self._arequest(self.GET_ENDPOINT, EmptyRequest(), params=params)

    async def put_json(self, data: dict[str, Any]) -> HTTPBinResponse:
        request = JSONRequest(data=data)
        return await self._arequest(self.PUT_ENDPOINT, request)

    async def delete_request(self) -> HTTPBinResponse:
        return await self._arequest(self.DELETE_ENDPOINT, EmptyRequest())

    async def test_headers(self, custom_headers: dict[str, str]) -> HTTPBinResponse:
        return await self._arequest(
            self.GET_ENDPOINT,
            EmptyRequest(),
            headers=custom_headers,
        )
