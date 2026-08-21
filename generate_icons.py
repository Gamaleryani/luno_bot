"""
Generates PWA icon PNGs matching the dashboard's dark/amber palette: a
simple ascending-candlestick mark on a rounded dark square. Run once
(or whenever the palette changes) - output goes to static/.

Usage:
    python generate_icons.py
"""

from PIL import Image, ImageDraw

BG = (9, 12, 18)  # --bg (dark)
ACCENT = (219, 162, 94)  # --accent (dark theme)
POS = (62, 207, 142)  # --pos (dark theme)


def rounded_square(size: int, radius_pct: float = 0.22) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    radius = int(size * radius_pct)
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=BG)
    return img, draw


def draw_candles(draw: ImageDraw.ImageDraw, size: int):
    # three ascending candlesticks, evoking a price chart
    margin = size * 0.20
    usable = size - 2 * margin
    bar_w = usable * 0.16
    gap = usable * 0.14
    heights = [0.32, 0.52, 0.74]  # ascending, as fraction of usable height
    colors = [ACCENT, ACCENT, POS]
    baseline = size - margin

    x = margin
    for h_frac, color in zip(heights, colors):
        h = usable * h_frac
        top = baseline - h
        # body
        draw.rounded_rectangle([x, top, x + bar_w, baseline], radius=bar_w * 0.25, fill=color)
        # wick
        wick_w = max(2, bar_w * 0.18)
        wick_top = top - usable * 0.08
        draw.rectangle([x + bar_w / 2 - wick_w / 2, wick_top, x + bar_w / 2 + wick_w / 2, top], fill=color)
        x += bar_w + gap


def make_icon(size: int, path: str):
    img, draw = rounded_square(size)
    draw_candles(draw, size)
    img.save(path)
    print(f"Wrote {path} ({size}x{size})")


if __name__ == "__main__":
    make_icon(192, "static/icon-192.png")
    make_icon(512, "static/icon-512.png")
    make_icon(180, "static/apple-touch-icon.png")
