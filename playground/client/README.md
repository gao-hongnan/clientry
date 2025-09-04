# HTTPBin Client Example

This example demonstrates the **Generic Request Pattern** implementation using
the `clientry` module with HTTPBin.org as the target API.

## Overview

The HTTPBin client showcases all features of the refactored `@fatum/client`
module:

-   🎯 **Type-safe API calls** with Pydantic models
-   📁 **File uploads** with multipart/form-data
-   🌊 **Streaming content** support (bytes, strings, async iterables)
-   🔄 **Automatic retry logic** with exponential backoff
-   ⚠️ **Error classification** (permanent vs retryable)
-   🚀 **Concurrent requests** with asyncio
-   📋 **Custom headers** and configuration

## Architecture

### Generic Request Pattern

The client uses a modern pattern that emerged from functional programming and
advanced type systems:

```python
class HTTPBinClient(BaseClient[HTTPBinConfig]):
    # Endpoint defined as data with type parameters
    JSON_ENDPOINT = EndpointConfig[JSONRequest, HTTPBinResponse](
        path="/post",
        method="POST",
        request_type=JSONRequest,
        response_type=HTTPBinResponse,
    )

    # Single generic _arequest method handles all endpoints
    async def echo_json(self, data: dict) -> HTTPBinResponse:
        return await self._arequest(self.JSON_ENDPOINT, JSONRequest(data=data))
```

**Key Benefits:**

-   **No code duplication** - one `_arequest()` method for all endpoints
-   **Full type safety** - request/response types flow through generics
-   **Data-driven** - endpoints defined as configuration, not code
-   **Extensible** - add new endpoints without new methods

## Installation

```bash
# Install dependencies
uv add httpx tenacity pydantic rich pytest pytest-asyncio

# Or with pip
pip install httpx tenacity pydantic rich pytest pytest-asyncio
```

## Usage

### Basic Example

```python
import asyncio
from playground.client import HTTPBinClient, HTTPBinConfig

async def main():
    config = HTTPBinConfig()

    async with HTTPBinClient(config) as client:
        # JSON request
        response = await client.echo_json({"hello": "world"})
        print(f"Response: {response.json}")

        # File upload
        from pathlib import Path
        file = Path("test.txt")
        file.write_text("Test content")
        response = await client.upload_file(file, {"version": "1.0"})
        print(f"Uploaded: {response.files}")

asyncio.run(main())
```

### File Upload Features

The refactored client supports three content modes with precedence: **files >
content > json**

```python
# 1. File upload (multipart/form-data)
files = {"file": ("test.txt", b"content", "text/plain")}
await client._arequest(endpoint, files=files)

# 2. Streaming content
async def stream():
    for chunk in data:
        yield chunk
await client._arequest(endpoint, content=stream())

# 3. JSON data (default)
await client._arequest(endpoint, request_data=model)
```

### Error Handling

The client automatically classifies and handles errors:

```python
try:
    await client.test_status(404)  # Permanent error
except PermanentError as e:
    print(f"Not found: {e.status_code}")  # No retry

try:
    await client.test_status(503)  # Retryable error
except RetryableError as e:
    print(f"Service unavailable: {e.status_code}")  # Auto-retried 3x
```

**Error Classification:**

-   **Retryable** (408, 429, 502, 503, 504): Automatic retry with exponential
    backoff
-   **Permanent** (400, 401, 403, 404, etc.): Fail immediately
-   **Network/Timeout**: Treated as retryable

## Running the Demo

```bash
# Run interactive demo
python playground/client/demo.py

# Run tests
pytest playground/client/test_client.py -v

# Run with asyncio debug mode
PYTHONASYNCIODEBUG=1 python playground/client/demo.py
```

## Demo Output

```
🧪 HTTPBin Client Demo
──────────────────────

📤 JSON Request Demo
────────────────────
Sending POST request with JSON data...
✅ Response received: {'message': 'Hello, HTTPBin!', 'count': 42}

📁 File Upload Demo
───────────────────
Uploading file: test.txt
✅ File uploaded successfully!
   Files received: ['file']
   Metadata: {"author": "demo", "version": "1.0"}

🌊 Streaming Demo
─────────────────
Sending streaming content...
✅ String stream sent, received 56 bytes

⚠️ Error Handling Demo
──────────────────────
Testing 404 (permanent error, no retry)...
❌ Expected permanent error: 404

Testing 503 (retryable error)...
⚠️ Retryable error after max attempts: 503

🔄 Concurrent Requests Demo
───────────────────────────
✅ Completed 5/5 requests successfully

┏━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━┓
┃ Request ID ┃ Status    ┃ Data         ┃
┡━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━┩
│ 0          │ ✅ Success │ 0            │
│ 1          │ ✅ Success │ 1            │
│ 2          │ ✅ Success │ 2            │
│ 3          │ ✅ Success │ 3            │
│ 4          │ ✅ Success │ 4            │
└────────────┴───────────┴──────────────┘
```

## HTTPBin Endpoints Used

| Endpoint         | Method | Purpose                         |
| ---------------- | ------ | ------------------------------- |
| `/post`          | POST   | Echo JSON data and file uploads |
| `/get`           | GET    | Echo query parameters           |
| `/put`           | PUT    | Echo PUT data                   |
| `/delete`        | DELETE | Test DELETE method              |
| `/status/{code}` | GET    | Return specific HTTP status     |
| `/delay/{n}`     | GET    | Delay response by n seconds     |
| `/stream/{n}`    | GET    | Stream n JSON responses         |

## Testing

The test suite covers:

-   ✅ JSON request/response handling
-   ✅ Single and multiple file uploads
-   ✅ Streaming content (bytes, strings, async generators)
-   ✅ Error classification and retry logic
-   ✅ Custom headers
-   ✅ All HTTP methods (GET, POST, PUT, DELETE)
-   ✅ Concurrent request execution
-   ✅ Context manager lifecycle
-   ✅ File/content/JSON precedence

Run tests:

```bash
pytest playground/client/test_client.py -v --tb=short
```

## Key Takeaways

1. **Generic Request Pattern** eliminates code duplication
2. **Type parameters** flow through for compile-time safety
3. **Precedence logic** handles files > content > json automatically
4. **Error classification** enables smart retry strategies
5. **Async context managers** ensure proper resource cleanup
6. **HTTPBin.org** is perfect for testing HTTP client features

## References

-   [HTTPBin.org](https://httpbin.org) - HTTP Request & Response Service
-   [clientry](../../fatum/client/) - Base client implementation
-   [Generic Request Pattern](../../fatum/client/base.py) - Pattern
    documentation
