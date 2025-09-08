from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import AsyncIterator

import httpx
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from clientry.errors import PermanentError, RetryableError
from playground.client.httpbin_client import HTTPBinClient

console = Console()


async def generate_stream_chunks() -> AsyncIterator[bytes]:
    for i in range(5):
        yield f"Chunk {i}: {'=' * 20}\n".encode()
        await asyncio.sleep(0.1)


async def demo_json_requests(client: HTTPBinClient) -> None:
    console.print("\n[bold cyan]📤 JSON Request Demo[/bold cyan]")
    console.print("─" * 40)

    console.print("Sending POST request with JSON data...")
    response = await client.echo_json({"message": "Hello, HTTPBin!", "count": 42})
    console.print(f"✅ Response received: {response.json_data}")

    console.print("\nSending PUT request...")
    response = await client.put_json({"updated": True, "version": "2.0"})
    console.print(f"✅ PUT response: {response.json_data}")

    console.print("\nSending GET request with query params...")
    response = await client.get_request({"page": 1, "limit": 10})
    console.print(f"✅ Query params echoed: {response.args}")


async def demo_file_upload(client: HTTPBinClient) -> None:
    console.print("\n[bold cyan]📁 File Upload Demo[/bold cyan]")
    console.print("─" * 40)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        test_file = Path(f.name)
        f.write("This is a test file for HTTPBin upload demo.\n")
        f.write("It demonstrates the file upload capability.\n")

    try:
        console.print(f"Uploading file: {test_file.name}")
        response = await client.upload_file(
            test_file,
            metadata={"author": "demo", "version": "1.0"},
        )
        console.print("✅ File uploaded successfully!")
        console.print(f"   Files received: {list(response.files.keys())}")
        console.print(f"   Metadata: {response.form}")

        console.print("\nUploading multiple files...")
        files_data = {
            "file1": ("test1.txt", b"Content of file 1", "text/plain"),
            "file2": ("test2.txt", b"Content of file 2", "text/plain"),
            "config": ("config.json", b'{"setting": "value"}', "application/json"),
        }
        response = await client.upload_multiple_files(files_data)
        console.print(f"✅ Multiple files uploaded: {list(response.files.keys())}")

    finally:
        test_file.unlink(missing_ok=True)


async def demo_streaming(client: HTTPBinClient) -> None:
    console.print("\n[bold cyan]🌊 Streaming Demo[/bold cyan]")
    console.print("─" * 40)

    console.print("Sending streaming content...")

    content = "This is streaming content that will be sent in one go."
    response = await client.send_stream(content)
    console.print(f"✅ String stream sent, received {len(response.data)} bytes")

    console.print("\nStreaming bytes content...")
    byte_content = b"Binary streaming content \x00\x01\x02"
    response = await client.send_stream(byte_content)
    console.print(f"✅ Byte stream sent, received {len(response.data)} bytes")

    console.print("\nStreaming async chunks...")
    try:
        async_content = generate_stream_chunks()
        response = await client.send_stream(async_content)
        console.print("✅ Async stream completed")
    except Exception as e:
        console.print(f"ℹ️ Streaming note: {e}")


async def demo_error_handling(client: HTTPBinClient) -> None:
    console.print("\n[bold cyan]⚠️ Error Handling Demo[/bold cyan]")
    console.print("─" * 40)

    console.print("Testing 404 (permanent error, no retry)...")
    try:
        await client.test_status(404)
    except PermanentError as e:
        console.print(f"❌ Expected permanent error: {e.status_code}")

    console.print("\nTesting 503 (retryable error with default retry)...")
    try:
        await client.test_status(503)
    except RetryableError as e:
        console.print(f"⚠️ Retryable error after default attempts: {e.status_code}")

    console.print("\nTesting 503 with retries disabled...")
    try:
        await client.test_status(503, max_retry_attempts=0)
    except RetryableError as e:
        console.print(f"⚡ Failed immediately (no retry): {e.status_code}")

    console.print("\nTesting 503 with aggressive retry (5 attempts)...")
    try:
        await client.test_status(503, max_retry_attempts=5)
    except RetryableError as e:
        console.print(f"⚠️ Failed after 5 attempts: {e.status_code}")

    console.print("\nTesting timeout handling (2 second delay)...")
    try:
        await client.test_delay(2)
        console.print("✅ Request completed without timeout")
    except Exception as e:
        console.print(f"⏱️ Timeout or error: {type(e).__name__}")


async def demo_concurrent_requests(client: HTTPBinClient) -> None:
    console.print("\n[bold cyan]🔄 Concurrent Requests Demo[/bold cyan]")
    console.print("─" * 40)

    tasks = [client.echo_json({"request_id": i, "data": f"Request {i}"}) for i in range(5)]

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Executing concurrent requests...", total=len(tasks))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        progress.update(task, completed=len(tasks))

    successful = sum(1 for r in results if not isinstance(r, Exception))
    console.print(f"✅ Completed {successful}/{len(tasks)} requests successfully")

    table = Table(title="Concurrent Request Results")
    table.add_column("Request ID", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Data Received")

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            table.add_row(str(i), "❌ Failed", str(result))
        else:
            request_id = "N/A"
            if hasattr(result, "json_data") and result.json_data:
                data = result.json_data
                if isinstance(data, dict) and "data" in data and isinstance(data["data"], dict):
                    request_id = str(data["data"].get("request_id", "N/A"))
            table.add_row(str(i), "✅ Success", request_id)

    console.print(table)


async def demo_retry_configuration(client: HTTPBinClient) -> None:
    console.print("\n[bold cyan]🔁 Retry Configuration Demo[/bold cyan]")
    console.print("─" * 40)

    console.print("1. Normal request with default retry config...")
    await client.echo_json({"test": "default retry"})
    console.print("   ✅ Success with default retry")

    console.print("\n2. Fast-fail request (retries disabled)...")
    try:
        await client.echo_json(
            {"test": "no retry"},
            max_retry_attempts=0,
        )
        console.print("   ✅ Success (no retry needed)")
    except Exception as e:
        console.print(f"   ❌ Failed immediately: {e}")

    console.print("\n3. Critical operation with aggressive retry...")
    await client.echo_json(
        {"test": "critical operation"},
        max_retry_attempts=5,
    )
    console.print("   ✅ Critical operation succeeded")
    console.print("   Config: 5 attempts, 0.5-30s wait, 1.5x backoff")

    console.print("\n4. Custom retry for rate limiting (429 only)...")
    try:
        await client.test_status(429, max_retry_attempts=3)
    except RetryableError:
        console.print("   ⚠️ Rate limited even after retries")

    console.print("\n5. Conservative retry for background tasks...")
    await client.echo_json(
        {"test": "background task"},
        max_retry_attempts=2,
    )
    console.print("   ✅ Background task completed")
    console.print("   Config: 2 attempts, 5-10s wait")

    console.print("\n6. Demonstrating retry config precedence...")
    console.print("   Per-request config overrides any defaults")
    await client.echo_json(
        {"test": "override"},
        max_retry_attempts=1,
    )
    console.print("   ✅ Used per-request retry config")


async def demo_custom_headers(client: HTTPBinClient) -> None:
    console.print("\n[bold cyan]📋 Custom Headers Demo[/bold cyan]")
    console.print("─" * 40)

    custom_headers = {
        "X-Custom-Header": "test-value",
        "X-Demo-Version": "1.0.0",
        "X-Request-ID": "demo-123",
    }

    console.print("Sending request with custom headers...")
    response = await client.test_headers(custom_headers)

    console.print("✅ Headers echoed back:")
    for key, value in response.headers.items():
        if key.startswith("X-"):
            console.print(f"   {key}: {value}")


async def demo_client_injection() -> None:
    console.print("\n[bold cyan]💉 Client Injection Demo[/bold cyan]")
    console.print("─" * 40)

    console.print("1. Injecting custom httpx client (verify=False)...")
    custom_client = httpx.AsyncClient(
        base_url="https://httpbin.org",
        verify=False,
        http2=True,
    )

    client_with_custom = HTTPBinClient(http_client=custom_client)
    console.print("   ✅ Using injected client with custom settings")

    response = await client_with_custom.echo_json({"test": "injected client"})
    console.print(f"   Response: {response.json_data}")

    await client_with_custom.aclose()
    console.print("   ℹ️ HTTPBinClient closed, but injected client still open")

    raw_response = await custom_client.get("/get")
    console.print(f"   ✅ Injected client still works: status={raw_response.status_code}")

    await custom_client.aclose()
    console.print("   ✅ Manually closed injected client")

    console.print("\n2. Using http_client_kwargs for configuration...")
    client_with_kwargs = HTTPBinClient(
        http_client_kwargs={
            "verify": False,
            "follow_redirects": False,
            "timeout": httpx.Timeout(10.0),
        }
    )
    console.print("   ✅ Client created with custom kwargs")

    response = await client_with_kwargs.echo_json({"test": "kwargs config"})
    console.print(f"   Response: {response.json_data}")

    await client_with_kwargs.aclose()
    console.print("   ✅ Client closed (owned by HTTPBinClient)")

    console.print("\n3. Default client for comparison...")
    async with HTTPBinClient() as default_client:
        response = await default_client.echo_json({"test": "default config"})
        console.print(f"   Default client response: {response.json_data}")
        console.print("   ✅ Default client with standard configuration")


async def main() -> None:
    console.print(
        Panel.fit(
            "[bold magenta]🧪 HTTPBin Client Demo[/bold magenta]\nDemonstrating clientry features",
            border_style="magenta",
        )
    )

    async with HTTPBinClient() as client:
        try:
            await demo_json_requests(client)
            await demo_file_upload(client)
            await demo_streaming(client)
            await demo_retry_configuration(client)
            await demo_error_handling(client)
            await demo_concurrent_requests(client)
            await demo_custom_headers(client)

            await demo_client_injection()

            console.print("\n")
            console.print(
                Panel.fit(
                    "[bold green]✅ All demos completed successfully![/bold green]",
                    border_style="green",
                )
            )

        except Exception as e:
            console.print(f"\n[bold red]❌ Demo failed: {e}[/bold red]")
            raise


if __name__ == "__main__":
    asyncio.run(main())
