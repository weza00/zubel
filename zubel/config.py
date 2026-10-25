"""Configuración persistente (JSON) y opciones de descarga."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields, replace
from typing import Any

from zubel import paths

VIDEO_CONTAINERS = ["mp4", "mkv", "webm", "mov", "avi", "flv"]
AUDIO_FORMATS = ["mp3", "m4a", "aac", "opus", "flac", "wav", "ogg", "alac", "vorbis"]
AUDIO_QUALITIES = [
    ("Máxima (VBR 0)", "0"),
    ("320 kbps", "320K"),
    ("256 kbps", "256K"),
    ("192 kbps", "192K"),
    ("160 kbps", "160K"),
    ("128 kbps", "128K"),
    ("96 kbps", "96K"),
    ("64 kbps", "64K"),
]
RESOLUTIONS = [4320, 2160, 1440, 1080, 720, 480, 360, 240, 144]
VIDEO_CODECS = [
    ("Automático", "any"),
    ("H.264 (máxima compatibilidad)", "h264"),
    ("H.265 / HEVC", "h265"),
    ("VP9", "vp9"),
    ("AV1", "av01"),
]
FPS_PREFS = [("Automático", "any"), ("Preferir 60 fps", "60"), ("Máximo 30 fps", "30")]
SUB_FORMATS = ["srt", "vtt", "ass", "lrc"]
BROWSERS = ["", "chrome", "firefox", "edge", "brave", "opera", "vivaldi", "chromium", "safari"]
SPONSORBLOCK_CATEGORIES = [
    ("sponsor", "Patrocinios"),
    ("intro", "Intros"),
    ("outro", "Outros / créditos"),
    ("selfpromo", "Autopromoción"),
    ("preview", "Avances / resúmenes"),
    ("interaction", "Recordatorios (suscríbete…)"),
    ("music_offtopic", "Música: partes sin música"),
    ("filler", "Relleno"),
]
FILENAME_PRESETS = [
    ("Título", "%(title)s.%(ext)s"),
    ("Título [id]", "%(title)s [%(id)s].%(ext)s"),
    ("Canal - Título", "%(uploader)s - %(title)s.%(ext)s"),
    ("Fecha - Título", "%(upload_date>%Y-%m-%d)s - %(title)s.%(ext)s"),
    ("Canal/Título", "%(uploader)s/%(title)s.%(ext)s"),
]


@dataclass
class DownloadOptions:
    """Opciones que pueden cambiar en cada descarga."""

    mode: str = "video"  # "video" | "audio"
    video_container: str = "mp4"
    resolution: int = 0  # 0 = la mejor disponible
    vcodec: str = "any"
    fps_pref: str = "any"
    audio_format: str = "mp3"
    audio_quality: str = "0"
    format_override: str = ""  # selector -f manual (tabla de formatos)
    start: float | None = None  # segundos
    end: float | None = None
    precise_cuts: bool = False
    subtitles: bool = False
    auto_subs: bool = False
    sub_langs: str = "es,en"
    embed_subs: bool = True
    sub_format: str = "srt"
    embed_thumbnail: bool = True
    write_thumbnail: bool = False
    embed_metadata: bool = True
    embed_chapters: bool = True
    split_chapters: bool = False
    write_description: bool = False
    write_info_json: bool = False
    sponsorblock_remove: list[str] = field(default_factory=list)
    sponsorblock_mark: bool = False
    keep_original: bool = False
    playlist_items: str = ""
    playlist_reverse: bool = False
    extra_args: str = ""

    def copy(self, **changes: Any) -> "DownloadOptions":
        return replace(self, sponsorblock_remove=list(self.sponsorblock_remove), **changes)


@dataclass
class Settings:
    """Configuración global de la aplicación."""

    output_dir: str = str(paths.default_download_dir())
    filename_template: str = "%(title)s.%(ext)s"
    playlist_subfolder: bool = True
    max_concurrent: int = 3
    concurrent_fragments: int = 4
    rate_limit: str = ""
    retries: int = 10
    proxy: str = ""
    cookies_browser: str = ""
    cookies_file: str = ""
    user_agent: str = ""
    force_ipv4: bool = False
    geo_bypass_country: str = ""
    restrict_filenames: bool = False
    overwrite: bool = False
    no_mtime: bool = True
    use_archive: bool = False
    prefer_single_video: bool = True
    auto_paste_clipboard: bool = True
    auto_analyze: bool = True
    notify_on_finish: bool = True
    open_folder_on_finish: bool = False
    check_updates_on_start: bool = True
    auto_update_ytdlp: bool = True
    animations: bool = True
    accent: str = "#7C5CFF"
    window_geometry: str = ""
    defaults: DownloadOptions = field(default_factory=DownloadOptions)


def _filter(cls, data: dict) -> dict:
    names = {f.name for f in fields(cls)}
    return {k: v for k, v in data.items() if k in names}


def options_from_dict(data: dict | None) -> DownloadOptions:
    return DownloadOptions(**_filter(DownloadOptions, data or {}))


def load_settings() -> Settings:
    try:
        data = json.loads(paths.settings_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Settings()
    defaults = options_from_dict(data.pop("defaults", None))
    try:
        settings = Settings(**_filter(Settings, data))
    except TypeError:
        settings = Settings()
    settings.defaults = defaults
    return settings


def save_settings(settings: Settings) -> None:
    path = paths.settings_file()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(asdict(settings), indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
