"""Generate favicon.ico / PNG variants by rasterizing static/favicon.svg via ImageMagick."""
from __future__ import annotations

import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SVG = ROOT / "static" / "favicon.svg"
OUT = ROOT / "static"


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    import zlib

    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def _read_png_rgba(path: Path) -> tuple[int, int, bytes]:
    """Return (w, h, raw RGBA bytes). Assumes filter=0 (ImageMagick may not)."""
    import zlib

    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos = 8
    idat = b""
    w = h = ct = None
    while pos < len(data):
        ln = struct.unpack(">I", data[pos : pos + 4])[0]
        tag = data[pos + 4 : pos + 8]
        chunk = data[pos + 8 : pos + 8 + ln]
        pos += 12 + ln
        if tag == b"IHDR":
            w, h, bit, ct = struct.unpack(">IIBB", chunk[:10])
            if bit != 8 or ct not in (2, 6):
                raise ValueError(f"unsupported PNG ct={ct} bit={bit}")
        elif tag == b"IDAT":
            idat += chunk
        elif tag == b"IEND":
            break
    raw = zlib.decompress(idat)
    bpp = 4 if ct == 6 else 3
    stride = w * bpp

    def paeth(a: int, b: int, c: int) -> int:
        p = a + b - c
        pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
        if pa <= pb and pa <= pc:
            return a
        if pb <= pc:
            return b
        return c

    prev = bytearray(stride)
    out = bytearray(w * h * 4)
    i = 0
    for y in range(h):
        f = raw[y * (1 + stride)]
        scan = bytearray(raw[y * (1 + stride) + 1 : (y + 1) * (1 + stride)])
        if f == 1:
            for j in range(stride):
                left = scan[j - bpp] if j >= bpp else 0
                scan[j] = (scan[j] + left) & 255
        elif f == 2:
            for j in range(stride):
                scan[j] = (scan[j] + prev[j]) & 255
        elif f == 3:
            for j in range(stride):
                left = scan[j - bpp] if j >= bpp else 0
                scan[j] = (scan[j] + ((left + prev[j]) // 2)) & 255
        elif f == 4:
            for j in range(stride):
                left = scan[j - bpp] if j >= bpp else 0
                up = prev[j]
                ul = prev[j - bpp] if j >= bpp else 0
                scan[j] = (scan[j] + paeth(left, up, ul)) & 255
        prev = scan
        for x in range(w):
            if ct == 6:
                out[i : i + 4] = scan[x * 4 : x * 4 + 4]
            else:
                out[i] = scan[x * 3]
                out[i + 1] = scan[x * 3 + 1]
                out[i + 2] = scan[x * 3 + 2]
                out[i + 3] = 255
            i += 4
    return w, h, bytes(out)


def write_opaque_png(path: Path, w: int, h: int, rgba: bytes) -> None:
    """Write PNG with alpha forced to 255 (fully opaque square)."""
    import zlib

    raw = bytearray()
    for y in range(h):
        raw.append(0)
        row = bytearray(rgba[y * w * 4 : (y + 1) * w * 4])
        for x in range(w):
            row[x * 4 + 3] = 255
        raw.extend(row)
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + _png_chunk(b"IEND", b"")
    )
    path.write_bytes(png)


def rasterize(size: int) -> tuple[int, int, bytes]:
    convert = shutil.which("magick") or shutil.which("convert")
    if not convert:
        raise RuntimeError("ImageMagick (convert/magick) not found")
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / f"icon-{size}.png"
        # Force 8-bit RGBA so our PNG reader can process it
        cmd = [
            convert,
            str(SVG),
            "-background",
            "#007acc",
            "-alpha",
            "remove",
            "-alpha",
            "off",
            "-density",
            "300",
            "-resize",
            f"{size}x{size}",
            "-gravity",
            "center",
            "-extent",
            f"{size}x{size}",
            "-type",
            "TrueColorAlpha",
            "-depth",
            "8",
            "-define",
            "png:color-type=6",
            "-define",
            "png:bit-depth=8",
            str(out),
        ]
        if Path(convert).name == "magick":
            # magick needs no separate 'convert' subcommand for this form
            pass
        subprocess.run(cmd, check=True, capture_output=True)
        # PNG8 may drop alpha; re-read and force opaque RGBA rewrite
        w, h, rgba = _read_png_rgba(out)
        write_opaque_png(out, w, h, rgba)
        return w, h, out.read_bytes()


def ico_from_pngs(images: list[tuple[int, bytes]]) -> bytes:
    count = len(images)
    header = struct.pack("<HHH", 0, 1, count)
    entries = b""
    data = b""
    offset = 6 + 16 * count
    for size, png in images:
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset)
        data += png
        offset += len(png)
    return header + entries + data


def main() -> None:
    if not SVG.is_file():
        raise SystemExit(f"missing {SVG}")

    # 16/32 written for <link>; 48 only embedded in ICO (no standalone file)
    pngs: list[tuple[int, bytes]] = []
    for s in (16, 32, 48):
        w, h, png = rasterize(s)
        pngs.append((s, png))
        if s in (16, 32):
            p = OUT / f"favicon-{s}.png"
            p.write_bytes(png)
            print(f"wrote {p} ({w}x{h}, {len(png)}B)")

    w, h, apple_png = rasterize(180)
    apple = OUT / "apple-touch-icon.png"
    apple.write_bytes(apple_png)
    print(f"wrote {apple} ({w}x{h}, {len(apple_png)}B)")

    ico = ico_from_pngs(pngs)
    ico_path = OUT / "favicon.ico"
    ico_path.write_bytes(ico)
    print(f"wrote {ico_path} ({len(ico)}B)")

    root_ico = ROOT / "favicon.ico"
    root_ico.write_bytes(ico)
    print(f"wrote {root_ico} ({len(ico)}B)")


if __name__ == "__main__":
    main()
