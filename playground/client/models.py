from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class JSONRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    data: dict[str, Any] = Field(default_factory=dict)
    headers: dict[str, str] | None = None


class UploadRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    description: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class HTTPBinResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    args: dict[str, Any] = Field(default_factory=dict)
    data: str = ""
    files: dict[str, Any] = Field(default_factory=dict)
    form: dict[str, Any] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    json_data: Any = Field(default=None, alias="json")
    method: str | None = None
    origin: str | None = None
    url: str | None = None


class StreamResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    data: str


class DelayResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    args: dict[str, Any] = Field(default_factory=dict)
    data: str = ""
    files: dict[str, Any] = Field(default_factory=dict)
    form: dict[str, Any] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    origin: str | None = None
    url: str | None = None


class StatusResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    code: int | None = None
    message: str | None = None
