"""Test fixture models for HTTPBin API testing."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class JSONRequest(BaseModel):
    """Request model for JSON data endpoints."""

    model_config = ConfigDict(extra="allow")

    data: dict[str, Any] = Field(default_factory=dict)
    headers: dict[str, str] | None = None


class UploadRequest(BaseModel):
    """Request model for file upload endpoints."""

    model_config = ConfigDict(extra="allow")

    description: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class HTTPBinResponse(BaseModel):
    """Base response model for HTTPBin endpoints."""

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
    """Response model for streaming endpoints."""

    model_config = ConfigDict(extra="allow")

    id: int
    data: str


class DelayResponse(BaseModel):
    """Response model for delay endpoint."""

    model_config = ConfigDict(extra="allow")

    args: dict[str, Any] = Field(default_factory=dict)
    data: str = ""
    files: dict[str, Any] = Field(default_factory=dict)
    form: dict[str, Any] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    origin: str | None = None
    url: str | None = None


class StatusResponse(BaseModel):
    """Response model for status code testing."""

    model_config = ConfigDict(extra="allow")

    code: int | None = None
    message: str | None = None
