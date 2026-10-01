"""Write nmos.ico (16-256 px PNG frames) with the standard library only: the plugin's icon (src/icon.ts, a one-stroke
N with a memory node) in white on the palette's black.

    python make_icon.py <out.ico> [<preview.png>]
"""

from __future__ import annotations

import struct
import sys
import zlib

BG = (0x0A, 0x0B, 0x0E)  # adapters/pocketrisu-plugin/src/palette.ts bg
FG = (0xF4, 0xF4, 0xF7)  # palette.ts textStrong
SIZES = (16, 20, 24, 32, 40, 48, 64, 256)
SS = 4  # supersampling per axis


def in_rounded_square(x: float, y: float, r: float = 0.22) -> bool:
    dx = max(abs(x - 0.5) - (0.5 - r), 0.0)
    dy = max(abs(y - 0.5) - (0.5 - r), 0.0)
    return dx * dx + dy * dy <= r * r


# src/icon.ts in its 24-unit viewBox: path "M6 19V5l12 14V9.5" (stroke 1.75, round caps and joins) and a dot
# at (18, 5.5), r 1.75.
STROKE = ((6, 19), (6, 5), (18, 19), (18, 9.5))
DOT, DOT_R = (18, 5.5), 1.75


def _segment_distance(px: float, py: float, a: tuple, b: tuple) -> float:
    (ax, ay), (bx, by) = a, b
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return ((px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2) ** 0.5


def in_glyph(x: float, y: float, size: int) -> bool:
    ux, uy = x * 24, y * 24
    # 1.75 units is about one pixel at 16 px; small sizes get a bolder stroke so the N stays legible.
    half = max(1.75, 1.5 * 24 / size) / 2
    if ((ux - DOT[0]) ** 2 + (uy - DOT[1]) ** 2) ** 0.5 <= DOT_R + (half - 0.875):
        return True
    return any(_segment_distance(ux, uy, a, b) <= half for a, b in zip(STROKE, STROKE[1:]))


def render(size: int) -> bytes:
    rows = []
    for py in range(size):
        row = bytearray([0])  # PNG filter: none
        for px in range(size):
            bg = fg = 0
            for sy in range(SS):
                for sx in range(SS):
                    x, y = (px + (sx + 0.5) / SS) / size, (py + (sy + 0.5) / SS) / size
                    if in_rounded_square(x, y):
                        bg += 1
                        fg += in_glyph(x, y, size)
            n = SS * SS
            if bg == 0:
                row += bytes(4)
                continue
            mix = fg / bg
            rgb = [round(BG[i] * (1 - mix) + FG[i] * mix) for i in range(3)]
            row += bytes(rgb + [round(255 * bg / n)])
        rows.append(bytes(row))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(b"".join(rows), 9))
            + chunk(b"IEND", b""))


def main() -> None:
    frames = [(s, render(s)) for s in SIZES]
    header = struct.pack("<HHH", 0, 1, len(frames))
    offset = 6 + 16 * len(frames)
    entries, blobs = b"", b""
    for size, png in frames:
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset + len(blobs))
        blobs += png
    with open(sys.argv[1], "wb") as f:
        f.write(header + entries + blobs)
    if len(sys.argv) > 2:
        with open(sys.argv[2], "wb") as f:
            f.write(dict(frames)[256])


if __name__ == "__main__":
    main()
