"""Compila Zubel: ejecutable con PyInstaller y, si Inno Setup está disponible, el instalador.

Uso:
    python tools/build.py            # dist/Zubel/ + installer/Output/Zubel-<versión>-setup.exe
    python tools/build.py --no-installer
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from zubel import __version__  # noqa: E402


def find_iscc() -> str | None:
    found = shutil.which("iscc") or shutil.which("ISCC")
    if found:
        return found
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"),
                 os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs")):
        if base:
            candidate = Path(base) / "Inno Setup 6" / "ISCC.exe"
            if candidate.exists():
                return str(candidate)
    return None


def run(cmd: list[str]) -> None:
    print(">", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def main() -> int:
    if not (ROOT / "assets" / "zubel.ico").exists():
        run([sys.executable, "tools/make_icon.py"])
    run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "zubel.spec"])
    print(f"\nEjecutable listo en {ROOT / 'dist' / 'Zubel'}")

    if "--no-installer" in sys.argv or sys.platform != "win32":
        return 0
    iscc = find_iscc()
    if not iscc:
        print("Inno Setup no encontrado: se omite el instalador (https://jrsoftware.org/isinfo.php).")
        return 0
    run([iscc, f"/DAppVersion={__version__}", str(ROOT / "installer" / "zubel.iss")])
    print(f"Instalador listo en {ROOT / 'installer' / 'Output'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
