"""앱 아이콘 PNG 생성(외부 라이브러리 없이). 어두운 배경 + 확률 fan + 중앙값 선 + 캔들.

python scripts/make_icons.py
"""
import struct
import zlib
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parents[1] / "site" / "icons"


def png(path: Path, rgb: np.ndarray) -> None:
    h, w, _ = rgb.shape
    raw = b"".join(b"\x00" + rgb[y].astype(np.uint8).tobytes() for y in range(h))
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)  # noqa: E731
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def draw(size: int, safe: float = 1.0) -> np.ndarray:
    ss = 3
    n = size * ss
    y, x = np.mgrid[0:n, 0:n] / n  # 0~1
    # 아이콘 내부 좌표(마스커블은 가운데 안전영역으로 축소)
    u = (x - 0.5) / safe + 0.5
    v = (y - 0.5) / safe + 0.5
    img = np.zeros((n, n, 3))
    top, bot = np.array([22, 28, 46]), np.array([11, 15, 23])
    img[:] = (top * (1 - y[..., None]) + bot * y[..., None])
    ox, oy = 0.40, 0.555  # fan 출발점
    fan = np.array([155, 133, 255])
    dx = u - ox
    for spread, a in ((0.34, 0.20), (0.22, 0.30), (0.12, 0.45)):
        inside = (dx > 0) & (u < 0.86) & (np.abs(v - (oy - 0.10 * dx)) < spread * dx)
        img[inside] = img[inside] * (1 - a) + fan * a
    # 중앙값 선
    med = (dx > 0) & (u < 0.86) & (np.abs(v - (oy - 0.10 * dx)) < 0.0065)
    img[med] = np.array([200, 190, 255])
    # 캔들 3개 (빨강=상승, 파랑=하락)
    for cx, o, c, col in ((0.17, 0.66, 0.54, (255, 92, 108)), (0.26, 0.55, 0.62, (76, 141, 255)), (0.35, 0.62, 0.53, (255, 92, 108))):
        lo, hi = min(o, c), max(o, c)
        body = (np.abs(u - cx) < 0.032) & (v > lo) & (v < hi)
        wick = (np.abs(u - cx) < 0.007) & (v > lo - 0.05) & (v < hi + 0.05)
        img[body | wick] = np.array(col)
    return img.reshape(size, ss, size, ss, 3).mean(axis=(1, 3))


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    png(OUT / "apple-touch-icon.png", draw(180))
    png(OUT / "icon-192.png", draw(192))
    png(OUT / "icon-512.png", draw(512))
    png(OUT / "icon-512-maskable.png", draw(512, safe=0.8))
    print("ok", sorted(p.name for p in OUT.iterdir()))
