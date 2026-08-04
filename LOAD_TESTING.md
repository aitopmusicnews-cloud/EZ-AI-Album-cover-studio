# Load testing

The repository includes a dependency-free asynchronous load tester built on the existing `httpx` dependency:

```bash
cd backend
python -m app.load_testing \
  --base-url https://YOUR-SERVICE.onrender.com \
  --collection-id YOUR_EXISTING_COLLECTION_ID \
  --users 10 \
  --duration 30 \
  --ramp 5 \
  --scenario mixed \
  --json-output ../load-test-results/smoke.json
```

The process exits with status `0` when every threshold passes and status `1` when a performance threshold fails, making it suitable for CI or release checks.

## Safe scenarios

### `read`

Exercises the routes used continuously by the browser:

- `GET /health`
- `GET /`
- `GET /api/collections/{collection_id}/versions`
- `GET /api/collections/{collection_id}/metrics`

### `mixed`

Uses the same read traffic plus a validation-only multipart request every tenth iteration. The request intentionally contains no audio or lyrics and expects HTTP `422`. It exercises upload parsing and request validation without queuing Gemini or OpenAI work.

**Neither scenario creates album covers or consumes image-generation credits.** Do not repurpose this runner to submit valid generation jobs against production. Full generation concurrency should be tested only on an isolated staging service configured with mock providers and a separate database/storage location.

## Default release thresholds

The defaults are intentionally conservative for a single Render web-service instance:

- Error rate: no more than `1%`
- Overall p95 latency: no more than `1500 ms`
- Overall p99 latency: no more than `3000 ms`
- Throughput: at least `1 request/second`

Override them when the service plan and release target justify different limits:

```bash
python -m app.load_testing \
  --base-url https://YOUR-SERVICE.onrender.com \
  --users 25 \
  --duration 60 \
  --p95-limit-ms 1000 \
  --p99-limit-ms 2000 \
  --max-error-rate 0.5 \
  --min-rps 10
```

## Recommended test ladder

Run each stage only after the previous stage passes:

| Stage | Users | Duration | Ramp | Purpose |
|---|---:|---:|---:|---|
| Smoke | 5 | 20 seconds | 5 seconds | Verify deployment and thresholds |
| Normal | 15 | 60 seconds | 15 seconds | Approximate normal concurrent browsing |
| Peak | 30 | 120 seconds | 30 seconds | Validate a short release-day spike |
| Soak | 15 | 15 minutes | 60 seconds | Detect memory growth and connection exhaustion |

Start with `read`, then repeat with `mixed`. Avoid sudden high-concurrency tests on a production service that is actively serving users.

## One-command smoke test

From the repository root after `make setup`:

```bash
make load-smoke \
  LOAD_BASE_URL=https://YOUR-SERVICE.onrender.com \
  LOAD_COLLECTION_ID=YOUR_EXISTING_COLLECTION_ID
```

The target writes a JSON report to `load-test-results/smoke.json`.

## Reading the report

The terminal and JSON report include:

- Total requests and requests per second
- Error rate and up to five distinct error examples
- Average, p50, p95, p99, and maximum latency
- Per-endpoint request, failure, and latency summaries
- A pass/fail result for every configured threshold

During a live test, compare these results with Render CPU, memory, HTTP latency, request count, database connections, and instance metrics. A passing client report with CPU or memory pinned near the service limit still indicates insufficient headroom.

## Full generation testing

Artwork generation depends on long-running external AI calls and has a real per-request cost. Test it separately on staging:

1. Use an isolated Render service and database.
2. Set `ALLOW_MOCK_IMAGES=true` and use mocked or disabled external providers.
3. Submit a small fixed number of generation jobs.
4. Measure queue time, completion time, partial failures, retries, database connections, and storage growth.
5. Remove the staging data after the test.

The production-safe runner intentionally does not automate this paid workflow.
