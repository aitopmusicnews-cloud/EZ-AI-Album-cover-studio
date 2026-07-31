from __future__ import annotations

import pytest

from app.errors import (
    OpenAIAuthenticationError,
    OpenAIRateLimitError,
    OpenAIServiceError,
)
from conftest import (
    FakeAudioAnalyzer,
    FakeImageClient,
    FakeLyricsAnalyzer,
    NEGATIVE_LYRICS,
    POSITIVE_AUDIO,
    POSITIVE_LYRICS,
)


def create(
    client,
    *,
    collection_id="collection_test",
    audio=None,
    lyrics=None,
    count=4,
    mood_path="auto",
    title=None,
    artist=None,
    parental_advisory=False,
):
    files = {}
    if audio is not None:
        files["audio"] = ("song.mp3", audio, "audio/mpeg")
    data = {
        "collection_id": collection_id,
        "lyrics_text": lyrics or "",
        "variation_count": str(count),
        "mood_path": mood_path,
        "run_async": "false",
        "title": title or "",
        "artist": artist or "",
        "parental_advisory": "true" if parental_advisory else "false",
    }
    return client.post("/api/generations", data=data, files=files)


def test_mp3_only_generates_three_variations(app_factory, mp3_bytes):
    client, audio, lyrics, images = app_factory()
    response = create(client, audio=mp3_bytes, count=3)
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "complete"
    assert body["has_audio"] is True
    assert body["has_lyrics"] is False
    assert body["analysis"]["audio"]["tempo_bpm"] == 128.0
    assert len(body["variation_sets"][0]["variations"]) == 3
    assert audio.calls == 1
    assert lyrics.calls == 0
    assert images.calls == 3


def test_lyrics_only_generates_variations(app_factory):
    client, audio, lyrics, images = app_factory()
    response = create(client, lyrics="We rise into the light and dream beyond the road", count=4)
    body = response.json()
    assert response.status_code == 201
    assert body["status"] == "complete"
    assert body["has_audio"] is False
    assert body["has_lyrics"] is True
    assert body["analysis"]["lyrics"]["themes"]
    assert audio.calls == 0
    assert lyrics.calls == 1
    assert images.calls == 4


def test_combined_inputs_are_equal_weighted(app_factory, mp3_bytes):
    client, _, _, _ = app_factory(
        audio_analyzer=FakeAudioAnalyzer(POSITIVE_AUDIO),
        lyrics_analyzer=FakeLyricsAnalyzer(POSITIVE_LYRICS),
    )
    response = create(
        client,
        audio=mp3_bytes,
        lyrics="Rise into the light and carry the dream",
        count=3,
    )
    body = response.json()
    signal = body["analysis"]["structured_signal"]
    assert signal["source_weights"] == {"audio": 0.5, "lyrics": 0.5}
    assert signal["mood"]["valence"] == pytest.approx(0.5)
    assert body["variation_sets"][0]["mood_path"] == "blend"


def test_conflict_requires_choice_then_supports_audio_path(app_factory, mp3_bytes):
    client, _, _, images = app_factory(
        audio_analyzer=FakeAudioAnalyzer(POSITIVE_AUDIO),
        lyrics_analyzer=FakeLyricsAnalyzer(NEGATIVE_LYRICS),
    )
    response = create(
        client,
        audio=mp3_bytes,
        lyrics="Ghosts and ashes fill the empty room",
        count=3,
    )
    body = response.json()
    assert body["status"] == "needs_mood_choice"
    assert body["conflict"]["detected"] is True
    assert "audio_path" in body["conflict"]
    assert "lyrics_path" in body["conflict"]
    assert images.calls == 0

    chosen = client.post(
        f"/api/generations/{body['id']}/generate",
        json={"mood_path": "audio", "variation_count": 3, "run_async": False},
    )
    chosen_body = chosen.json()
    assert chosen.status_code == 200
    assert chosen_body["status"] == "complete"
    assert chosen_body["variation_sets"][0]["mood_path"] == "audio"
    assert images.calls == 3


def test_invalid_non_mp3_rejected(app_factory):
    client, *_ = app_factory()
    response = client.post(
        "/api/generations",
        data={"collection_id": "collection_test", "run_async": "false"},
        files={"audio": ("song.wav", b"RIFF-not-mp3", "audio/wav")},
    )
    assert response.status_code == 415
    assert "MP3" in response.json()["detail"]


def test_same_input_returns_cached_variations_without_openai(app_factory, mp3_bytes):
    client, _, _, images = app_factory()
    first = create(client, audio=mp3_bytes, lyrics="Rise into light", count=3).json()
    calls_after_first = images.calls
    second_response = create(client, audio=mp3_bytes, lyrics="Rise into light", count=5)
    second = second_response.json()
    assert second_response.status_code == 200
    assert second["cache_hit"] is True
    assert second["id"] == first["id"]
    assert images.calls == calls_after_first
    assert len(second["variation_sets"][0]["variations"]) == 3


def test_variations_can_be_selected_and_downloaded(app_factory):
    client, *_ = app_factory()
    body = create(client, lyrics="Rise into light", count=5).json()
    assert len(body["variation_sets"][0]["variations"]) == 5
    variation = body["variation_sets"][0]["variations"][2]
    selected = client.post(f"/api/variations/{variation['id']}/select").json()
    assert selected["selected_variation_id"] == variation["id"]
    assert selected["variation_sets"][0]["variations"][2]["selected"] is True
    download = client.get(variation["download_url"])
    assert download.status_code == 200
    assert download.headers["content-type"] == "image/png"
    assert download.content.startswith(b"\x89PNG")


def test_regeneration_adds_fresh_set_and_preserves_original(app_factory):
    client, _, _, images = app_factory()
    original = create(client, lyrics="Rise into light", count=3).json()
    old_ids = {v["id"] for v in original["variation_sets"][0]["variations"]}
    regenerated = client.post(
        f"/api/generations/{original['id']}/regenerate",
        json={"mood_path": "lyrics", "variation_count": 4, "run_async": False},
    ).json()
    assert len(regenerated["variation_sets"]) == 2
    assert {v["id"] for v in regenerated["variation_sets"][0]["variations"]} == old_ids
    assert len(regenerated["variation_sets"][1]["variations"]) == 4
    # A fresh set must rotate the visual DNA rather than sending OpenAI the
    # exact same base prompt again.
    assert regenerated["variation_sets"][0]["prompt"] != regenerated["variation_sets"][1]["prompt"]
    assert images.calls == 7


def test_modified_input_creates_new_version_and_history_preserves_old(app_factory):
    client, *_ = app_factory()
    first = create(client, lyrics="First lyric version", count=3).json()
    second = create(client, lyrics="Second lyric version changed", count=3).json()
    assert first["id"] != second["id"]
    assert first["version"] == 1
    assert second["version"] == 2
    history = client.get("/api/collections/collection_test/versions").json()
    assert [item["version"] for item in history["versions"]] == [2, 1]
    assert len(history["versions"][1]["variation_sets"][0]["variations"]) == 3



def test_release_metadata_is_stored_and_composited(app_factory):
    client, *_ = app_factory()
    body = create(
        client,
        lyrics="Night city lights and thunder",
        count=3,
        title="Midnight Drive",
        artist="The Artist Cut",
        parental_advisory=True,
    ).json()
    assert body["title"] == "Midnight Drive"
    assert body["artist"] == "The Artist Cut"
    assert body["parental_advisory"] is True
    prompt = body["variation_sets"][0]["prompt"]
    assert "Do not draw words or lettering" in prompt
    assert "lower corner" in prompt
    download = client.get(body["variation_sets"][0]["variations"][0]["download_url"])
    assert download.status_code == 200
    from io import BytesIO
    from PIL import Image
    image = Image.open(BytesIO(download.content)).convert("RGB")
    assert image.size == (3000, 3000)
    # The exact advisory is composited in the lower-right; this area differs from
    # the fake image provider's flat source color.
    assert len(set(image.crop((2190, 2490, 2910, 2910)).getdata())) > 4


def test_release_metadata_change_creates_new_version(app_factory):
    client, *_ = app_factory()
    first = create(client, lyrics="same lyrics", count=3, title="First Title").json()
    second = create(client, lyrics="same lyrics", count=3, title="Second Title").json()
    assert first["version"] == 1
    assert second["version"] == 2
    assert first["id"] != second["id"]


def test_audio_analysis_is_retried_and_eventually_succeeds(app_factory, mp3_bytes):
    flaky_audio = FakeAudioAnalyzer(failures=1)
    client, _, _, _ = app_factory(audio_analyzer=flaky_audio)
    body = create(client, audio=mp3_bytes, count=3).json()
    assert body["status"] == "complete"
    assert flaky_audio.calls == 2
    events = [
        event for event in body["audit_events"] if event["step"] == "audio_analysis"
    ]
    assert [(event["attempt"], event["outcome"]) for event in events] == [
        (1, "started"),
        (1, "failed"),
        (2, "started"),
        (2, "succeeded"),
    ]


@pytest.mark.parametrize(
    "error,expected_calls,expected_code",
    [
        (OpenAIRateLimitError("rate limited", status_code=429), 3, "openai_rate_limit"),
        (OpenAIServiceError("unavailable", status_code=503), 3, "openai_service_unavailable"),
        (OpenAIAuthenticationError("bad key", status_code=401), 1, "openai_authentication_error"),
    ],
)
def test_openai_errors_surface_cleanly(app_factory, error, expected_calls, expected_code):
    images = FakeImageClient(failures={index: error for index in range(1, expected_calls + 1)})
    client, _, _, _ = app_factory(image_client=images)
    body = create(client, lyrics="Rise into light", count=3).json()
    assert body["status"] == "image_failed"
    assert body["last_error"]["code"] == expected_code
    assert images.calls == expected_calls
    assert body["analysis"] is not None


def test_partial_failure_can_retry_only_missing_images(app_factory):
    images = FakeImageClient(
        failures={3: OpenAIServiceError("temporary outage", status_code=503)}
    )
    client, _, _, _ = app_factory(image_client=images, retry_attempts=1)
    first = create(client, lyrics="Rise into light", count=4).json()
    assert first["status"] == "partial"
    assert len(first["variation_sets"][0]["variations"]) == 2

    retried = client.post(
        f"/api/generations/{first['id']}/retry?run_async=false"
    ).json()
    assert retried["status"] == "complete"
    assert len(retried["variation_sets"]) == 1
    assert len(retried["variation_sets"][0]["variations"]) == 4


def test_no_build_frontend_is_served(app_factory):
    client, *_ = app_factory()
    response = client.get("/")
    assert response.status_code == 200
    assert "EZ AI Album Cover Studio" in response.text
    assert "/assets/ez-album-cover-logo.png" in response.text
    assert "/assets/favicon.ico" in response.text
    assert 'id="release-title"' in response.text
    assert 'id="artist-name"' in response.text
    assert 'id="parental-advisory"' in response.text

    logo = client.get("/assets/ez-album-cover-logo.png")
    assert logo.status_code == 200
    assert logo.headers["content-type"] == "image/png"

    favicon = client.get("/assets/favicon.ico")
    assert favicon.status_code == 200
    assert favicon.headers["content-type"] in {"image/vnd.microsoft.icon", "image/x-icon"}


def test_creative_director_makes_each_image_prompt_materially_different(app_factory):
    client, _, _, images = app_factory()
    body = create(client, lyrics="broken promises under summer rain", count=5).json()
    assert body["status"] == "complete"
    assert len(images.prompts) == 5
    assert len(set(images.prompts)) == 5
    assert all("CREATIVE DIRECTOR CONCEPT" in p for p in images.prompts)
    assert any("cut-paper collage" in p for p in images.prompts)
    assert any("screenprint sleeve" in p for p in images.prompts)


def test_fresh_variations_tell_creative_director_about_previous_set(app_factory):
    from conftest import FakeCreativeDirector

    director = FakeCreativeDirector()
    client, _, _, images = app_factory(creative_director=director)
    first = create(client, lyrics="memory turns into rain", count=3).json()
    second = client.post(
        f"/api/generations/{first['id']}/regenerate",
        json={"mood_path": "lyrics", "variation_count": 3, "run_async": False},
    ).json()
    assert len(second["variation_sets"]) == 2
    assert director.calls == 2
    assert director.previous_prompts_seen[0] == []
    assert director.previous_prompts_seen[1]
    assert "Concept 1-1" in director.previous_prompts_seen[1][0]
    first_batch = images.prompts[:3]
    second_batch = images.prompts[3:]
    assert set(first_batch).isdisjoint(set(second_batch))
