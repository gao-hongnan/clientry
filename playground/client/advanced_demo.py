from __future__ import annotations

import asyncio
import time
import types
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Self, TypeVar

from pydantic import BaseModel
from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TimeElapsedColumn
from rich.table import Table

from clientry import BaseClient, EmptyRequest, EndpointConfig
from clientry.errors import PermanentError, RetryableError
from playground.client.models import HTTPBinResponse

if TYPE_CHECKING:
    from playground.client.httpbin_client import HTTPBinClient
else:
    from playground.client.httpbin_client import HTTPBinClient

console = Console()

T = TypeVar("T")


@dataclass
class CircuitBreakerState:
    failures: int = 0
    last_failure_time: float = 0.0
    state: str = "closed"
    failure_threshold: int = 5
    recovery_timeout: float = 60.0


class ResilientClient:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._client = HTTPBinClient(*args, **kwargs)
        self._circuit_breaker = CircuitBreakerState()
        self._rate_limit_tokens = 10.0
        self._last_token_refresh = time.time()
        self._token_refresh_rate = 1.0

    async def __aenter__(self) -> Self:
        await self._client.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        await self._client.__aexit__(exc_type, exc_val, exc_tb)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def test_status(self, status_code: int, max_retry_attempts: int | None = None) -> Any:
        return await self._client.test_status(status_code, max_retry_attempts)

    async def _check_circuit_breaker(self) -> None:
        now = time.time()

        if self._circuit_breaker.state == "open":
            if now - self._circuit_breaker.last_failure_time > self._circuit_breaker.recovery_timeout:
                self._circuit_breaker.state = "half_open"
                console.print("🔄 Circuit breaker: HALF_OPEN (testing)")
            else:
                raise PermanentError("Circuit breaker OPEN - failing fast")

    async def _rate_limit(self) -> None:
        now = time.time()
        elapsed = now - self._last_token_refresh
        self._rate_limit_tokens = min(10, self._rate_limit_tokens + elapsed * self._token_refresh_rate)
        self._last_token_refresh = now

        if self._rate_limit_tokens < 1:
            wait_time = (1 - self._rate_limit_tokens) / self._token_refresh_rate
            console.print(f"🚦 Rate limited, waiting {wait_time:.1f}s")
            await asyncio.sleep(wait_time)

        self._rate_limit_tokens -= 1

    async def echo_json_resilient(self, data: dict[str, Any]) -> HTTPBinResponse:
        await self._check_circuit_breaker()
        await self._rate_limit()

        try:
            response = await self._client.echo_json(data)

            if self._circuit_breaker.state == "half_open":
                self._circuit_breaker.state = "closed"
                self._circuit_breaker.failures = 0
                console.print("✅ Circuit breaker: CLOSED (recovered)")

            return response

        except (RetryableError, PermanentError):
            self._circuit_breaker.failures += 1
            self._circuit_breaker.last_failure_time = time.time()

            if self._circuit_breaker.failures >= self._circuit_breaker.failure_threshold:
                self._circuit_breaker.state = "open"
                console.print("💥 Circuit breaker: OPEN (too many failures)")

            raise


class GitHubUser(BaseModel):
    login: str
    id: int
    name: str | None = None
    public_repos: int = 0
    followers: int = 0
    following: int = 0


class GitHubRepo(BaseModel):
    id: int
    name: str
    full_name: str
    private: bool = False
    description: str | None = None
    stargazers_count: int = 0
    language: str | None = None


class GitHubClient(BaseClient):
    USER_ENDPOINT = EndpointConfig[EmptyRequest, GitHubUser](
        path="/users/{username}",
        method="GET",
        request_type=EmptyRequest,
        response_type=GitHubUser,
    )

    def __init__(self) -> None:
        super().__init__(
            base_url="https://api.github.com",
            default_headers={"Accept": "application/vnd.github.v3+json"},
        )

    async def get_user(self, username: str) -> GitHubUser:
        endpoint = self.USER_ENDPOINT.model_copy(update={"path": f"/users/{username}"})
        return await self._arequest(endpoint, EmptyRequest())


@asynccontextmanager
async def demo_section(title: str, description: str) -> AsyncIterator[None]:
    start_time = time.perf_counter()

    panel = Panel.fit(f"[bold cyan]{title}[/bold cyan]\n{description}", border_style="cyan")
    console.print("\n")
    console.print(panel)

    try:
        yield
    finally:
        elapsed = time.perf_counter() - start_time
        console.print(f"[dim]⏱️  Section completed in {elapsed:.2f}s[/dim]")


async def demo_generic_pattern() -> None:
    async with demo_section("🎯 Generic Request Pattern", "Type-safe endpoints with zero code duplication"):
        results_table = Table(title="Generic Pattern Results")
        results_table.add_column("Client", style="cyan")
        results_table.add_column("Endpoint", style="yellow")
        results_table.add_column("Result", style="green")

        async with HTTPBinClient() as httpbin_client, GitHubClient() as github_client:
            response = await httpbin_client.get_request({"demo": "generic_pattern"})
            results_table.add_row("HTTPBin", "GET /get", f"✅ {len(response.args)} params echoed")

            json_response = await httpbin_client.echo_json({"pattern": "generic", "type_safe": True})
            pattern_value = json_response.json_data.get("pattern") if json_response.json_data else None
            results_table.add_row(
                "HTTPBin",
                "POST /post",
                f"✅ JSON echoed: {pattern_value}",
            )

            try:
                user = await github_client.get_user("octocat")
                results_table.add_row(
                    "GitHub",
                    "GET /users/octocat",
                    f"✅ User: {user.name or 'N/A'} ({user.public_repos} repos)",
                )
            except Exception as e:
                results_table.add_row("GitHub", "GET /users/octocat", f"❌ {str(e)[:50]}")

        console.print(results_table)
        console.print("[dim]💡 Same BaseClient, different APIs, full type safety[/dim]")


async def demo_error_resilience() -> None:
    async with (
        demo_section("🛡️ Error Resilience", "Circuit breakers, retries, and graceful degradation"),
        ResilientClient() as client,
    ):
        error_scenarios = [
            ("✅ Success", lambda: client.echo_json_resilient({"test": "success"})),
            (
                "⚠️ Rate Limited",
                lambda: asyncio.gather(*[client.echo_json_resilient({"burst": i}) for i in range(15)]),
            ),
            ("💥 Failures", lambda: client.test_status(503, max_retry_attempts=1)),
        ]

        for scenario_name, scenario_func in error_scenarios:
            console.print(f"\n[yellow]{scenario_name}[/yellow]")
            try:
                start = time.perf_counter()
                result = await scenario_func()
                elapsed = time.perf_counter() - start

                if isinstance(result, list):
                    console.print(f"   📊 Processed {len(result)} requests in {elapsed:.2f}s")
                    console.print(f"   🚀 Throughput: {len(result) / elapsed:.1f} req/s")
                else:
                    console.print(f"   ✅ Completed in {elapsed:.2f}s")

            except (RetryableError, PermanentError) as e:
                console.print(f"   ❌ Expected failure: {e.status_code}")
            except Exception as e:
                console.print(f"   🔄 Handled: {type(e).__name__}")


async def demo_concurrent_patterns() -> None:
    async with (
        demo_section(
            "🚀 Concurrent Patterns",
            "Batching, parallel processing, and performance optimization",
        ),
        HTTPBinClient() as client,
    ):
        batch_sizes = [1, 5, 10, 20]

        results_table = Table(title="Concurrency Performance")
        results_table.add_column("Batch Size", justify="center")
        results_table.add_column("Time (s)", justify="right")
        results_table.add_column("Throughput (req/s)", justify="right")
        results_table.add_column("Efficiency", style="green")

        for batch_size in batch_sizes:
            requests = [client.echo_json({"batch_id": batch_size, "request_id": i}) for i in range(batch_size)]

            with Progress(
                SpinnerColumn(),
                "[progress.description]{task.description}",
                BarColumn(),
                TimeElapsedColumn(),
                console=console,
                transient=True,
            ) as progress:
                task = progress.add_task(f"Processing batch of {batch_size}...", total=batch_size)

                start = time.perf_counter()
                results = await asyncio.gather(*requests, return_exceptions=True)
                elapsed = time.perf_counter() - start

                progress.update(task, completed=batch_size)

            successful = sum(1 for r in results if not isinstance(r, Exception))
            throughput = successful / elapsed if elapsed > 0 else 0
            efficiency = "🔥" if throughput > 15 else "⚡" if throughput > 10 else "✅"

            results_table.add_row(
                str(batch_size),
                f"{elapsed:.2f}",
                f"{throughput:.1f}",
                f"{efficiency} {successful}/{batch_size}",
            )

        console.print(results_table)


async def demo_production_patterns() -> None:
    async with demo_section(
        "🏭 Production Patterns",
        "Real-world patterns: caching, monitoring, graceful shutdown",
    ):
        cache: dict[str, tuple[Any, float]] = {}
        cache_ttl = 5.0

        async def cached_request(client: HTTPBinClient, key: str, data: dict[str, Any]) -> HTTPBinResponse:
            now = time.time()

            if key in cache:
                cached_data, timestamp = cache[key]
                if now - timestamp < cache_ttl:
                    console.print(f"💾 Cache hit for {key}")
                    return cached_data

            console.print(f"🌐 Cache miss for {key} - fetching...")
            result = await client.echo_json(data)
            cache[key] = (result, now)
            return result

        request_count = 0
        error_count = 0

        async def monitored_request(client: HTTPBinClient, data: dict[str, Any]) -> HTTPBinResponse | None:
            nonlocal request_count, error_count
            request_count += 1

            try:
                return await client.echo_json(data)
            except Exception as e:
                error_count += 1
                console.print(f"📊 Recorded error: {type(e).__name__}")
                return None

        async with HTTPBinClient() as client:
            workflow_table = Table(title="Production Workflow Results")
            workflow_table.add_column("Operation", style="cyan")
            workflow_table.add_column("Result", style="green")
            workflow_table.add_column("Cache", style="yellow")
            workflow_table.add_column("Monitoring", style="blue")

            operations = [
                ("user_profile", {"user_id": 123, "action": "get_profile"}),
                ("user_profile", {"user_id": 123, "action": "get_profile"}),
                ("user_settings", {"user_id": 123, "action": "get_settings"}),
                ("user_profile", {"user_id": 456, "action": "get_profile"}),
            ]

            for i, (cache_key, request_data) in enumerate(operations):
                await cached_request(client, cache_key, request_data)
                await monitored_request(client, {"monitoring": "demo"})

                is_cached = cache_key in cache and i > 0 and cache_key == operations[i - 1][0]

                workflow_table.add_row(
                    f"Request {i + 1}",
                    "✅ Success",
                    "💾 Hit" if is_cached else "🌐 Miss",
                    f"📊 {request_count} reqs",
                )

            console.print(workflow_table)

            metrics_panel = Panel(
                f"[green]📈 Session Metrics[/green]\n"
                f"Total Requests: {request_count}\n"
                f"Errors: {error_count}\n"
                f"Success Rate: {((request_count - error_count) / request_count * 100):.1f}%\n"
                f"Cache Entries: {len(cache)}",
                border_style="green",
            )
            console.print(metrics_panel)


async def main() -> None:
    console.print(
        Panel.fit(
            "[bold magenta]🚀 Advanced Client Patterns Demo[/bold magenta]\n"
            "Generic Request Pattern • Error Resilience • Concurrency • Production Patterns",
            border_style="magenta",
        )
    )

    demos = [
        demo_generic_pattern,
        demo_error_resilience,
        demo_concurrent_patterns,
        demo_production_patterns,
    ]

    total_start = time.perf_counter()

    for demo in demos:
        try:
            await demo()
        except Exception as e:
            console.print(f"[red]❌ Demo failed: {e}[/red]")
            continue

    total_elapsed = time.perf_counter() - total_start

    console.print("\n")
    console.print(
        Panel.fit(
            f"[bold green]✅ All demos completed in {total_elapsed:.2f}s![/bold green]\n"
            "[dim]The Generic Request Pattern provides type safety, reusability, and elegance.[/dim]",
            border_style="green",
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
