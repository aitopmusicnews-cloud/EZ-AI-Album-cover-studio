from PIL import Image

from app.storage import LocalStorage
from app.typography import choose_typography_style, typography_direction


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
