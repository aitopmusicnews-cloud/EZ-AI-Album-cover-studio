# EZ AI Album Cover Studio

A complete, self-contained album-cover generation pipeline for a new project. Users can upload an MP3, lyrics, or both; the backend extracts audio and lyric signals, detects mood conflicts, converts those signals into visual art direction, creates 3–5 OpenAI image variations, normalizes every image to exactly **1000×1000 PNG**, and stores a versioned audit trail.

The stack is deliberately small and Intel-Mac friendly:

- **FastAPI** API and background jobs
- **SQLAlchemy + SQLite** by default, with Alembic migrations
- **librosa** for MP3/music analysis
- Lightweight in-process lyrics NLP with no model download
- **OpenAI Image API** adapter supporting `gpt-image-1`, `gpt-image-2`, and legacy `dall-e-3`
- Local filesystem image storage behind a replaceable storage class
- No-build HTML/CSS/JavaScript UI served by FastAPI
- Pytest integration and unit tests with a mocked image provider

No modern stack can run on every historical macOS release. This code contains no Apple-Silicon-only components and targets Intel Macs that can run **Python 3.11+**. The no-build frontend removes Node.js as a runtime requirement.

## What is implemented

- MP3-only, lyrics-only, and combined uploads
- Extension, MIME, magic-byte, size, UTF-8, and text-length validation
- Audio tempo/BPM, RMS energy, loudness, spectral centroid/bandwidth/rolloff/contrast/flatness, zero-crossing rate, bass ratio, key/scale, dominant frequencies, mood, and heuristic genre/style
- Lyric keywords, themes, tone, imagery, sentiment/valence, energy, and mood
- Exactly equal `0.5 / 0.5` source weights when both inputs are present
- Mood-conflict detection with separate audio-driven and lyric-driven generation choices
- Visual prompt construction rather than raw technical-value prompting
- 3–5 independently generated concepts per variation set
- Exact 1000×1000 PNG normalization and immediate local persistence
- Input-hash cache reuse without rerunning analysis or OpenAI
- Immutable input versions and append-only fresh variation sets
- Historical version browsing, variation selection, and downloads
- Per-step exponential retry logging
- Partial-analysis persistence and partial-image-set resume
- Clear status/error records for authentication, rate-limit, request, timeout, and service failures

## Branding

The browser UI uses the supplied **The Beat'z EZ — The Easy Way** artwork as its primary logo and derives the favicon and installable-app icons from the same source. Brand assets live in `frontend/assets/`:

- `ez-album-cover-logo.png` — optimized 640×640 interface logo
- `favicon.ico`, `favicon-32x32.png`, and `favicon-16x16.png` — browser-tab icons
- `apple-touch-icon.png` — iOS/macOS shortcut icon
- `icon-192.png`, `icon-512.png`, and `site.webmanifest` — installable web-app metadata

The interface palette is based on the logo: charcoal black surfaces, brushed-steel neutrals, warm ivory text, and copper-orange accents. Theme values are centralized as CSS custom properties at the top of `frontend/styles.css`, so the palette can be adjusted without changing component rules.

## Project layout

```text
album-cover-studio/
├── backend/
│   ├── app/
│   │   ├── audio_analysis.py      # librosa feature extraction
│   │   ├── lyrics_analysis.py     # lightweight NLP
│   │   ├── signals.py             # equal weighting + conflict detection
│   │   ├── prompts.py             # signal-to-visual prompt translation
│   │   ├── image_client.py        # OpenAI Image API adapter
│   │   ├── service.py             # pipeline, cache, retry, versioning
│   │   ├── models.py              # audit/version schema
│   │   └── routers/generations.py # API endpoints
│   ├── alembic/                   # production migrations
│   └── tests/                     # 19 passing tests
├── frontend/                      # no-build browser UI + branded assets
├── data/                          # SQLite DB and generated files
├── .env.example
└── Makefile
```

## macOS Intel setup

Install Apple command-line tools and native audio dependencies:

```bash
xcode-select --install
brew install python@3.12 ffmpeg libsndfile
```

Create the environment and install the app:

```bash
cd album-cover-studio
make setup
cp .env.example .env
```

Edit `.env` and set `OPENAI_API_KEY`. Absolute paths are safest for `DATABASE_URL`, `STORAGE_ROOT`, and `FRONTEND_ROOT`; the built-in defaults already resolve to this project’s `data/` and `frontend/` directories when those variables are omitted.

Run the app:

```bash
make run
```

Open `http://127.0.0.1:8000`. OpenAPI documentation is available at `http://127.0.0.1:8000/docs`.

### Schema management

Development defaults to `AUTO_CREATE_SCHEMA=true`, which creates missing tables at startup. For a deployed environment, use migrations:

```bash
export AUTO_CREATE_SCHEMA=false
make migrate
make run
```

SQLite is appropriate for a single-process deployment. For multiple API workers, set `DATABASE_URL` to PostgreSQL and replace `LocalStorage` with S3-compatible object storage while keeping the service interface unchanged.

## Environment variables

| Variable | Required | Default | Purpose |
|---|---:|---|---|
| `OPENAI_API_KEY` | Yes for real images | none | Server-side OpenAI credential; never sent to the browser |
| `OPENAI_IMAGE_MODEL` | No | `gpt-image-1` | Image API model; `gpt-image-2` and `dall-e-3` are supported |
| `OPENAI_IMAGE_QUALITY` | No | `medium` | GPT Image quality; maps to `standard`/`hd` for DALL·E 3 |
| `OPENAI_TIMEOUT_SECONDS` | No | `150` | Per-request image generation timeout |
| `DATABASE_URL` | No | project-local SQLite | SQLAlchemy database URL |
| `STORAGE_ROOT` | No | `data/storage` | Input and normalized image storage |
| `FRONTEND_ROOT` | No | `frontend` | Static browser application directory |
| `MAX_AUDIO_MB` | No | `30` | MP3 upload limit |
| `MAX_LYRICS_CHARS` | No | `50000` | Sanitized lyric character limit |
| `AUDIO_ANALYSIS_MAX_SECONDS` | No | `180` | Maximum decoded audio duration analyzed |
| `RETRY_MAX_ATTEMPTS` | No | `3` | Attempts per audio, lyrics, or image step |
| `RETRY_BASE_DELAY_SECONDS` | No | `0.75` | Exponential-backoff base delay |
| `AUTO_CREATE_SCHEMA` | No | `true` | Bootstrap tables automatically |
| `ALLOW_MOCK_IMAGES` | No | `false` | Development-only placeholder output without an API key |
| `CORS_ORIGINS` | No | `http://localhost:5173` | Separate-frontend allowed origins |

## API usage

### Create or reuse an input version

`POST /api/generations` accepts multipart form data:

- `audio`: optional `.mp3`
- `lyrics_file`: optional UTF-8 `.txt`
- `lyrics_text`: optional pasted text
- `collection_id`: optional 8–64 character browser/session grouping ID
- `variation_count`: `3`, `4`, or `5`
- `mood_path`: normally `auto`
- `run_async`: normally `true`

MP3-only example:

```bash
curl -X POST http://127.0.0.1:8000/api/generations \
  -F 'collection_id=demo_collection_01' \
  -F 'audio=@song.mp3;type=audio/mpeg' \
  -F 'variation_count=4' \
  -F 'mood_path=auto' \
  -F 'run_async=true'
```

Combined example:

```bash
curl -X POST http://127.0.0.1:8000/api/generations \
  -F 'collection_id=demo_collection_01' \
  -F 'audio=@song.mp3;type=audio/mpeg' \
  -F 'lyrics_file=@lyrics.txt;type=text/plain' \
  -F 'variation_count=4' \
  -F 'run_async=true'
```

The create route returns `202` for a queued job, `200` for an exact cache hit, or `201` when `run_async=false` completes inline. Poll:

```bash
curl http://127.0.0.1:8000/api/generations/GENERATION_ID
```

Terminal states are `complete`, `partial`, `analysis_failed`, `image_failed`, and `needs_mood_choice`.

### Resolve a mood conflict

When `status` is `needs_mood_choice`, the response includes `conflict.audio_path` and `conflict.lyrics_path`. Generate one path without redoing analysis:

```bash
curl -X POST http://127.0.0.1:8000/api/generations/GENERATION_ID/generate \
  -H 'Content-Type: application/json' \
  -d '{"mood_path":"audio","variation_count":4,"run_async":true}'
```

Use `"lyrics"` to prioritize lyric mood instead.

### Fresh regeneration

Fresh variations append a new set to the same input version. Previous images remain accessible:

```bash
curl -X POST http://127.0.0.1:8000/api/generations/GENERATION_ID/regenerate \
  -H 'Content-Type: application/json' \
  -d '{"mood_path":"blend","variation_count":4,"run_async":true}'
```

### Retry only incomplete work

```bash
curl -X POST 'http://127.0.0.1:8000/api/generations/GENERATION_ID/retry?run_async=true'
```

If analysis is incomplete, only missing analysis signals are rerun. If a variation set is partial or failed, only missing image positions are generated.

### History, selection, and download

```text
GET  /api/collections/{collection_id}/versions
POST /api/variations/{variation_id}/select
GET  /api/variations/{variation_id}/download
```

## Signal extraction and equal weighting

### Audio

`AudioAnalyzer` loads a maximum configured duration at 22.05 kHz mono, then computes:

- tempo using librosa’s tempo estimator
- RMS and dBFS-like loudness normalization
- spectral centroid, bandwidth, rolloff, flatness, contrast, and zero crossings
- low-frequency power ratio and five separated dominant FFT frequencies
- chroma-profile key and major/minor-scale correlation
- heuristic genre and style tags
- a normalized mood `{label, valence, energy}`

Genre classification is intentionally lightweight and transparent. It is a prompt signal, not a definitive musicological label.

### Lyrics

The lyric analyzer Unicode-normalizes and sanitizes text, then applies stop-word filtering, frequency-based keyword extraction, small explainable sentiment/emotion lexicons, theme vocabularies, and imagery detection. It requires no external NLP model or corpus download.

### Combined payload

When both sources are present, `combine_signals` records:

```json
"source_weights": { "audio": 0.5, "lyrics": 0.5 }
```

Blended valence and energy are arithmetic means. Audio-derived visual themes and lyric themes are interleaved so both sources contribute to the final structured payload. Raw technical fields remain in the audit JSON, while the prompt builder maps them into palette, light, composition, pacing, texture, and symbolic motifs.

## Conflict detection

A conflict is flagged only when both inputs exist and one of these conditions is met:

1. Audio and lyric valence have opposite polarity and differ by at least `0.60`.
2. The audio is positively valenced and energetic while lyrics are strongly negative.
3. The audio is strongly negative while lyrics are strongly positive.

The API stops before spending image-generation calls and returns two paths:

- **Audio-driven:** musical tempo, energy, tonality, and production style control the emotional center; lyric motifs remain secondary.
- **Lyrics-driven:** lyric sentiment, themes, and imagery control the emotional center; audio shapes rhythm and texture only.

The browser presents both choices. The selected path creates a normal append-only variation set.

## Caching, versioning, and audit trail

The cache key is a SHA-256 hash of the exact MP3 bytes plus sanitized lyric text.

- Same `collection_id` + same input hash returns the existing generation with `cache_hit=true` and does not rerun librosa, NLP, or OpenAI.
- Changed audio or changed sanitized lyrics creates `version + 1` under the same collection.
- Old `Generation` rows and all associated `VariationSet` and `Variation` rows remain immutable and browsable.
- Regeneration does not create a new input version; it appends `set_number + 1` to the existing version.
- Every attempt and state transition is stored in `audit_events`, including retry attempt number, outcome, error code, HTTP status, and OpenAI request ID where available.

Stored images are downloaded immediately from the provider if a temporary URL is returned, normalized with Pillow, and persisted locally. The app never relies on expiring provider URLs.

## Retry and partial-failure behavior

Each audio-analysis, lyrics-analysis, and individual image-generation position uses exponential retry:

```text
base_delay × 2^(attempt - 1)
```

The default is three attempts. Typed errors decide retryability:

- Retry: timeouts/network errors, HTTP `429`, HTTP `5xx`, decoder/NLP transient failures
- Do not retry: HTTP `401/403`, invalid image request `400/422`, invalid user input

Analysis is committed after each successful source. If image generation fails afterward, the complete structured analysis stays available. If two of four images succeeded, the variation set is marked `partial`; the retry route fills positions three and four in the same set without replacing positions one and two.

## Image sizing

The provider is requested at `1024×1024`, because that size is supported by GPT Image and DALL·E 3. Every result is decoded and passed through `PIL.ImageOps.fit(..., (1000, 1000))`, then stored as PNG. API metadata and tests verify `width=1000`, `height=1000`.

## Tests

Run:

```bash
make test
```

The suite makes no OpenAI calls. It currently contains **19 passing tests** covering:

- MP3-only input
- lyrics-only input
- combined equal weighting
- conflict detection and both-choice flow
- invalid file rejection
- exact cache reuse without image API calls
- 3–5 variations, selection, and download
- fresh regeneration while preserving old sets
- version history after modified inputs
- automatic analysis retry and audit events
- OpenAI `401`, `429`, `503`, and `400` mapping
- partial generation and missing-position retry
- static browser UI serving
- Alembic migration viability

The executed verification commands for this deliverable were:

```bash
cd backend && PYTHONPATH=. pytest
# 19 passed

DATABASE_URL=sqlite:////tmp/album-cover-migration-test.db alembic upgrade head
# upgrade completed

python -m compileall -q backend/app
node --check frontend/app.js
```

## Production hardening notes

The included implementation is complete for a single-node service. Before high-volume deployment:

- use PostgreSQL and a real job queue such as Redis/RQ, Celery, or a managed queue instead of FastAPI in-process background tasks
- move `LocalStorage` to S3-compatible object storage and use signed download URLs
- add request-level rate limiting and per-tenant quotas when authentication is introduced
- run malware scanning on uploads if files come from untrusted public users
- add lifecycle/retention rules for original MP3s and generated images
- record OpenAI usage/cost metadata if billing or quotas are needed

Authentication, image editing, and a cross-user gallery are intentionally out of scope.
