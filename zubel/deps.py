"""Gestión de dependencias externas: yt-dlp, ffmpeg y deno.

Todo se descarga desde los repositorios oficiales (última versión publicada)
y se guarda en ``paths.bin_dir()``; nada se instala de forma global.

* yt-dlp  → https://github.com/yt-dlp/yt-dlp/releases
* ffmpeg  → https://github.com/yt-dlp/FFmpeg-Builds/releases (builds recomendadas por yt-dlp)
* deno    → https://github.com/denoland/deno/releases (runtime JS que yt-dlp
            necesita para resolver los desafíos de YouTube)
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import tarfile
import tempfile
import threading
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from zubel import paths

USER_AGENT = "Zubel (+https://github.com/yt-dlp/yt-dlp)"
NO_WINDOW = 0x08000000 if paths.IS_WINDOWS else 0  # CREATE_NO_WINDOW

ProgressCb = Callable[[int, int], None]


class Cancelled(Exception):
    pass


def _machine() -> str:
    m = platform.machine().lower()
    if m in ("amd64", "x86_64", "x64"):
        return "x64"
    if m in ("arm64", "aarch64"):
        return "arm64"
    return m


@dataclass
class Component:
    key: str
    name: str
    description: str
    required: bool

    # -- rutas / urls -------------------------------------------------------
    def target(self) -> Path:
        return {
            "yt-dlp": paths.ytdlp_path,
            "ffmpeg": paths.ffmpeg_path,
            "deno": paths.deno_path,
        }[self.key]()

    def url(self) -> str | None:
        arch = _machine()
        if self.key == "yt-dlp":
            if paths.IS_WINDOWS:
                asset = "yt-dlp_arm64.exe" if arch == "arm64" else "yt-dlp.exe"
            elif paths.IS_MAC:
                asset = "yt-dlp_macos"
            else:
                asset = "yt-dlp_linux_aarch64" if arch == "arm64" else "yt-dlp_linux"
            return f"https://github.com/yt-dlp/yt-dlp/releases/latest/download/{asset}"
        if self.key == "ffmpeg":
            base = "https://github.com/yt-dlp/FFmpeg-Builds/releases/latest/download/"
            if paths.IS_WINDOWS:
                return base + ("ffmpeg-master-latest-winarm64-gpl.zip" if arch == "arm64"
                               else "ffmpeg-master-latest-win64-gpl.zip")
            if paths.IS_MAC:
                return None  # No hay builds oficiales; se usa el ffmpeg del sistema.
            return base + ("ffmpeg-master-latest-linuxarm64-gpl.tar.xz" if arch == "arm64"
                           else "ffmpeg-master-latest-linux64-gpl.tar.xz")
        if self.key == "deno":
            base = "https://github.com/denoland/deno/releases/latest/download/"
            if paths.IS_WINDOWS:
                return base + "deno-x86_64-pc-windows-msvc.zip"  # funciona emulado en ARM
            if paths.IS_MAC:
                return base + ("deno-aarch64-apple-darwin.zip" if arch == "arm64"
                               else "deno-x86_64-apple-darwin.zip")
            return base + ("deno-aarch64-unknown-linux-gnu.zip" if arch == "arm64"
                           else "deno-x86_64-unknown-linux-gnu.zip")
        return None

    def github_repo(self) -> str:
        return {"yt-dlp": "yt-dlp/yt-dlp", "ffmpeg": "yt-dlp/FFmpeg-Builds",
                "deno": "denoland/deno"}[self.key]

    # -- estado ----------------------------------------------------------------
    def resolved_path(self) -> Path | None:
        """Ruta utilizable del componente (la local; en macOS el ffmpeg del sistema)."""
        if self.target().exists():
            return self.target()
        if self.key == "ffmpeg" and paths.IS_MAC:
            found = shutil.which("ffmpeg")
            return Path(found) if found else None
        return None

    def installed(self) -> bool:
        return self.resolved_path() is not None

    def local_version(self) -> str | None:
        exe = self.resolved_path()
        if not exe:
            return None
        arg = {"yt-dlp": "--version", "ffmpeg": "-version", "deno": "--version"}[self.key]
        try:
            out = subprocess.run([str(exe), arg], capture_output=True, text=True,
                                 timeout=20, creationflags=NO_WINDOW).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return None
        first = out.splitlines()[0] if out else ""
        if self.key == "ffmpeg":
            # "ffmpeg version N-118000-g... Copyright" → "N-118000-g..."
            parts = first.split()
            return parts[2] if len(parts) > 2 else first
        if self.key == "deno":
            return first.replace("deno ", "").split(" ")[0]
        return first or None


COMPONENTS: dict[str, Component] = {
    "yt-dlp": Component("yt-dlp", "yt-dlp", "Motor de descarga", True),
    "ffmpeg": Component("ffmpeg", "FFmpeg", "Conversión a MP3, unión de audio/video y recortes", True),
    "deno": Component("deno", "Deno", "Runtime JavaScript necesario para YouTube", False),
}


def missing_components(include_optional: bool = True) -> list[Component]:
    return [c for c in COMPONENTS.values()
            if (c.required or include_optional) and c.url() and not c.installed()]


def latest_release_tag(component: Component, timeout: float = 10) -> str | None:
    req = urllib.request.Request(
        f"https://api.github.com/repos/{component.github_repo()}/releases/latest",
        headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8")).get("tag_name")
    except (OSError, ValueError):
        return None


def _download(url: str, dest: Path, progress: ProgressCb | None, cancel: threading.Event | None) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp, open(dest, "wb") as fh:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            if cancel is not None and cancel.is_set():
                raise Cancelled()
            chunk = resp.read(256 * 1024)
            if not chunk:
                break
            fh.write(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)


def _extract_members(archive: Path, wanted: dict[str, Path]) -> None:
    """Extrae los archivos cuyo nombre base esté en ``wanted`` (nombre → destino)."""
    found: set[str] = set()
    if archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive) as zf:
            for info in zf.infolist():
                base = info.filename.rsplit("/", 1)[-1]
                if base in wanted and not info.is_dir():
                    with zf.open(info) as src, open(wanted[base], "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    found.add(base)
    else:
        with tarfile.open(archive) as tf:
            for member in tf.getmembers():
                base = member.name.rsplit("/", 1)[-1]
                if base in wanted and member.isfile():
                    src = tf.extractfile(member)
                    assert src is not None
                    with src, open(wanted[base], "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    found.add(base)
    missing = set(wanted) - found
    if missing:
        raise RuntimeError(f"El archivo descargado no contiene: {', '.join(sorted(missing))}")


def install(component: Component, progress: ProgressCb | None = None,
            cancel: threading.Event | None = None) -> None:
    """Descarga (o actualiza) un componente a la carpeta ``bin`` del programa."""
    url = component.url()
    if not url:
        raise RuntimeError(f"{component.name} no tiene descarga disponible para esta plataforma.")
    target = component.target()
    target.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="zubel_") as tmp:
        tmp_dir = Path(tmp)
        archive = tmp_dir / url.rsplit("/", 1)[-1]
        _download(url, archive, progress, cancel)

        if component.key == "yt-dlp":
            staged = {target.name: archive}
        elif component.key == "ffmpeg":
            staged = {
                paths.ffmpeg_path().name: tmp_dir / f"out_{paths.ffmpeg_path().name}",
                paths.ffprobe_path().name: tmp_dir / f"out_{paths.ffprobe_path().name}",
            }
            _extract_members(archive, staged)
        else:  # deno
            staged = {target.name: tmp_dir / f"out_{target.name}"}
            _extract_members(archive, staged)

        for name, src in staged.items():
            dest = target.parent / name
            if dest.exists():
                dest.unlink()
            shutil.move(str(src), dest)
            if not paths.IS_WINDOWS:
                dest.chmod(0o755)


def subprocess_env() -> dict[str, str]:
    """Entorno para lanzar yt-dlp: los binarios locales van primero en el PATH."""
    env = dict(os.environ)
    extra = [str(paths.bin_dir()), str(paths.ffmpeg_dir())]
    env["PATH"] = os.pathsep.join(extra + [env.get("PATH", "")])
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env
