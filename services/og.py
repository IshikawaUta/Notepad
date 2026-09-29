import textwrap
from io import BytesIO
from pathlib import Path

W, H = 1200, 630
BG = "#14161d"
FG = "#f5f6fa"
MUTED = "#9aa2b5"

_PROJECT_FONTS = Path(__file__).resolve().parent.parent / "static" / "fonts"
_SYSTEM_DIRS = (
    Path("/usr/share/fonts/truetype/dejavu"),
    Path("/usr/share/fonts/dejavu"),
    Path("/usr/share/fonts/TTF"),
    Path("/usr/local/share/fonts"),
)


def load_font(name: str, size: int):
    from PIL import ImageFont

    for path in [_PROJECT_FONTS / name] + [d / name for d in _SYSTEM_DIRS]:
        if path.is_file():
            try:
                return ImageFont.truetype(str(path), size)
            except Exception:
                continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def generate_note_card(title: str, site_name: str, accent: str = "#6366f1") -> bytes:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, 16, H], fill=accent)
    draw.rectangle([16, H - 120, W, H - 116], fill="#232734")

    max_w = W - 180
    size = 64
    title_font = load_font("DejaVuSans-Bold.ttf", size)
    lines = _wrap(draw, title, title_font, max_w)
    while len(lines) > 4 and size > 36:
        size -= 6
        title_font = load_font("DejaVuSans-Bold.ttf", size)
        lines = _wrap(draw, title, title_font, max_w)

    line_h = int(size * 1.32)
    block_h = line_h * len(lines)
    y = (H - 120 - block_h) // 2
    for ln in lines:
        draw.text((90, y), ln, font=title_font, fill=FG)
        y += line_h

    site_font = load_font("DejaVuSans.ttf", 30)
    draw.text((90, H - 88), site_name, font=site_font, fill=MUTED)

    buf = BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _wrap(draw, text: str, font, max_w: int) -> list[str]:
    words = str(text).split()
    if not words:
        return [""]
    lines: list[str] = []
    cur = ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > 4:
        joined = " ".join(words)
        wrapped = textwrap.wrap(joined, width=max(8, len(joined) // 4))
        lines = wrapped[:4]
    return lines
