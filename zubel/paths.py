"""Rutas de la aplicación.

Los binarios (yt-dlp, ffmpeg, deno) viven dentro de la carpeta de instalación
del programa, en ``<instalación>/bin``. Nunca se instalan de forma global.
Si la carpeta de instalación no tiene permisos de escritura se usa
``%LOCALAPPDATA%/Zubel/bin`` como alternativa.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
EXE = ".exe" if IS_WINDOWS else ""


def app_dir() -> Path:
    """Carpeta donde está instalado el programa (o la raíz del repo en desarrollo)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _user_data_dir() -> Path:
    if IS_WINDOWS:
        base = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
        return Path(base) / "Zubel"
    if IS_MAC:
        return Path.home() / "Library" / "Application Support" / "Zubel"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "zubel"


def config_dir() -> Path:
    if IS_WINDOWS:
        base = os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming"
        path = Path(base) / "Zubel"
    elif IS_MAC:
        path = _user_data_dir()
    else:
        path = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "zubel"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _is_writable(directory: Path) -> bool:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / ".zubel_write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


_bin_dir: Path | None = None


def bin_dir() -> Path:
    global _bin_dir
    if _bin_dir is None:
        preferred = app_dir() / "bin"
        _bin_dir = preferred if _is_writable(preferred) else _user_data_dir() / "bin"
        _bin_dir.mkdir(parents=True, exist_ok=True)
    return _bin_dir


def ytdlp_path() -> Path:
    return bin_dir() / f"yt-dlp{EXE}"


def ffmpeg_dir() -> Path:
    return bin_dir() / "ffmpeg"


def ffmpeg_path() -> Path:
    return ffmpeg_dir() / f"ffmpeg{EXE}"


def ffprobe_path() -> Path:
    return ffmpeg_dir() / f"ffprobe{EXE}"


def deno_path() -> Path:
    return bin_dir() / f"deno{EXE}"


def default_download_dir() -> Path:
    return Path.home() / "Downloads" / "Zubel"


def settings_file() -> Path:
    return config_dir() / "settings.json"


def queue_file() -> Path:
    return config_dir() / "queue.json"


def archive_file() -> Path:
    return config_dir() / "archive.txt"


def temp_root() -> Path:
    """Archivos intermedios de cada descarga (.part, fragmentos)."""
    return _user_data_dir() / "tmp"


def thumbs_cache_dir() -> Path:
    path = _user_data_dir() / "cache" / "thumbs"
    path.mkdir(parents=True, exist_ok=True)
    return path
