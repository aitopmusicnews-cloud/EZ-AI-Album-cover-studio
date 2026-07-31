# EZ AI Album Cover Studio

A complete, self-contained album-cover generation pipeline for a new project. Users can upload an MP3, lyrics, or both; the backend extracts audio and lyric signals, detects mood conflicts, converts those signals into visual art direction, creates 3–5 OpenAI image variations, normalizes every image to exactly **3000×3000 PNG**, and stores a versioned audit trail.

The stack is deliberately small and Intel-Mac friendly:

- **FastAPI** API and background jobs
- **SQLAlchemy + SQLite** by default, with Alembic migrations
- **librosa** for MP3/music analysis
- Lightweight in-process lyrics NLP with no model download
- **Gemini** independent creative-director/prompt-enhancement stage
- **OpenAI Image API** renderer supporting `gpt-image-1`, `gpt-image-2`, and legacy `dall-e-3`
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
- 3–5 independently art-directed album-cover concepts per variation set, using distinct cinematic, narrative, classic-sleeve, mixtape/poster, and alternate-story archetypes
- Genre-specific real-world cover direction (rap/mixtape, R&B, Americana/country, rock, pop, electronic, ambient) instead of a generic surreal-art default
- Anti-repetition prompt guardrails that explicitly avoid cracked-statue / fragmented-face AI clichés unless the song itself calls for them
- Exact locally composited release typography with five cover-style layouts, plus optional Parental Advisory placement
- Exact 3000×3000 PNG normalization and immediate local persistence
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
│   │   ├── creative_director.py   # Gemini prompt enhancement / concept planning
│   │   ├── image_client.py        # OpenAI Image API adapter
│   │   ├── service.py             # pipeline, cache, retry, versioning
│   │   ├── models.py              # audit/version schema
│   │   └── routers/generations.py # API endpoints
│   ├── alembic/                   # production migrations
│   └── tests/                     # mocked provider/unit/integration tests
├── frontend/                      # no-build browser UI + branded assets
├── data/                          # SQLite DB and generated files
├── scripts/configure_gemini.py    # safe Gemini-key setup helper
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

For Intel macOS, the project pins `librosa==0.11.0`, `numba==0.61.2`, and `llvmlite==0.44.0` so pip can use the compatible x86_64 wheels rather than attempting a local LLVM build.

Edit `.env` and set both `OPENAI_API_KEY` and `GEMINI_API_KEY`. OpenAI renders artwork; Gemini independently invents/enhances the cover concepts. Absolute paths are safest for `DATABASE_URL`, `STORAGE_ROOT`, and `FRONTEND_ROOT`; the built-in defaults already resolve to this project’s `data/` and `frontend/` directories when those variables are omitted.

For a non-coder-friendly Gemini setup, run:

```bash
.venv/bin/python scripts/configure_gemini.py
```

The helper prompts for the key without echoing it to the screen and writes only to the ignored `.env` file. Do not put either API key in source code or commit `.env` to GitHub.

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


## Anti-repetition creative director

Image generation has intentionally separate providers. **Gemini is the prompt enhancer / creative director; OpenAI is only the image renderer.** Before any OpenAI image call, the backend sends the analyzed song signal to Gemini (`GEMINI_CONCEPT_MODEL`, default `gemini-3.6-flash`). Gemini returns 3–5 structured, mutually different cover concepts. Each concept contains a distinct subject, setting, action/symbol, camera language, medium, palette, typography-safe zone, and a complete image prompt.

The planner is specifically told not to behave like a template engine. Genre alone cannot inject cars, trucks, city streets, buildings, mansions, motels, gas stations, cracked statues, chrome masks, or other recurring AI-cover clichés. For 4–5 image sets, it must include at least one no-person concept and at least one non-conventional-photography medium. Recent concept sets are supplied to Gemini when the user requests **Fresh Variations**, so the next set must avoid the prior central subject, environment, composition, medium, dominant prop, and metaphor.

Gemini uses its own `GEMINI_API_KEY`; the OpenAI key is never sent to Google and the Gemini key is never sent to OpenAI. If Gemini is missing or temporarily unavailable, the pipeline logs the provider failure and falls back to the local deterministic diversity planner. It does **not** fall back to OpenAI for prompt enhancement. Set `USE_GEMINI_CREATIVE_DIRECTOR=false` to disable the Gemini stage.

## Environment variables

| Variable | Required | Default | Purpose |
|---|---:|---|---|
| `OPENAI_API_KEY` | Yes for real images | none | Server-side OpenAI credential; never sent to the browser |
| `OPENAI_IMAGE_MODEL` | No | `gpt-image-2` | Image API model; `gpt-image-1` and legacy `dall-e-3` are also supported |
| `OPENAI_IMAGE_QUALITY` | No | `medium` | GPT Image quality; maps to `standard`/`hd` for DALL·E 3 |
| `OPENAI_TIMEOUT_SECONDS` | No | `150` | Per-request image generation timeout |
| `GEMINI_API_KEY` | Yes for Gemini prompt enhancement | none | Server-side Google Gemini credential; never sent to OpenAI or the browser |
| `GEMINI_CONCEPT_MODEL` | No | `gemini-3.6-flash` | Gemini model used only for creative direction / prompt enhancement |
| `USE_GEMINI_CREATIVE_DIRECTOR` | No | `true` | Enable the independent Gemini concept-planning stage |
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
- `title`: optional album/single title (up to 200 characters)
- `artist`: optional artist name (up to 200 characters)
- `parental_advisory`: optional boolean; overlays an exact Parental Advisory label on final images
- `collection_id`: optional 8–64 character browser/session grouping ID
- `variation_count`: `3`, `4`, or `5`
- `mood_path`: normally `auto`
- `run_async`: normally `true`

MP3-only example:

```bash
curl -X POST http://127.0.0.1:8000/api/generations \
  -F 'collection_id=demo_collection_01' \
  -F 'audio=@song.mp3;type=audio/mpeg' \
  -F 'title=Midnight Drive' \
  -F 'artist=The Artist Cut' \
  -F 'parental_advisory=true' \
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

## Release metadata and exact typography

The browser form accepts an optional album/single **Title**, **Artist**, and **Parental Advisory** checkbox. These values are versioned inputs. The OpenAI prompt reserves calm title and advisory-safe zones but explicitly asks the image model not to draw words. After the 1024×1024 provider image is normalized to a 1000×1000 composition canvas, Pillow composites the exact title/artist text and optional `PARENTAL ADVISORY / EXPLICIT CONTENT` label, then the finished cover is upscaled to 3000×3000 for export. This avoids common generative-image spelling errors.

The result panel also shows the extracted signal (BPM, key/scale, energy, loudness, genre/style confidence, audio mood, lyric mood, themes, and keywords) so incorrect heuristic classifications are visible instead of hidden.

## Signal extraction and equal weighting

### Audio

`AudioAnalyzer` loads a maximum configured duration at 22.05 kHz mono, then computes:

- tempo from onset/beat tracking with half/double-tempo normalization and a confidence score
- RMS and dBFS-like loudness measured from the original decoded amplitude (not a normalized waveform), plus dynamic range
- spectral centroid, bandwidth, rolloff, flatness, contrast, and zero crossings
- low-frequency power ratio and five separated dominant FFT frequencies
- chroma-profile key and major/minor-scale correlation
- heuristic genre candidates/style tags with confidence
- a normalized mood `{label, valence, energy, confidence}`

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

## Album-cover art direction

The image prompt builder is intentionally biased toward **commercial music-cover photography and art direction**, not generic AI surrealism. Audio establishes pace, energy, tonality, and a broad genre family, but genre no longer injects stock locations or props. Lyric keywords and themes supply the concrete story clues. Transportation imagery and architecture-led compositions are blocked unless the lyrical signal explicitly earns them, so hip-hop does not automatically become a car/parking-garage cover and country does not automatically become a truck/roadside-building cover.

Each 3–5 image set rotates among lyric-symbol, documentary, tactile still-life, wide emotional scene, character/fashion, after-the-event, unexpected-viewpoint, minimal physical, energetic-human, intimate-detail, and practical-concept directions. The prompt explicitly rejects recurring cracked-statue, shattered-face, floating-fragment, cyber-mask, transportation, and architecture defaults unless those ideas are actually supported by the song.

The image model is still told **not to generate lettering**. The exact release title, artist name, and optional Parental Advisory label are rendered locally with Pillow after generation. The five variation positions use different typography layouts so the set reads more like professionally art-directed cover options rather than the same label pasted on every image.

## Caching, versioning, and audit trail

The cache key is a SHA-256 hash of the exact MP3 bytes, sanitized lyric text, release title, artist name, and parental-advisory choice.

- Same `collection_id` + same input hash returns the existing generation with `cache_hit=true` and does not rerun librosa, NLP, or OpenAI.
- Changed audio, lyrics, title, artist, or advisory choice creates `version + 1` under the same collection.
- Old `Generation` rows and all associated `VariationSet` and `Variation` rows remain immutable and browsable.
- Regeneration does not create a new input version; it appends `set_number + 1` to the existing version.
- Every attempt and state transition is stored in `audit_events`, including retry attempt number, outcome, error code, HTTP status, and provider request ID where available.

Stored images are downloaded immediately from the provider if a temporary URL is returned, normalized with Pillow, and persisted locally. The app never relies on expiring provider URLs. Title/artist text and the optional Parental Advisory label are rendered locally after AI generation, which keeps release text exact and prevents misspelled AI typography.


## Song-specific visual DNA and anti-repetition

The image prompt is not a fixed five-template sequence. Each immutable input version contributes its input hash to a **visual DNA** seed. The seed deterministically rotates subject strategy, song-derived scene premise, camera viewpoint, time/weather, image-making treatment, and layout. A fresh regeneration mixes in the next variation-set number, so regenerating the same song deliberately creates a new art-direction rotation while preserving the prior set.

The prompt also includes audio-to-visual cues derived from spectral balance and dynamics without exposing raw technical measurements to the image model. Lyrics contribute only a small number of concrete story clues. Human subjects are optional: visual-DNA combinations can use lyric symbols, tactile still-lifes, natural settings, distant silhouettes, hands/details, candid relationships, fashion-led characters, practical sets, or documentary action. Cars and buildings are not fallback subject categories.

Because identical uploads are intentionally cached, re-uploading the exact same inputs returns the existing historical result. Use **Fresh Variations** to create a new visual-DNA rotation for that same version.

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

The provider is requested at `1024×1024`, because that size is supported by GPT Image and DALL·E 3. Every result is decoded and passed through `PIL.ImageOps.fit(..., (1000, 1000))`, composites exact release typography, then performs a high-quality Lanczos upscale to exactly `3000×3000` before storing the PNG. API metadata and tests verify `width=3000`, `height=3000`.

## Tests

Run:

```bash
make test
```

The suite makes no live OpenAI or Gemini calls. It covers:

- MP3-only input
- lyrics-only input
- combined equal weighting
- conflict detection and both-choice flow
- invalid file rejection
- exact cache reuse without image API calls
- 3–5 variations, selection, and download
- fresh regeneration while preserving old sets and rotating visual DNA
- different songs receiving different visual DNA even when genre/mood are similar
- version history after modified inputs
- automatic analysis retry and audit events
- OpenAI `401`, `429`, `503`, and `400` mapping
- Gemini structured-output concept planning and `401`, `429`, `503` mapping
- Gemini as the default creative director while OpenAI remains the image renderer
- partial generation and missing-position retry
- release title/artist/advisory persistence and exact local image compositing
- metadata changes creating a new historical version
- real audio-amplitude regression test proving loudness/energy are not measured from a normalized waveform
- static browser UI serving
- Alembic migration viability

The executed verification commands for this deliverable were:

```bash
cd backend && PYTHONPATH=. pytest
# passing test count is printed by pytest

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


## Final image output

Every downloadable cover is an exact **1:1, 3000×3000 pixel PNG**. The OpenAI provider is requested at its supported square size, the artwork and exact typography are composed, and the final result is upscaled with Pillow Lanczos resampling to 3000×3000 for distribution-ready export.
