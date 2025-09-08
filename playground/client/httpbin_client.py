from __future__ import annotations

from collections.abc import AsyncIterable
from pathlib import Path
from typing import Any

import httpx

from clientry import BaseClient, EmptyRequest
from playground.client.endpoints import HTTPBinEndpoints
from playground.client.models import (
    DelayResponse,
    HTTPBinResponse,
    JSONRequest,
    StatusResponse,
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
        self.endpoints = HTTPBinEndpoints()

    async def echo_json(
        self,
        data: dict[str, Any],
        max_retry_attempts: int | None = None,
    ) -> HTTPBinResponse:
        request = JSONRequest(data=data)
        return await self._arequest(
            self.endpoints.POST_JSON,
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
            self.endpoints.UPLOAD,
            files=files,
            data=data if data else None,
        )

    async def upload_multiple_files(
        self,
        files_data: dict[str, tuple[str, bytes, str]],
    ) -> HTTPBinResponse:
        return await self._arequest(self.endpoints.UPLOAD, files=files_data)

    async def send_stream(
        self,
        content: bytes | str | AsyncIterable[bytes],
    ) -> HTTPBinResponse:
        return await self._arequest(
            self.endpoints.POST_JSON,
            content=content,
        )

    async def test_status(
        self,
        status_code: int,
        max_retry_attempts: int | None = None,
    ) -> StatusResponse | None:
        endpoint = self.endpoints.STATUS.model_copy(update={"path": f"/status/{status_code}"})
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
        endpoint = self.endpoints.DELAY.model_copy(update={"path": f"/delay/{seconds}"})
        return await self._arequest(
            endpoint,
            EmptyRequest(),
            max_retry_attempts=max_retry_attempts,
        )

    async def get_request(self, params: dict[str, Any] | None = None) -> HTTPBinResponse:
        return await self._arequest(self.endpoints.GET, EmptyRequest(), params=params)

    async def put_json(self, data: dict[str, Any]) -> HTTPBinResponse:
        request = JSONRequest(data=data)
        return await self._arequest(self.endpoints.PUT_JSON, request)

    async def delete_request(self) -> HTTPBinResponse:
        return await self._arequest(self.endpoints.DELETE, EmptyRequest())

    async def test_headers(self, custom_headers: dict[str, str]) -> HTTPBinResponse:
        return await self._arequest(
            self.endpoints.GET,
            EmptyRequest(),
            headers=custom_headers,
        )
