"""Build the alpha lesson's cover plate from the original, pre-icon desktop-pet drawing."""

from pathlib import Path

from PIL import Image, ImageDraw

PROJECT = Path(__file__).resolve().parents[1]
ORIGINAL = PROJECT / "assets/whale-pet-front.png"


def render() -> None:
    width, height = 1920, 1080
    plate = Image.new("RGB", (width, height), "#c4efe8")
    draw = ImageDraw.Draw(plate)
    tile = 57
    for y in range(0, height, tile):
        for x in range(0, width, tile):
            warm = x + y * 0.19 > 908
            light = (x // tile + y // tile) % 2 == 0
            color = ("#ffdbaf" if light else "#f7ca9e") if warm else ("#d8f0e8" if light else "#c2e6de")
            draw.rectangle((x, y, x + tile - 1, y + tile - 1), fill=color)

    with Image.open(ORIGINAL) as original:
        # One scalar maps both axes. The plate and the two exports crop the surrounding space.
        scale = 1.83
        left = 684 - original.width * scale / 2
        top = 52
        overlay = original.convert("RGBA").transform(
            plate.size,
            Image.Transform.AFFINE,
            (1 / scale, 0, -left / scale, 0, 1 / scale, -top / scale),
            Image.Resampling.BICUBIC,
        )
        plate.paste(overlay, mask=overlay.getchannel("A"))
    plate.save(PROJECT / "assets/cover-base.jpg", quality=97, subsampling=0)


if __name__ == "__main__":
    render()
