from app.load_testing import (
    LoadTestConfig,
    RequestSample,
    evaluate_thresholds,
    percentile,
    summarize_samples,
)


def config(**overrides):
    values = {
        "base_url": "https://example.com",
        "collection_id": "load_test_collection_01",
        "users": 4,
        "duration_seconds": 10,
        "ramp_seconds": 1,
        "max_error_rate_percent": 1,
        "p95_limit_ms": 500,
        "p99_limit_ms": 1000,
        "min_requests_per_second": 1,
    }
    values.update(overrides)
    return LoadTestConfig(**values)


def test_percentile_uses_nearest_rank():
    values = [10.0, 20.0, 30.0, 40.0, 50.0]

    assert percentile(values, 50) == 30.0
    assert percentile(values, 95) == 50.0
    assert percentile([], 95) is None


def test_summary_groups_endpoints_and_passes_thresholds():
    samples = [
        RequestSample("/health", 200, 40.0, True),
        RequestSample("/health", 200, 55.0, True),
        RequestSample("/api/collections/demo/metrics", 200, 90.0, True),
        RequestSample("/api/generations [validation-only]", 422, 120.0, True),
    ]
    settings = config()

    summary = summarize_samples(samples, elapsed_seconds=2.0, config=settings)
    result = evaluate_thresholds(summary, settings)

    assert summary["requests"] == 4
    assert summary["requests_per_second"] == 2.0
    assert summary["error_rate_percent"] == 0.0
    assert summary["latency_ms"]["p95"] == 120.0
    assert summary["by_endpoint"]["/health"]["requests"] == 2
    assert result.passed is True
    assert result.failures == []


def test_thresholds_fail_for_errors_latency_and_low_throughput():
    samples = [
        RequestSample("/health", 500, 1800.0, False, "expected 200, received 500"),
        RequestSample("/health", None, 2200.0, False, "ReadTimeout"),
    ]
    settings = config(
        max_error_rate_percent=1,
        p95_limit_ms=500,
        p99_limit_ms=1000,
        min_requests_per_second=5,
    )

    summary = summarize_samples(samples, elapsed_seconds=10.0, config=settings)
    result = evaluate_thresholds(summary, settings)

    assert result.passed is False
    assert any("error rate" in failure for failure in result.failures)
    assert any("p95" in failure for failure in result.failures)
    assert any("p99" in failure for failure in result.failures)
    assert any("throughput" in failure for failure in result.failures)


def test_config_rejects_unsafe_dimensions():
    settings = config(users=0)

    try:
        settings.validate()
    except ValueError as exc:
        assert "users" in str(exc)
    else:
        raise AssertionError("Expected invalid users to raise ValueError")
