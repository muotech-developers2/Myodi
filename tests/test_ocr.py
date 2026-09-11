from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from processing.ocr import extract_matches_from_image


def create_synthetic_odds_image(path: Path):
    img = Image.new("RGB", (1400, 900), color=(230, 230, 230))
    draw = ImageDraw.Draw(img)

    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
    small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)

    rows = [
        {
            "y": 120,
            "home": "Aston Villa",
            "away": "Everton",
            "values": ["1.90", "3.43", "4.05", "1.75", "2.03"],
        },
        {
            "y": 220,
            "home": "West Ham",
            "away": "Londn Reds",
            "values": ["3.15", "3.71", "2.10", "1.67", "2.14"],
        },
    ]

    for row in rows:
        y = row["y"]
        draw.rectangle((80, y, 1280, y + 70), fill=(245, 245, 245), outline=(200, 200, 200), width=2)
        draw.text((110, y + 18), row["home"], fill=(20, 20, 20), font=font)
        draw.text((630, y + 18), "vs", fill=(80, 80, 80), font=small)
        draw.text((710, y + 18), row["away"], fill=(20, 20, 20), font=font)

        x_positions = [840, 920, 1000, 1080, 1160]
        for x, value in zip(x_positions, row["values"]):
            draw.text((x, y + 18), value, fill=(20, 20, 20), font=font)

    img.save(path)


def test_extract_matches_from_synthetic_drawing(tmp_path):
    image_path = tmp_path / "synthetic_odds.png"
    create_synthetic_odds_image(image_path)

    matches = extract_matches_from_image(str(image_path))

    assert len(matches) >= 1
    assert matches[0]["home_team"]
    assert matches[0]["away_team"]
    assert matches[0]["home_odds"] is not None
    assert matches[0]["draw_odds"] is not None
    assert matches[0]["away_odds"] is not None
    assert matches[0]["btts_yes"] is not None
    assert matches[0]["btts_no"] is not None
