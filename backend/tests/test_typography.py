from PIL import Image, ImageFont

from app.font_catalog import all_bundled_font_paths, bundled_font_candidates
from app.storage import LocalStorage
from app.typography import (
    choose_typography_style,
    split_typography_token,
    typography_direction,
    typography_idea_capacity,
)


def test_typography_styles_are_genre_aware_and_vary_across_set():
    rap = {"inferred_genre": "hip-hop / trap"}
    country = {"inferred_genre": "country / americana"}
    rap_styles = [choose_typography_style(rap, i) for i in range(1, 6)]
    country_styles = [choose_typography_style(country, i) for i in range(1, 6)]
    assert len(set(rap_styles)) == 5
    assert len(set(country_styles)) == 5
    assert rap_styles != country_styles
    assert "street_script" in rap_styles
    assert "heritage_script" in country_styles


def test_typography_direction_describes_creative_lettering_not_plain_block_text():
    direction = typography_direction({"inferred_genre": "R&B / soul"}, 1)
    assert "script" in direction
    assert "block" not in direction


def test_seeded_typography_profiles_do_not_restart_the_same_sequence():
    signal = {"inferred_genre": "hip-hop / trap", "mood": {"energy": 0.8}}
    first_set = [
        choose_typography_style(signal, position, creative_seed="variation-set-a")
        for position in range(1, 6)
    ]
    fresh_set = [
        choose_typography_style(signal, position, creative_seed="variation-set-b")
        for position in range(1, 6)
    ]

    assert len({split_typography_token(token)[0] for token in first_set}) == 5
    assert first_set != fresh_set
    assert all("::" in token for token in first_set)


def test_typography_catalog_provides_hundreds_of_design_combinations():
    assert typography_idea_capacity() >= 500


def test_every_registered_commercial_font_is_present_and_loadable():
    paths = all_bundled_font_paths()
    assert len(paths) >= 25
    for path in paths:
        assert path.is_file(), path
        assert ImageFont.truetype(str(path), size=40)


def test_bundled_fonts_lead_aws_system_fallbacks_and_change_with_seed():
    first = bundled_font_candidates("script", "luxury_script::release-a")
    second = bundled_font_candidates("script", "luxury_script::release-b")
    assert first
    assert first != second
    assert "/assets/fonts/" in first[0]


def test_typography_palette_changes_with_release_seed():
    source = Image.new("RGB", (1000, 1000), (30, 35, 45))
    first = LocalStorage._apply_release_text(
        source, title="Color Theory", artist="EZ AI", parental_advisory=False,
        typography_style="luxury_script::palette-a",
    )
    second = LocalStorage._apply_release_text(
        source, title="Color Theory", artist="EZ AI", parental_advisory=False,
        typography_style="luxury_script::palette-b",
    )
    assert first.tobytes() != second.tobytes()


def test_creative_lower_third_treatment_remains_face_safe():
    source = Image.new("RGB", (1000, 1000), (51, 61, 71))
    rendered = LocalStorage._apply_release_text(
        source,
        title="Cold Signal",
        artist="Night Vault",
        parental_advisory=False,
        position=3,
        typography_style="marker_signature",
    )
    # Portrait/face region is untouched while the lower third receives lettering.
    assert set(rendered.crop((180, 120, 820, 560)).getdata()) == {(51, 61, 71)}
    assert len(set(rendered.crop((60, 610, 940, 930)).getdata())) > 1
