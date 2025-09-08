from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import httpx

from clientry.errors import PermanentError, RetryableError
from playground.client.httpbin_client import HTTPBinClient


async def demo_json_requests(client: HTTPBinClient) -> None:
    print("\nJSON Request Demos")
    print("-" * 20)

    response = await client.echo_json({"message": "Hello, HTTPBin!", "count": 42})
    print(f"POST response: {response.json_data}")

    response = await client.put_json({"updated": True, "version": "2.0"})
    print(f"PUT response: {response.json_data}")

    response = await client.get_request({"page": 1, "limit": 10})
    print(f"GET with params: {response.args}")


async def demo_file_upload(client: HTTPBinClient) -> None:
    print("\nFile Upload Demo")
    print("-" * 20)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("This is a test file for HTTPBin upload demo.\n")
        f.write("It demonstrates the file upload capability.\n")
        temp_path = Path(f.name)

    try:
        response = await client.upload_file(
            temp_path,
            metadata={"description": "Test file", "timestamp": "2024-01-01"},
        )
        print(f"File uploaded: {temp_path.name}")
        print(f"Response files: {list(response.files.keys())}")
    finally:
        temp_path.unlink()


async def demo_streaming(client: HTTPBinClient) -> None:
    print("\nStreaming Demo")
    print("-" * 20)

    async def generate_chunks():
        for i in range(3):
            yield f"Chunk {i}\n".encode()
            await asyncio.sleep(0.1)

    response = await client.send_stream(generate_chunks())
    print(f"Stream processed: {response.url}")


async def demo_error_handling(client: HTTPBinClient) -> None:
    print("\nError Handling Demo")
    print("-" * 20)

    try:
        await client.test_status(404, max_retry_attempts=1)
    except PermanentError as e:
        print(f"Caught 404 error: {e.status_code}")

    try:
        await client.test_status(503, max_retry_attempts=2)
    except RetryableError:
        print("Caught 503 error after retries")


async def demo_custom_client() -> None:
    print("\nCustom Client Configuration")
    print("-" * 20)

    custom_http_client = httpx.AsyncClient(
        base_url="https://httpbin.org",
        headers={"User-Agent": "Clientry-Demo/1.0"},
        follow_redirects=True,
    )

    async with HTTPBinClient(
        base_url="https://httpbin.org",
        http_client=custom_http_client,
        timeout=10.0,
        max_retry_attempts=5,
    ) as client:
        response = await client.test_headers({"X-Custom-Header": "CustomValue"})
        headers = response.headers
        print(f"Custom User-Agent: {headers.get('User-Agent')}")
        print(f"Custom Header: {headers.get('X-Custom-Header')}")


async def main() -> None:
    print("HTTPBin Client Demo")
    print("=" * 40)

    async with HTTPBinClient(timeout=30.0) as client:
        await demo_json_requests(client)
        await demo_file_upload(client)
        await demo_streaming(client)
        await demo_error_handling(client)

    await demo_custom_client()

    print("\nDemo completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())
