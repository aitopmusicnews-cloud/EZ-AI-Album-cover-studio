from __future__ import annotations

from dataclasses import replace
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import Settings
from app.errors import AnalysisError
from app.image_client import GeneratedImage
from app.prompts import variation_prompt
from app.main import AppDependencies, create_app


POSITIVE_AUDIO = {
    "tempo_bpm": 128.0,
    "energy": 0.78,
    "loudness_dbfs": -10.0,
    "spectral": {
        "centroid_hz": 3100.0,
        "bandwidth_hz": 2200.0,
        "rolloff_hz": 6500.0,
        "flatness": 0.08,
        "zero_crossing_rate": 0.11,
        "contrast": [1.0] * 7,
        "bass_ratio": 0.24,
    },
    "key": "C",
    "scale": "major",
    "key_confidence": 0.8,
    "dominant_frequencies_hz": [65.4, 130.8, 261.6],
    "inferred_genre": "electronic / dance",
    "style_tags": ["synthetic", "kinetic", "club-oriented"],
    "mood": {"label": "uplifting and energetic", "valence": 0.8, "energy": 0.78},
    "duration_seconds_analyzed": 60.0,
    "sample_rate": 22050,
}

NEGATIVE_LYRICS = {
    "mood": {"label": "melancholic", "valence": -0.8, "energy": 0.35},
    "themes": ["loss and memory", "identity and reflection"],
    "tone": ["sadness"],
    "keywords": ["ghost", "ashes", "empty", "memory"],
    "imagery": ["ghost", "ashes"],
    "token_count": 20,
}

POSITIVE_LYRICS = {
    "mood": {"label": "hopeful", "valence": 0.2, "energy": 0.42},
    "themes": ["resilience and rebirth", "freedom and escape"],
    "tone": ["hope"],
    "keywords": ["rise", "light", "road", "dream"],
    "imagery": ["light", "road"],
    "token_count": 20,
}


class FakeAudioAnalyzer:
    def __init__(self, signal: dict[str, Any] | None = None, failures: int = 0):
        self.signal = signal or POSITIVE_AUDIO
        self.failures = failures
        self.calls = 0

    def analyze(self, path: str | Path) -> dict[str, Any]:
        self.calls += 1
        assert Path(path).exists()
        if self.calls <= self.failures:
            raise AnalysisError("temporary decoder failure")
        return self.signal


class FakeLyricsAnalyzer:
    def __init__(self, signal: dict[str, Any] | None = None, failures: int = 0):
        self.signal = signal or POSITIVE_LYRICS
        self.failures = failures
        self.calls = 0

    def analyze(self, text: str) -> dict[str, Any]:
        self.calls += 1
        assert text
        if self.calls <= self.failures:
            raise AnalysisError("temporary NLP failure")
        return self.signal


class FakeCreativeDirector:
    def __init__(self, failures: int = 0):
        self.failures = failures
        self.calls = 0
        self.previous_prompts_seen: list[list[str]] = []

    async def plan(
        self,
        *,
        base_brief,
        signal,
        count,
        creative_seed,
        title,
        artist,
        previous_prompts=None,
    ):
        from app.creative_director import ConceptPlan
        self.calls += 1
        self.previous_prompts_seen.append(list(previous_prompts or []))
        if self.calls <= self.failures:
            raise AnalysisError("temporary creative director failure")
        media = [
            "35mm documentary photograph",
            "tactile cut-paper collage",
            "hand-painted editorial illustration",
            "medium-format still-life photograph",
            "two-color screenprint sleeve",
        ]
        subjects = [
            "a solitary lyric-specific object",
            "two people caught in a candid gesture",
            "a symbolic natural form with no people",
            "hands performing a private ritual",
            "an abstracted practical arrangement of fabric and light",
        ]
        settings = [
            "open natural ground",
            "plain studio sweep",
            "tabletop practical set",
            "dark undefined interior",
            "weather-filled open space",
        ]
        cameras = [
            "wide low-angle frame",
            "overhead graphic crop",
            "tight macro detail",
            "off-center documentary frame",
            "long-distance silhouette frame",
        ]
        concepts = []
        for i in range(count):
            concepts.append({
                "name": f"Concept {self.calls}-{i+1}",
                "subject": subjects[i],
                "setting": settings[i],
                "action_or_symbol": f"song-specific action {self.calls}-{i+1}",
                "camera": cameras[i],
                "medium": media[i],
                "palette": f"distinct palette {self.calls}-{i+1}",
                "typography_zone": "clear lower-left zone away from faces",
                "image_prompt": f"Unique cover concept batch {self.calls} variation {i+1}; materially distinct subject, setting, medium and camera.",
            })
        return ConceptPlan(concepts, request_id=f"concept-{self.calls}")


class FakeImageClient:
    def __init__(self, failures: dict[int, Exception] | None = None):
        self.failures = failures or {}
        self.calls = 0
        self.prompts: list[str] = []

    async def generate(self, prompt: str, position: int) -> GeneratedImage:
        self.calls += 1
        self.prompts.append(variation_prompt(prompt, position))
        failure = self.failures.get(self.calls)
        if failure:
            raise failure
        image = Image.new(
            "RGB",
            (1024, 1024),
            ((position * 50) % 255, (self.calls * 30) % 255, 120),
        )
        output = BytesIO()
        image.save(output, format="PNG")
        return GeneratedImage(output.getvalue(), request_id=f"req-{self.calls}")


@pytest.fixture
def app_factory(tmp_path):
    clients: list[TestClient] = []

    def factory(
        *,
        audio_analyzer: Any | None = None,
        lyrics_analyzer: Any | None = None,
        image_client: Any | None = None,
        creative_director: Any | None = None,
        retry_attempts: int = 3,
    ):
        settings = Settings(
            database_url=f"sqlite:///{tmp_path / ('test-' + str(len(clients)) + '.db')}",
            storage_root=tmp_path / f"storage-{len(clients)}",
            retry_max_attempts=retry_attempts,
            retry_base_delay_seconds=0,
            openai_api_key="test-key",
        )
        audio = audio_analyzer or FakeAudioAnalyzer()
        lyrics = lyrics_analyzer or FakeLyricsAnalyzer()
        images = image_client or FakeImageClient()
        director = creative_director or FakeCreativeDirector()
        app = create_app(
            settings,
            AppDependencies(
                audio_analyzer=audio,
                lyrics_analyzer=lyrics,
                image_client=images,
                creative_director=director,
            ),
        )
        client = TestClient(app)
        client.__enter__()
        clients.append(client)
        return client, audio, lyrics, images

    yield factory

    for client in clients:
        client.__exit__(None, None, None)


@pytest.fixture
def mp3_bytes() -> bytes:
    return b"ID3" + b"\x00" * 4096
