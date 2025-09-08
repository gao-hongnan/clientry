from __future__ import annotations

from clientry import EmptyRequest, EndpointConfig
from playground.client.models import (
    DelayResponse,
    HTTPBinResponse,
    JSONRequest,
    StatusResponse,
    StreamResponse,
    UploadRequest,
)


class HTTPBinEndpoints:
    GET = EndpointConfig[EmptyRequest, HTTPBinResponse](
        path="/get",
        method="GET",
        request_type=EmptyRequest,
        response_type=HTTPBinResponse,
    )

    POST_JSON = EndpointConfig[JSONRequest, HTTPBinResponse](
        path="/post",
        method="POST",
        request_type=JSONRequest,
        response_type=HTTPBinResponse,
    )

    PUT_JSON = EndpointConfig[JSONRequest, HTTPBinResponse](
        path="/put",
        method="PUT",
        request_type=JSONRequest,
        response_type=HTTPBinResponse,
    )

    DELETE = EndpointConfig[EmptyRequest, HTTPBinResponse](
        path="/delete",
        method="DELETE",
        request_type=EmptyRequest,
        response_type=HTTPBinResponse,
    )

    UPLOAD = EndpointConfig[UploadRequest, HTTPBinResponse](
        path="/post",
        method="POST",
        request_type=UploadRequest,
        response_type=HTTPBinResponse,
    )

    DELAY = EndpointConfig[EmptyRequest, DelayResponse](
        path="/delay/{seconds}",
        method="GET",
        request_type=EmptyRequest,
        response_type=DelayResponse,
    )

    STATUS = EndpointConfig[EmptyRequest, StatusResponse](
        path="/status/{code}",
        method="GET",
        request_type=EmptyRequest,
        response_type=StatusResponse,
    )

    STREAM = EndpointConfig[EmptyRequest, StreamResponse](
        path="/stream/{n}",
        method="GET",
        request_type=EmptyRequest,
        response_type=StreamResponse,
    )
