from __future__ import annotations

import argparse
import asyncio
import json
import math
import random
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any, Literal

import httpx


Scenario = Literal["read", "mixed"]


@dataclass(frozen=True, slots=True)
class LoadTestConfig:
    base_url: str
    collection_id: str
    users: int = 10
    duration_seconds: float = 30.0
    ramp_seconds: float = 5.0
    scenario: Scenario = "mixed"
    request_timeout_seconds: float = 20.0
    think_time_seconds: float = 0.05
    max_error_rate_percent: float = 1.0
    p95_limit_ms: float = 1500.0
    p99_limit_ms: float = 3000.0
    min_requests_per_second: float = 1.0

    def validate(self) -> None:
        if not self.base_url.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        if not 1 <= self.users <= 500:
            raise ValueError("users must be between 1 and 500")
        if not 1 <= self.duration_seconds <= 3600:
            raise ValueError("duration_seconds must be between 1 and 3600")
        if not 0 <= self.ramp_seconds <= self.duration_seconds:
            raise ValueError("ramp_seconds must be between 0 and duration_seconds")
        if self.scenario not in {"read", "mixed"}:
            raise ValueError("scenario must be read or mixed")
        if self.think_time_seconds < 0:
            raise ValueError("think_time_seconds cannot be negative")


@dataclass(frozen=True, slots=True)
class RequestSample:
    endpoint: str
    status_code: int | None
    elapsed_ms: float
    ok: bool
    error: str | None = None


@dataclass(frozen=True, slots=True)
class ThresholdResult:
    passed: bool
    failures: list[str]


READ_ENDPOINTS = ("/health", "/", "/versions", "/metrics")


async def run_load_test(config: LoadTestConfig) -> tuple[dict[str, Any], ThresholdResult]:
    config.validate()
    samples: list[RequestSample] = []
    sample_lock = asyncio.Lock()
    started = perf_counter()
    deadline = started + config.duration_seconds
    limits = httpx.Limits(
        max_connections=max(20, config.users * 2),
        max_keepalive_connections=max(10, config.users),
    )

    async with httpx.AsyncClient(
        base_url=config.base_url.rstrip("/"),
        follow_redirects=True,
        timeout=httpx.Timeout(config.request_timeout_seconds),
        limits=limits,
        headers={"User-Agent": "ez-ai-album-cover-load-test/1.0"},
    ) as client:
        tasks = [
            asyncio.create_task(
                _worker(
                    worker_id=index,
                    client=client,
                    config=config,
                    deadline=deadline,
                    samples=samples,
                    sample_lock=sample_lock,
                )
            )
            for index in range(config.users)
        ]
        await asyncio.gather(*tasks)

    elapsed = max(perf_counter() - started, 0.001)
    summary = summarize_samples(samples, elapsed, config)
    thresholds = evaluate_thresholds(summary, config)
    summary["thresholds"] = asdict(thresholds)
    return summary, thresholds


async def _worker(
    *,
    worker_id: int,
    client: httpx.AsyncClient,
    config: LoadTestConfig,
    deadline: float,
    samples: list[RequestSample],
    sample_lock: asyncio.Lock,
) -> None:
    if config.users > 1 and config.ramp_seconds:
        delay = config.ramp_seconds * worker_id / (config.users - 1)
        await asyncio.sleep(delay)

    request_number = 0
    rng = random.Random(worker_id + 20260803)
    while perf_counter() < deadline:
        request_number += 1
        sample = await _execute_request(
            client=client,
            config=config,
            worker_id=worker_id,
            request_number=request_number,
            rng=rng,
        )
        async with sample_lock:
            samples.append(sample)
        if config.think_time_seconds:
            jitter = config.think_time_seconds * rng.uniform(0.6, 1.4)
            await asyncio.sleep(jitter)


async def _execute_request(
    *,
    client: httpx.AsyncClient,
    config: LoadTestConfig,
    worker_id: int,
    request_number: int,
    rng: random.Random,
) -> RequestSample:
    endpoint, method, expected_status = _choose_request(config, request_number, rng)
    started = perf_counter()
    try:
        if method == "POST":
            response = await client.post(
                "/api/generations",
                files={
                    "collection_id": (None, config.collection_id),
                    "lyrics_text": (None, ""),
                    "run_async": (None, "true"),
                },
                headers={"X-Load-Test-Worker": str(worker_id)},
            )
        else:
            response = await client.get(endpoint)
        elapsed_ms = (perf_counter() - started) * 1000
        ok = response.status_code == expected_status
        return RequestSample(
            endpoint=endpoint,
            status_code=response.status_code,
            elapsed_ms=elapsed_ms,
            ok=ok,
            error=None if ok else f"expected {expected_status}, received {response.status_code}",
        )
    except Exception as exc:  # httpx exposes several transport/timeout subclasses.
        return RequestSample(
            endpoint=endpoint,
            status_code=None,
            elapsed_ms=(perf_counter() - started) * 1000,
            ok=False,
            error=f"{type(exc).__name__}: {exc}",
        )


def _choose_request(
    config: LoadTestConfig, request_number: int, rng: random.Random
) -> tuple[str, str, int]:
    if config.scenario == "mixed" and request_number % 10 == 0:
        # This deliberately invalid submission exercises multipart parsing and validation
        # without queuing Gemini/OpenAI work or consuming image credits.
        return "/api/generations [validation-only]", "POST", 422

    choice = rng.choice(READ_ENDPOINTS)
    if choice == "/versions":
        return f"/api/collections/{config.collection_id}/versions", "GET", 200
    if choice == "/metrics":
        return f"/api/collections/{config.collection_id}/metrics", "GET", 200
    return choice, "GET", 200


def summarize_samples(
    samples: list[RequestSample], elapsed_seconds: float, config: LoadTestConfig
) -> dict[str, Any]:
    latencies = sorted(sample.elapsed_ms for sample in samples)
    successful = [sample for sample in samples if sample.ok]
    failed = [sample for sample in samples if not sample.ok]
    by_endpoint: dict[str, dict[str, Any]] = {}

    for endpoint in sorted({sample.endpoint for sample in samples}):
        endpoint_samples = [sample for sample in samples if sample.endpoint == endpoint]
        endpoint_latencies = sorted(sample.elapsed_ms for sample in endpoint_samples)
        endpoint_failures = sum(not sample.ok for sample in endpoint_samples)
        by_endpoint[endpoint] = {
            "requests": len(endpoint_samples),
            "failures": endpoint_failures,
            "error_rate_percent": _percent(endpoint_failures, len(endpoint_samples)),
            "average_ms": _average(endpoint_latencies),
            "p95_ms": percentile(endpoint_latencies, 95),
            "p99_ms": percentile(endpoint_latencies, 99),
            "max_ms": round(max(endpoint_latencies), 2) if endpoint_latencies else None,
        }

    error_examples = []
    for sample in failed:
        if sample.error and sample.error not in error_examples:
            error_examples.append(sample.error)
        if len(error_examples) == 5:
            break

    return {
        "config": asdict(config),
        "duration_seconds": round(elapsed_seconds, 3),
        "requests": len(samples),
        "successful_requests": len(successful),
        "failed_requests": len(failed),
        "requests_per_second": round(len(samples) / max(elapsed_seconds, 0.001), 2),
        "error_rate_percent": _percent(len(failed), len(samples)),
        "latency_ms": {
            "average": _average(latencies),
            "p50": percentile(latencies, 50),
            "p95": percentile(latencies, 95),
            "p99": percentile(latencies, 99),
            "max": round(max(latencies), 2) if latencies else None,
        },
        "by_endpoint": by_endpoint,
        "error_examples": error_examples,
    }


def evaluate_thresholds(summary: dict[str, Any], config: LoadTestConfig) -> ThresholdResult:
    failures: list[str] = []
    error_rate = float(summary.get("error_rate_percent") or 0)
    rps = float(summary.get("requests_per_second") or 0)
    latency = summary.get("latency_ms") or {}
    p95 = float(latency.get("p95") or math.inf)
    p99 = float(latency.get("p99") or math.inf)

    if int(summary.get("requests") or 0) == 0:
        failures.append("no requests completed")
    if error_rate > config.max_error_rate_percent:
        failures.append(
            f"error rate {error_rate:.2f}% exceeded {config.max_error_rate_percent:.2f}%"
        )
    if p95 > config.p95_limit_ms:
        failures.append(f"p95 {p95:.2f}ms exceeded {config.p95_limit_ms:.2f}ms")
    if p99 > config.p99_limit_ms:
        failures.append(f"p99 {p99:.2f}ms exceeded {config.p99_limit_ms:.2f}ms")
    if rps < config.min_requests_per_second:
        failures.append(
            f"throughput {rps:.2f} req/s was below {config.min_requests_per_second:.2f} req/s"
        )
    return ThresholdResult(passed=not failures, failures=failures)


def percentile(values: list[float], value: int) -> float | None:
    if not values:
        return None
    rank = max(1, math.ceil((value / 100) * len(values)))
    return round(values[min(rank - 1, len(values) - 1)], 2)


def _average(values: list[float]) -> float | None:
    return round(mean(values), 2) if values else None


def _percent(part: int, total: int) -> float:
    return round(part / total * 100, 3) if total else 0.0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run a safe asynchronous load test against EZ AI Album Cover Studio. "
            "The mixed scenario never queues paid image generation."
        )
    )
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--collection-id", default="load_test_collection_01")
    parser.add_argument("--users", type=int, default=10)
    parser.add_argument("--duration", type=float, default=30.0)
    parser.add_argument("--ramp", type=float, default=5.0)
    parser.add_argument("--scenario", choices=("read", "mixed"), default="mixed")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--think-time", type=float, default=0.05)
    parser.add_argument("--max-error-rate", type=float, default=1.0)
    parser.add_argument("--p95-limit-ms", type=float, default=1500.0)
    parser.add_argument("--p99-limit-ms", type=float, default=3000.0)
    parser.add_argument("--min-rps", type=float, default=1.0)
    parser.add_argument("--json-output", type=Path)
    return parser


def _print_summary(summary: dict[str, Any]) -> None:
    latency = summary["latency_ms"]
    thresholds = summary["thresholds"]
    state = "PASS" if thresholds["passed"] else "FAIL"
    print(f"\nLoad test: {state}")
    print(
        f"{summary['requests']} requests | {summary['requests_per_second']} req/s | "
        f"{summary['error_rate_percent']}% errors"
    )
    print(
        f"latency avg={latency['average']}ms p50={latency['p50']}ms "
        f"p95={latency['p95']}ms p99={latency['p99']}ms max={latency['max']}ms"
    )
    for endpoint, values in summary["by_endpoint"].items():
        print(
            f"  {endpoint}: {values['requests']} req | {values['error_rate_percent']}% errors | "
            f"p95 {values['p95_ms']}ms"
        )
    for failure in thresholds["failures"]:
        print(f"  threshold failure: {failure}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = LoadTestConfig(
        base_url=args.base_url,
        collection_id=args.collection_id,
        users=args.users,
        duration_seconds=args.duration,
        ramp_seconds=args.ramp,
        scenario=args.scenario,
        request_timeout_seconds=args.timeout,
        think_time_seconds=args.think_time,
        max_error_rate_percent=args.max_error_rate,
        p95_limit_ms=args.p95_limit_ms,
        p99_limit_ms=args.p99_limit_ms,
        min_requests_per_second=args.min_rps,
    )
    try:
        summary, thresholds = asyncio.run(run_load_test(config))
    except (ValueError, KeyboardInterrupt) as exc:
        print(f"Load test did not run: {exc}", file=sys.stderr)
        return 2

    _print_summary(summary)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(json.dumps(summary, indent=2, default=str) + "\n")
        print(f"JSON report: {args.json_output}")
    return 0 if thresholds.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
