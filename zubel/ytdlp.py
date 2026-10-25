"""Traducción de opciones a argumentos de yt-dlp y parseo de su salida."""
from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from typing import Any

from zubel import paths
from zubel.config import DownloadOptions, Settings

PROGRESS_PREFIX = "[zubel] "
PP_PREFIX = "[zubel-pp] "
FILE_PREFIX = "[zubel-file] "

PROGRESS_TEMPLATE = (
    "download:" + PROGRESS_PREFIX
    + "%(progress.status)s|%(progress.downloaded_bytes)s|%(progress.total_bytes)s|"
    "%(progress.total_bytes_estimate)s|%(progress.speed)s|%(progress.eta)s|"
    "%(progress.fragment_index)s|%(progress.fragment_count)s|%(info.vcodec)s|%(info.acodec)s"
)
PP_TEMPLATE = "postprocess:" + PP_PREFIX + "%(progress.status)s|%(progress.postprocessor)s"


# ---------------------------------------------------------------------------
# Información del video
# ---------------------------------------------------------------------------
@dataclass
class FormatInfo:
    format_id: str
    ext: str
    height: int | None
    width: int | None
    fps: float | None
    vcodec: str
    acodec: str
    tbr: float | None
    abr: float | None
    filesize: int | None
    note: str
    protocol: str
    url: str

    @property
    def has_video(self) -> bool:
        return self.vcodec not in ("none", "", None)

    @property
    def has_audio(self) -> bool:
        return self.acodec not in ("none", "", None)

    @property
    def kind(self) -> str:
        if self.has_video and self.has_audio:
            return "video+audio"
        return "video" if self.has_video else "audio"

    @property
    def res(self) -> int | None:
        """Resolución como la entiende yt-dlp: la dimensión más pequeña."""
        if self.height and self.width:
            return min(self.height, self.width)
        return self.height

    @property
    def resolution(self) -> str:
        if self.res:
            return f"{self.res}p" + (f"{int(self.fps)}" if self.fps and self.fps > 30 else "")
        return "—"


@dataclass
class PlaylistEntry:
    index: int
    id: str
    title: str
    url: str
    duration: float | None


@dataclass
class MediaInfo:
    url: str
    id: str
    title: str
    uploader: str
    duration: float | None
    thumbnails: list[str]
    view_count: int | None
    upload_date: str | None
    extractor: str
    is_live: bool
    formats: list[FormatInfo] = field(default_factory=list)
    is_playlist: bool = False
    entries: list[PlaylistEntry] = field(default_factory=list)

    @property
    def thumbnail(self) -> str | None:
        return self.thumbnails[0] if self.thumbnails else None

    @property
    def heights(self) -> list[int]:
        return sorted({f.res for f in self.formats if f.has_video and f.res}, reverse=True)

    def preview_url(self) -> str | None:
        """URL directa de un formato con audio y video apto para previsualizar."""
        candidates = [
            f for f in self.formats
            if f.has_video and f.has_audio and f.protocol in ("https", "http") and f.url
        ]
        if not candidates:
            return None
        def score(f: FormatInfo) -> tuple:
            h = f.height or 0
            return (f.ext == "mp4", 240 <= h <= 720, -abs(h - 480))
        return max(candidates, key=score).url

    def estimate_size(self, opts: DownloadOptions) -> int | None:
        """Estimación aproximada del tamaño final en bytes."""
        def size(f: FormatInfo) -> int | None:
            if f.filesize:
                return f.filesize
            if f.tbr and self.duration:
                return int(f.tbr * 1000 / 8 * self.duration)
            return None

        audios = [f for f in self.formats if f.has_audio and not f.has_video and size(f)]
        best_audio = max(audios, key=lambda f: f.abr or f.tbr or 0, default=None)
        total: int | None
        if opts.mode == "audio":
            if opts.audio_quality.endswith("K") and self.duration and opts.audio_format not in ("flac", "wav", "alac"):
                total = int(int(opts.audio_quality[:-1]) * 1000 / 8 * self.duration)
            else:
                total = size(best_audio) if best_audio else None
        else:
            videos = [f for f in self.formats if f.has_video and f.res and size(f)]
            if opts.resolution:
                fitting = [f for f in videos if f.res <= opts.resolution]
                videos = fitting or videos
            if not videos:
                return None
            top = max(f.res for f in videos)
            same = [f for f in videos if f.res == top]
            best_video = max(same, key=lambda f: f.tbr or 0)
            total = size(best_video) or 0
            if not best_video.has_audio and best_audio:
                total += size(best_audio) or 0
        if total and self.duration and (opts.start is not None or opts.end is not None):
            start = opts.start or 0
            end = opts.end if opts.end is not None else self.duration
            total = int(total * max(0.0, end - start) / self.duration)
        return total or None


def _thumbnail_candidates(data: dict) -> list[str]:
    """Miniaturas ordenadas de mejor a peor (algunas pueden no existir: se prueban en orden)."""
    thumbs = [t for t in data.get("thumbnails") or [] if t.get("url")]
    # Qt carga JPG/PNG sin plugins extra: se prefieren sobre WebP.
    def score(t: dict) -> tuple:
        url = t["url"].split("?")[0].lower()
        return (url.endswith((".jpg", ".jpeg", ".png")), t.get("preference") or 0,
                (t.get("width") or 0) * (t.get("height") or 0))
    urls = [t["url"] for t in sorted(thumbs, key=score, reverse=True)]
    if data.get("thumbnail") and data["thumbnail"] not in urls:
        urls.append(data["thumbnail"])
    return urls[:6]


def parse_info(data: dict, url: str) -> MediaInfo:
    is_playlist = data.get("_type") in ("playlist", "multi_video")
    info = MediaInfo(
        url=url,
        id=str(data.get("id") or ""),
        title=data.get("title") or data.get("id") or url,
        uploader=data.get("uploader") or data.get("channel") or data.get("uploader_id") or "",
        duration=data.get("duration"),
        thumbnails=_thumbnail_candidates(data),
        view_count=data.get("view_count"),
        upload_date=data.get("upload_date"),
        extractor=data.get("extractor_key") or data.get("extractor") or "",
        is_live=bool(data.get("is_live")),
        is_playlist=is_playlist,
    )
    if is_playlist:
        for i, entry in enumerate(data.get("entries") or [], start=1):
            if not entry:
                continue
            info.entries.append(PlaylistEntry(
                index=i,
                id=str(entry.get("id") or ""),
                title=entry.get("title") or entry.get("id") or f"Elemento {i}",
                url=entry.get("url") or entry.get("webpage_url") or "",
                duration=entry.get("duration"),
            ))
        if not info.thumbnails:
            for entry in data.get("entries") or []:
                if entry and (thumbs := _thumbnail_candidates(entry)):
                    info.thumbnails = thumbs
                    break
        info.duration = sum(e.duration or 0 for e in info.entries) or None
        return info

    for f in data.get("formats") or []:
        info.formats.append(FormatInfo(
            format_id=str(f.get("format_id")),
            ext=f.get("ext") or "",
            height=f.get("height"),
            width=f.get("width"),
            fps=f.get("fps"),
            vcodec=f.get("vcodec") or "none",
            acodec=f.get("acodec") or "none",
            tbr=f.get("tbr"),
            abr=f.get("abr"),
            filesize=f.get("filesize") or f.get("filesize_approx"),
            note=f.get("format_note") or "",
            protocol=f.get("protocol") or "",
            url=f.get("url") or "",
        ))
    # Formatos tipo storyboard (imágenes) no sirven para descargar.
    info.formats = [f for f in info.formats if f.ext != "mhtml"]
    return info


# ---------------------------------------------------------------------------
# Construcción de argumentos
# ---------------------------------------------------------------------------
def network_args(settings: Settings) -> list[str]:
    args: list[str] = []
    if settings.proxy:
        args += ["--proxy", settings.proxy]
    if settings.cookies_file:
        args += ["--cookies", settings.cookies_file]
    elif settings.cookies_browser:
        args += ["--cookies-from-browser", settings.cookies_browser]
    if settings.user_agent:
        args += ["--add-headers", f"User-Agent:{settings.user_agent}"]
    if settings.force_ipv4:
        args.append("--force-ipv4")
    if settings.geo_bypass_country:
        args += ["--xff", settings.geo_bypass_country.upper()]
    return args


def base_args() -> list[str]:
    args = ["--color", "never", "--ignore-config"]
    ffmpeg = paths.ffmpeg_path()
    if ffmpeg.exists():
        args += ["--ffmpeg-location", str(ffmpeg.parent)]
    return args


def info_args(url: str, settings: Settings) -> list[str]:
    args = base_args() + ["-J", "--flat-playlist", "--no-warnings"]
    args.append("--no-playlist" if settings.prefer_single_video else "--yes-playlist")
    return args + network_args(settings) + ["--", url]


def _format_sort(opts: DownloadOptions) -> list[str]:
    sort: list[str] = []
    if opts.resolution:
        sort.append(f"res:{opts.resolution}")
    if opts.fps_pref == "60":
        sort.append("fps")
    elif opts.fps_pref == "30":
        sort.append("fps:30")
    if opts.vcodec != "any":
        sort.append(f"vcodec:{opts.vcodec}")
    if opts.video_container == "mp4":
        sort.append("ext:mp4:m4a")
    elif opts.video_container == "webm":
        sort.append("ext:webm:webm")
    return sort


def _seconds(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def download_args(url: str, opts: DownloadOptions, settings: Settings,
                  is_playlist: bool, temp_dir: str) -> list[str]:
    args = base_args()
    args += [
        "--newline", "--progress", "--progress-template", PROGRESS_TEMPLATE,
        "--progress-template", PP_TEMPLATE,
        "--print", f"after_move:{FILE_PREFIX}%(filepath)s",
        "--no-simulate",
    ]

    # --- Formato -----------------------------------------------------------
    if opts.mode == "audio":
        args += ["-f", opts.format_override or "ba/b", "-x"]
        if opts.audio_format and opts.audio_format != "best":
            args += ["--audio-format", opts.audio_format]
        args += ["--audio-quality", opts.audio_quality or "0"]
    else:
        args += ["-f", opts.format_override or "bv*+ba/b"]
        sort = _format_sort(opts)
        if sort and not opts.format_override:
            args += ["-S", ",".join(sort)]
        container = opts.video_container
        if container in ("mp4", "mkv", "mov", "webm"):
            args += ["--merge-output-format", container, "--remux-video", container]
        else:  # avi / flv necesitan recodificar
            args += ["--merge-output-format", "mkv", "--recode-video", container]

    # --- Rango --------------------------------------------------------------
    is_range = opts.start is not None or opts.end is not None
    if is_range:
        start = _seconds(opts.start or 0)
        end = _seconds(opts.end) if opts.end is not None else "inf"
        args += ["--download-sections", f"*{start}-{end}"]
        if opts.precise_cuts:
            args.append("--force-keyframes-at-cuts")

    # --- Subtítulos ---------------------------------------------------------
    if opts.subtitles or opts.auto_subs:
        if opts.subtitles:
            args.append("--write-subs")
        if opts.auto_subs:
            args.append("--write-auto-subs")
        args += ["--sub-langs", opts.sub_langs or "all"]
        if opts.sub_format:
            args += ["--convert-subs", opts.sub_format]
        if opts.embed_subs and opts.mode == "video":
            args.append("--embed-subs")

    # --- Miniatura y metadatos ---------------------------------------------
    if opts.embed_thumbnail:
        args.append("--embed-thumbnail")
    if opts.write_thumbnail:
        args += ["--write-thumbnail", "--convert-thumbnails", "jpg"]
    if opts.embed_metadata:
        args.append("--embed-metadata")
    # Los capítulos (y SponsorBlock) usan tiempos del video completo: en un recorte
    # dejarían una pista de capítulos con la duración original y el reproductor
    # creería que el archivo dura todo el video. --embed-metadata los incrusta
    # implícitamente, así que se desactivan de forma explícita.
    if opts.embed_chapters and opts.mode == "video" and not is_range:
        args.append("--embed-chapters")
    else:
        args.append("--no-embed-chapters")
    if opts.split_chapters and not is_range:
        args.append("--split-chapters")
    if opts.write_description:
        args.append("--write-description")
    if opts.write_info_json:
        args.append("--write-info-json")

    # --- SponsorBlock -------------------------------------------------------
    if opts.sponsorblock_remove and not is_range:
        args += ["--sponsorblock-remove", ",".join(opts.sponsorblock_remove)]
    if opts.sponsorblock_mark and not is_range:
        args += ["--sponsorblock-mark", "all"]

    if opts.keep_original:
        args.append("-k")

    # --- Playlist -----------------------------------------------------------
    if is_playlist:
        args.append("--yes-playlist")
        if opts.playlist_items:
            args += ["--playlist-items", opts.playlist_items]
        elif opts.playlist_reverse:
            args += ["--playlist-items", "::-1"]
    else:
        args.append("--no-playlist")

    # --- Salida -------------------------------------------------------------
    template = settings.filename_template or "%(title)s.%(ext)s"
    if is_playlist and settings.playlist_subfolder:
        template = "%(playlist_title,playlist|Playlist)s/%(playlist_index|0)03d - " + template
    args += ["-P", settings.output_dir, "-P", f"temp:{temp_dir}", "-o", template]
    if paths.IS_WINDOWS:
        args.append("--windows-filenames")
    if settings.restrict_filenames:
        args.append("--restrict-filenames")
    args.append("--force-overwrites" if settings.overwrite else "--no-overwrites")
    if settings.no_mtime:
        args.append("--no-mtime")
    if settings.use_archive:
        args += ["--download-archive", str(paths.archive_file())]

    # --- Red ----------------------------------------------------------------
    args += ["-N", str(max(1, settings.concurrent_fragments))]
    args += ["-R", str(settings.retries), "--fragment-retries", str(settings.retries)]
    if settings.rate_limit:
        args += ["-r", settings.rate_limit]
    args += network_args(settings)

    if opts.extra_args.strip():
        args += shlex.split(opts.extra_args, posix=not paths.IS_WINDOWS)

    return args + ["--", url]


# ---------------------------------------------------------------------------
# Parseo del progreso
# ---------------------------------------------------------------------------
def _num(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass
class ProgressEvent:
    status: str
    downloaded: float | None
    total: float | None
    speed: float | None
    eta: float | None
    fraction: float | None
    stream: str  # "video" | "audio" | "video+audio"


def parse_progress(line: str) -> ProgressEvent | None:
    if not line.startswith(PROGRESS_PREFIX):
        return None
    parts = line[len(PROGRESS_PREFIX):].split("|")
    if len(parts) < 10:
        return None
    status, downloaded, total, estimate, speed, eta, frag_i, frag_n, vcodec, acodec = parts[:10]
    downloaded_n = _num(downloaded)
    total_n = _num(total) or _num(estimate)
    fraction = None
    if downloaded_n is not None and total_n:
        fraction = min(1.0, downloaded_n / total_n)
    elif _num(frag_i) and _num(frag_n):
        fraction = min(1.0, _num(frag_i) / _num(frag_n))
    if status == "finished":
        fraction = 1.0
    has_v = vcodec not in ("none", "NA", "")
    has_a = acodec not in ("none", "NA", "")
    stream = "video+audio" if has_v and has_a else ("audio" if has_a and not has_v else "video")
    return ProgressEvent(status, downloaded_n, total_n, _num(speed), _num(eta), fraction, stream)


POSTPROCESSOR_LABELS = {
    "Merger": "Uniendo audio y video",
    "FFmpegMerger": "Uniendo audio y video",
    "ExtractAudio": "Convirtiendo audio",
    "FFmpegExtractAudio": "Convirtiendo audio",
    "VideoRemuxer": "Cambiando contenedor",
    "FFmpegVideoRemuxer": "Cambiando contenedor",
    "VideoConvertor": "Recodificando video",
    "FFmpegVideoConvertor": "Recodificando video",
    "EmbedThumbnail": "Incrustando miniatura",
    "FFmpegEmbedSubtitle": "Incrustando subtítulos",
    "EmbedSubtitle": "Incrustando subtítulos",
    "FFmpegMetadata": "Escribiendo metadatos",
    "Metadata": "Escribiendo metadatos",
    "SponsorBlock": "Procesando SponsorBlock",
    "ModifyChapters": "Recortando segmentos",
    "FFmpegSplitChapters": "Dividiendo capítulos",
    "SplitChapters": "Dividiendo capítulos",
    "MoveFiles": "Moviendo archivo",
    "MoveFilesAfterDownload": "Moviendo archivo",
    "FFmpegSubtitlesConvertor": "Convirtiendo subtítulos",
    "FFmpegThumbnailsConvertor": "Convirtiendo miniatura",
}


def parse_postprocess(line: str) -> str | None:
    if not line.startswith(PP_PREFIX):
        return None
    parts = line[len(PP_PREFIX):].split("|")
    name = parts[1] if len(parts) > 1 else ""
    return POSTPROCESSOR_LABELS.get(name, "Procesando")


def format_bytes(n: float | None) -> str:
    if not n:
        return "—"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return "—"


def format_time(seconds: float | None, with_ms: bool = False) -> str:
    if seconds is None:
        return "--:--"
    seconds = max(0.0, seconds)
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    out = f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
    if with_ms:
        out += f".{int((seconds % 1) * 10)}"
    return out


def parse_time(text: str) -> float | None:
    """'1:02:03.5', '02:03', '123' → segundos."""
    text = text.strip()
    if not text:
        return None
    try:
        parts = [float(p) for p in text.split(":")]
    except ValueError:
        return None
    total = 0.0
    for p in parts:
        total = total * 60 + p
    return total


def info_from_json(raw: str, url: str) -> MediaInfo:
    import json
    data: Any = json.loads(raw)
    return parse_info(data, url)
