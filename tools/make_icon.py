"""Genera assets/zubel.ico (multi-tamaño) y assets/zubel.png a partir del logo dibujado en código."""
from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QBuffer, QByteArray, QIODevice  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from zubel.ui.icons import app_icon_pixmap  # noqa: E402

SIZES = [16, 24, 32, 48, 64, 128, 256]


def png_bytes(size: int) -> bytes:
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    app_icon_pixmap(size).save(buf, "PNG")
    return bytes(data.data())


def main() -> None:
    QGuiApplication(sys.argv)
    out = ROOT / "assets"
    out.mkdir(exist_ok=True)
    images = [png_bytes(s) for s in SIZES]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries = b""
    for size, img in zip(SIZES, images):
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(img), offset)
        offset += len(img)
    (out / "zubel.ico").write_bytes(header + entries + b"".join(images))
    app_icon_pixmap(512).save(str(out / "zubel.png"))
    print("Iconos generados en", out)


if __name__ == "__main__":
    main()
