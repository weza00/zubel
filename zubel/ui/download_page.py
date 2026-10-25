"""Página principal: análisis de la URL, vista previa y opciones de descarga."""
from __future__ import annotations

import re
from datetime import datetime

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView, QFileDialog, QFrame, QHBoxLayout, QHeaderView, QLineEdit, QListWidget,
    QListWidgetItem, QScrollArea, QStackedWidget, QTableWidget, QTableWidgetItem, QTabWidget,
    QVBoxLayout, QWidget,
)

from zubel import config
from zubel.config import DownloadOptions, Settings
from zubel.manager import DownloadManager, DownloadTask
from zubel.ui import icons, theme
from zubel.ui.forms import combo, field, fit_stack, grid, set_combo_data, vbox
from zubel.ui.widgets import (
    Collapsible, ImageLoader, LabeledSwitch, RangeSlider, SegmentedControl, Spinner, Toast, VideoPreview, button,
    card, fade_in, icon_button, label,
)
from zubel.workers import InfoFetcher
from zubel.ytdlp import MediaInfo, format_bytes, format_time, parse_time

URL_RE = re.compile(r"^https?://\S+$", re.IGNORECASE)


def _compress_indices(indices: list[int]) -> str:
    """[1,2,3,5,7,8] → '1-3,5,7-8'."""
    out: list[str] = []
    start = prev = None
    for i in indices:
        if start is None:
            start = prev = i
        elif i == prev + 1:
            prev = i
        else:
            out.append(f"{start}-{prev}" if start != prev else str(start))
            start = prev = i
    if start is not None:
        out.append(f"{start}-{prev}" if start != prev else str(start))
    return ",".join(out)


class DownloadPage(QWidget):
    queued = Signal()

    def __init__(self, settings: Settings, manager: DownloadManager, save_settings) -> None:
        super().__init__()
        self.settings = settings
        self.manager = manager
        self._save_settings = save_settings
        self.info: MediaInfo | None = None
        self._last_clip = ""
        self.fetcher = InfoFetcher(self)
        self.fetcher.finished.connect(self._on_info)
        self.fetcher.failed.connect(self._on_fail)
        self._seek_timer = QTimer(self, singleShot=True, interval=120)
        self._seek_timer.timeout.connect(self._do_seek)
        self._seek_to = 0.0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)
        content = QWidget()
        scroll.setWidget(content)
        self.lay = QVBoxLayout(content)
        self.lay.setContentsMargins(32, 28, 32, 28)
        self.lay.setSpacing(18)

        self._build_header()
        self._build_url_bar()
        self._build_empty_state()
        self._build_result()
        self.lay.addStretch(1)
        self.apply_options(settings.defaults)

    # ------------------------------------------------------------------ UI
    def _build_header(self) -> None:
        self.lay.addWidget(label("Nueva descarga", "h1"))
        self.lay.addWidget(label("Descarga videos y audio de YouTube y de más de 1800 sitios compatibles con yt-dlp.",
                                 "muted"))

    def _build_url_bar(self) -> None:
        bar = card()
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)
        link = label()
        link.setPixmap(icons.pixmap("link", theme.MUTED, 20))
        link.setContentsMargins(8, 0, 0, 0)
        lay.addWidget(link)
        self.url_edit = QLineEdit()
        self.url_edit.setProperty("size", "xl")
        self.url_edit.setStyleSheet("border: none; background: transparent;")
        self.url_edit.setPlaceholderText("Pega aquí el enlace del video o playlist…")
        self.url_edit.setClearButtonEnabled(True)
        self.url_edit.returnPressed.connect(self.analyze)
        lay.addWidget(self.url_edit, 1)
        self.spinner = Spinner(22)
        lay.addWidget(self.spinner)
        paste = button("Pegar", "paste", "ghost")
        paste.clicked.connect(self.paste_and_analyze)
        lay.addWidget(paste)
        self.analyze_btn = button("Analizar", "search", "primary")
        self.analyze_btn.clicked.connect(self.analyze)
        lay.addWidget(self.analyze_btn)
        self.lay.addWidget(bar)
        self.error_lbl = label("", "error", wrap=True)
        self.error_lbl.hide()
        self.lay.addWidget(self.error_lbl)

    def _build_empty_state(self) -> None:
        self.empty = card()
        lay = QVBoxLayout(self.empty)
        lay.setContentsMargins(30, 50, 30, 50)
        lay.setSpacing(10)
        ic = label()
        ic.setPixmap(icons.pixmap("download", theme.lighten(theme.ACCENT, 130), 46))
        ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(ic)
        t = label("Pega un enlace para empezar", "h2")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(t)
        s = label("Verás la vista previa, podrás elegir formato, resolución y recortar el fragmento exacto.\n"
                  "YouTube · TikTok · Instagram · X · Twitch · Vimeo · SoundCloud · Facebook · Reddit…", "muted")
        s.setAlignment(Qt.AlignmentFlag.AlignCenter)
        s.setWordWrap(True)
        lay.addWidget(s)
        self.lay.addWidget(self.empty)

    def _build_result(self) -> None:
        self.result = QWidget()
        self.result.hide()
        row = QHBoxLayout(self.result)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(18)

        # ---------------- Columna izquierda: vista previa + rango ----------------
        left = QVBoxLayout()
        left.setSpacing(14)
        preview_card = card()
        pl = QVBoxLayout(preview_card)
        pl.setContentsMargins(12, 12, 12, 10)
        pl.setSpacing(8)
        self.preview = VideoPreview()
        pl.addWidget(self.preview)
        controls = QHBoxLayout()
        controls.setSpacing(6)
        self.play_btn = icon_button("play", "Reproducir / pausar")
        self.play_btn.clicked.connect(self.preview.toggle)
        controls.addWidget(self.play_btn)
        self.mute_btn = icon_button("volume", "Silenciar")
        self.mute_btn.setCheckable(True)
        self.mute_btn.toggled.connect(self._on_mute)
        controls.addWidget(self.mute_btn)
        self.time_lbl = label("00:00 / 00:00", "muted")
        controls.addWidget(self.time_lbl)
        controls.addStretch(1)
        self.mark_start_btn = button("Inicio aquí", "chevron-right", "ghost")
        self.mark_start_btn.setToolTip("Usar la posición actual de la vista previa como inicio")
        self.mark_start_btn.clicked.connect(lambda: self._mark("start"))
        controls.addWidget(self.mark_start_btn)
        self.mark_end_btn = button("Fin aquí", "chevron-down", "ghost")
        self.mark_end_btn.setToolTip("Usar la posición actual de la vista previa como fin")
        self.mark_end_btn.clicked.connect(lambda: self._mark("end"))
        controls.addWidget(self.mark_end_btn)
        pl.addLayout(controls)
        left.addWidget(preview_card)
        self.preview.stateChanged.connect(
            lambda playing: self.play_btn.setIcon(icons.icon("pause" if playing else "play", theme.TEXT, 18)))
        self.preview.positionChanged.connect(self._on_position)

        # Rango / playlist (se alternan)
        self.lower_stack = QStackedWidget()
        self.lower_stack.addWidget(self._build_range_card())
        self.lower_stack.addWidget(self._build_playlist_card())
        fit_stack(self.lower_stack)
        left.addWidget(self.lower_stack)
        left.addStretch(1)
        row.addLayout(left, 3)

        # ---------------- Columna derecha: info + opciones ----------------
        right = QVBoxLayout()
        right.setSpacing(14)
        right.addWidget(self._build_info_card())
        right.addWidget(self._build_format_card())
        right.addWidget(self._build_more_options())
        right.addWidget(self._build_output_card())
        right.addStretch(1)
        rw = QWidget()
        rw.setLayout(right)
        rw.setMinimumWidth(400)
        rw.setMaximumWidth(520)
        row.addWidget(rw, 2)
        self.lay.addWidget(self.result)

    def _build_range_card(self) -> QWidget:
        c = card()
        lay = QVBoxLayout(c)
        lay.setContentsMargins(18, 14, 18, 16)
        lay.setSpacing(10)
        head = QHBoxLayout()
        ic = label()
        ic.setPixmap(icons.pixmap("scissors", theme.lighten(theme.ACCENT, 130), 18))
        head.addWidget(ic)
        head.addWidget(label("Rango de descarga", "h3"))
        head.addStretch(1)
        self.range_switch = LabeledSwitch("Recortar")
        self.range_switch.toggled.connect(self._on_range_toggled)
        head.addWidget(self.range_switch)
        lay.addLayout(head)

        self.slider = RangeSlider()
        self.slider.rangeChanged.connect(self._on_slider)
        self.slider.handleDragged.connect(self._queue_seek)
        lay.addWidget(self.slider)

        times = QHBoxLayout()
        times.setSpacing(10)
        self.start_edit = QLineEdit()
        self.start_edit.setPlaceholderText("00:00")
        self.start_edit.setFixedWidth(110)
        self.start_edit.editingFinished.connect(self._on_time_edit)
        self.end_edit = QLineEdit()
        self.end_edit.setPlaceholderText("00:00")
        self.end_edit.setFixedWidth(110)
        self.end_edit.editingFinished.connect(self._on_time_edit)
        times.addWidget(field("Inicio", self.start_edit))
        times.addWidget(field("Fin", self.end_edit))
        times.addStretch(1)
        self.loop_btn = button("Reproducir recorte", "play", "ghost")
        self.loop_btn.clicked.connect(self._play_range)
        times.addWidget(self.loop_btn, 0, Qt.AlignmentFlag.AlignBottom)
        lay.addLayout(times)
        self.precise_switch = LabeledSwitch(
            "Cortes precisos", "Recodifica en los puntos de corte para que sean exactos (más lento).")
        self.precise_switch.toggled.connect(self._update_estimate)
        lay.addWidget(self.precise_switch)
        self.range_note = label("", "subtle", wrap=True)
        self.range_note.hide()
        lay.addWidget(self.range_note)
        self._set_range_enabled(False)
        return c

    def _build_playlist_card(self) -> QWidget:
        c = card()
        lay = QVBoxLayout(c)
        lay.setContentsMargins(18, 14, 18, 16)
        lay.setSpacing(10)
        head = QHBoxLayout()
        ic = label()
        ic.setPixmap(icons.pixmap("playlist", theme.lighten(theme.ACCENT, 130), 18))
        head.addWidget(ic)
        self.playlist_title = label("Playlist", "h3")
        head.addWidget(self.playlist_title)
        head.addStretch(1)
        all_btn = button("Todos", "check", "ghost")
        all_btn.clicked.connect(lambda: self._check_all(True))
        none_btn = button("Ninguno", "x", "ghost")
        none_btn.clicked.connect(lambda: self._check_all(False))
        head.addWidget(all_btn)
        head.addWidget(none_btn)
        lay.addLayout(head)
        self.playlist_list = QListWidget()
        self.playlist_list.setMinimumHeight(260)
        self.playlist_list.itemChanged.connect(self._update_playlist_count)
        lay.addWidget(self.playlist_list)
        self.playlist_count = label("", "muted")
        lay.addWidget(self.playlist_count)
        self.reverse_switch = LabeledSwitch("Descargar en orden inverso")
        lay.addWidget(self.reverse_switch)
        return c

    def _build_info_card(self) -> QWidget:
        c = card()
        lay = QVBoxLayout(c)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(6)
        badges = QHBoxLayout()
        self.site_badge = label("", "badge")
        self.kind_badge = label("", "badge")
        badges.addWidget(self.site_badge)
        badges.addWidget(self.kind_badge)
        badges.addStretch(1)
        lay.addLayout(badges)
        self.title_lbl = label("", "h2", wrap=True)
        self.title_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(self.title_lbl)
        self.meta_lbl = label("", "muted", wrap=True)
        lay.addWidget(self.meta_lbl)
        return c

    def _build_format_card(self) -> QWidget:
        c = card()
        lay = QVBoxLayout(c)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(14)
        self.mode = SegmentedControl([("Video", "video"), ("Solo audio", "music")])
        self.mode.changed.connect(self._on_mode)
        lay.addWidget(self.mode)

        self.mode_stack = QStackedWidget()
        # Video
        self.container_combo = combo([(c.upper(), c) for c in config.VIDEO_CONTAINERS])
        self.res_combo = combo([("Mejor disponible", 0)])
        self.vcodec_combo = combo(config.VIDEO_CODECS)
        self.fps_combo = combo(config.FPS_PREFS)
        video = grid([
            field("Formato", self.container_combo),
            field("Resolución", self.res_combo),
            field("Códec de video", self.vcodec_combo),
            field("Fotogramas", self.fps_combo),
        ])
        # Audio
        self.afmt_combo = combo([(f.upper(), f) for f in config.AUDIO_FORMATS]
                                + [("Original (sin convertir)", "best")])
        self.aq_combo = combo(config.AUDIO_QUALITIES)
        audio = grid([field("Formato", self.afmt_combo), field("Calidad", self.aq_combo)])
        self.mode_stack.addWidget(video)
        self.mode_stack.addWidget(audio)
        fit_stack(self.mode_stack)
        lay.addWidget(self.mode_stack)
        for box in (self.container_combo, self.res_combo, self.vcodec_combo, self.fps_combo,
                    self.afmt_combo, self.aq_combo):
            box.currentIndexChanged.connect(self._update_estimate)
        self.afmt_combo.currentIndexChanged.connect(self._on_audio_format)

        self.estimate_lbl = label("", "muted")
        lay.addWidget(self.estimate_lbl)
        return c

    def _build_more_options(self) -> QWidget:
        c = card()
        lay = QVBoxLayout(c)
        lay.setContentsMargins(6, 6, 6, 6)
        self.more = Collapsible("Más opciones", "sliders")
        tabs = QTabWidget()
        tabs.setDocumentMode(True)

        # Subtítulos
        self.subs_switch = LabeledSwitch("Descargar subtítulos")
        self.autosubs_switch = LabeledSwitch("Incluir subtítulos automáticos")
        self.embed_subs_switch = LabeledSwitch("Incrustar en el video")
        self.sub_langs = QLineEdit()
        self.sub_langs.setPlaceholderText("es,en  ·  es.*  ·  all")
        self.sub_fmt = combo([(f.upper(), f) for f in config.SUB_FORMATS])
        tabs.addTab(vbox(self.subs_switch, self.autosubs_switch, self.embed_subs_switch,
                         grid([field("Idiomas", self.sub_langs, "Códigos separados por coma; admite regex."),
                               field("Formato", self.sub_fmt)]), margins=(10, 12, 10, 8)),
                    "Subtítulos")

        # Metadatos
        self.embed_thumb_switch = LabeledSwitch("Incrustar miniatura", "Portada en MP3/M4A/MP4/MKV.")
        self.write_thumb_switch = LabeledSwitch("Guardar miniatura como JPG")
        self.embed_meta_switch = LabeledSwitch("Incrustar metadatos", "Título, artista, fecha, descripción…")
        self.embed_chapters_switch = LabeledSwitch("Incrustar capítulos")
        self.split_chapters_switch = LabeledSwitch("Dividir por capítulos", "Un archivo por capítulo.")
        self.write_desc_switch = LabeledSwitch("Guardar descripción (.description)")
        self.write_json_switch = LabeledSwitch("Guardar info JSON")
        tabs.addTab(vbox(self.embed_thumb_switch, self.write_thumb_switch, self.embed_meta_switch,
                         self.embed_chapters_switch, self.split_chapters_switch, self.write_desc_switch,
                         self.write_json_switch, spacing=2, margins=(10, 12, 10, 8)), "Metadatos")

        # SponsorBlock
        self.sb_switches: dict[str, LabeledSwitch] = {}
        sb_widgets = [label("Elimina automáticamente segmentos marcados por la comunidad (solo YouTube).",
                            "subtle", wrap=True)]
        for key, text in config.SPONSORBLOCK_CATEGORIES:
            sw = LabeledSwitch(text)
            self.sb_switches[key] = sw
            sb_widgets.append(sw)
        self.sb_mark_switch = LabeledSwitch("Marcar segmentos como capítulos", "En lugar de eliminarlos.")
        sb_widgets.append(self.sb_mark_switch)
        tabs.addTab(vbox(*sb_widgets, spacing=0, margins=(10, 12, 10, 8)), "SponsorBlock")

        # Formatos manuales
        fmt = QWidget()
        fl = QVBoxLayout(fmt)
        fl.setContentsMargins(4, 12, 4, 8)
        self.manual_switch = LabeledSwitch(
            "Usar formatos seleccionados", "Selecciona una fila de video y otra de audio (Ctrl+clic).")
        self.manual_switch.toggled.connect(self._update_manual)
        fl.addWidget(self.manual_switch)
        self.formats_table = QTableWidget(0, 8)
        self.formats_table.setHorizontalHeaderLabels(
            ["ID", "Ext", "Resolución", "Video", "Audio", "Bitrate", "Tamaño", "Nota"])
        self.formats_table.verticalHeader().hide()
        self.formats_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.formats_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.formats_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.formats_table.setAlternatingRowColors(True)
        self.formats_table.setShowGrid(False)
        self.formats_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.formats_table.horizontalHeader().setStretchLastSection(True)
        self.formats_table.setMinimumHeight(240)
        self.formats_table.itemSelectionChanged.connect(self._update_manual)
        fl.addWidget(self.formats_table)
        self.manual_lbl = label("", "subtle")
        fl.addWidget(self.manual_lbl)
        tabs.addTab(fmt, "Formatos")

        # Avanzado
        self.keep_switch = LabeledSwitch("Conservar archivos originales", "No borra el video/audio previo a la conversión.")
        self.extra_edit = QLineEdit()
        self.extra_edit.setPlaceholderText('--limit-rate 2M --match-filter "duration < 600"')
        tabs.addTab(vbox(self.keep_switch,
                         field("Argumentos extra para yt-dlp", self.extra_edit,
                               "Se añaden tal cual al comando. Consulta la documentación de yt-dlp."),
                         margins=(10, 12, 10, 8)), "Extra")

        self.more.set_content(tabs)
        lay.addWidget(self.more)
        return c

    def _build_output_card(self) -> QWidget:
        c = card()
        lay = QVBoxLayout(c)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(12)
        row = QHBoxLayout()
        self.folder_edit = QLineEdit(self.settings.output_dir)
        self.folder_edit.editingFinished.connect(self._folder_edited)
        row.addWidget(self.folder_edit, 1)
        browse = icon_button("folder", "Elegir carpeta", "ghost")
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        holder = QWidget()
        holder.setLayout(row)
        row.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(field("Guardar en", holder))
        actions = QHBoxLayout()
        actions.setSpacing(10)
        save_def = icon_button("save", "Guardar estas opciones como predeterminadas", "ghost")
        save_def.clicked.connect(self._save_defaults)
        actions.addWidget(save_def)
        self.download_btn = button("Descargar", "download", "primary", "lg")
        self.download_btn.clicked.connect(self.enqueue)
        actions.addWidget(self.download_btn, 1)
        lay.addLayout(actions)
        return c

    # ------------------------------------------------------------ análisis
    def paste_and_analyze(self) -> None:
        text = QGuiApplication.clipboard().text().strip()
        if text:
            self.url_edit.setText(text)
            self.analyze()

    def check_clipboard(self) -> None:
        """Si el portapapeles tiene un enlace nuevo, lo propone automáticamente."""
        if not self.settings.auto_paste_clipboard:
            return
        text = QGuiApplication.clipboard().text().strip()
        if not text or text == self._last_clip or not URL_RE.match(text):
            return
        self._last_clip = text
        if text != self.url_edit.text().strip():
            self.url_edit.setText(text)
            if self.settings.auto_analyze:
                self.analyze()

    def analyze(self) -> None:
        url = self.url_edit.text().strip()
        if not url:
            self.url_edit.setFocus()
            return
        if not URL_RE.match(url) and not re.match(r"^[a-z]+search\d*(all)?:", url, re.IGNORECASE):
            if re.match(r"^[\w-]{11}$", url):  # id de YouTube
                url = f"https://www.youtube.com/watch?v={url}"
            elif "." in url and " " not in url:
                url = "https://" + url
            else:
                url = f"ytsearch1:{url}"  # búsqueda en YouTube
            self.url_edit.setText(url)
        self._last_clip = url
        self.error_lbl.hide()
        self.spinner.start()
        self.analyze_btn.setEnabled(False)
        self.analyze_btn.setText("Analizando…")
        self.fetcher.fetch(url, self.settings)

    def _reset_analyze_btn(self) -> None:
        self.spinner.stop()
        self.analyze_btn.setEnabled(True)
        self.analyze_btn.setText("Analizar")

    def _on_fail(self, message: str) -> None:
        self._reset_analyze_btn()
        self.error_lbl.setText(f"No se pudo analizar el enlace: {message}")
        fade_in(self.error_lbl)

    def _on_info(self, info: MediaInfo) -> None:
        self._reset_analyze_btn()
        # "ytsearch1:" devuelve una playlist de un único resultado
        if info.is_playlist and info.url.startswith("ytsearch") and len(info.entries) == 1:
            self.url_edit.setText(info.entries[0].url)
            self.analyze()
            return
        self.info = info
        self.title_lbl.setText(info.title)
        self.site_badge.setText(info.extractor or "Web")
        self.kind_badge.setText(
            f"Playlist · {len(info.entries)} elementos" if info.is_playlist
            else ("En directo" if info.is_live else "Video"))
        meta = []
        if info.uploader:
            meta.append(info.uploader)
        if info.duration:
            meta.append(format_time(info.duration))
        if info.view_count:
            meta.append(f"{info.view_count:,} vistas".replace(",", "."))
        if info.upload_date and len(info.upload_date) == 8:
            try:
                meta.append(datetime.strptime(info.upload_date, "%Y%m%d").strftime("%d/%m/%Y"))
            except ValueError:
                pass
        self.meta_lbl.setText("  ·  ".join(meta))

        self.preview.set_media(None if info.is_playlist else info.preview_url(), info.thumbnails,
                               "" if info.is_playlist else "Vista previa de video no disponible")
        self.time_lbl.setText(f"00:00 / {format_time(info.duration)}")
        for w in (self.play_btn, self.mute_btn, self.mark_start_btn, self.mark_end_btn):
            w.setEnabled(not info.is_playlist and info.preview_url() is not None)

        # Resoluciones disponibles
        current = self.res_combo.currentData() or self.settings.defaults.resolution
        self.res_combo.blockSignals(True)
        self.res_combo.clear()
        self.res_combo.addItem("Mejor disponible", 0)
        heights = info.heights
        for h in config.RESOLUTIONS:
            if not heights or any(x >= h * 0.9 for x in heights) and h <= max(heights) * 1.1:
                tag = {4320: " (8K)", 2160: " (4K)", 1440: " (2K)", 1080: " (Full HD)", 720: " (HD)"}.get(h, "")
                self.res_combo.addItem(f"{h}p{tag}", h)
        set_combo_data(self.res_combo, current)
        self.res_combo.blockSignals(False)

        self._fill_formats(info)

        if info.is_playlist:
            self.lower_stack.setCurrentIndex(1)
            self.playlist_title.setText(info.title)
            self.playlist_list.blockSignals(True)
            self.playlist_list.clear()
            for e in info.entries:
                item = QListWidgetItem(f"{e.index:>3}.  {e.title}" + (f"   ·  {format_time(e.duration)}" if e.duration else ""))
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked)
                item.setData(Qt.ItemDataRole.UserRole, e.index)
                self.playlist_list.addItem(item)
            self.playlist_list.blockSignals(False)
            self._update_playlist_count()
        else:
            self.lower_stack.setCurrentIndex(0)
            can_cut = bool(info.duration) and not info.is_live
            self.range_switch.setEnabled(can_cut)
            self.range_switch.setChecked(False)
            self.slider.set_maximum(info.duration or 1)
            self._set_range_enabled(False)
            self.range_note.setVisible(not can_cut)
            self.range_note.setText("Este contenido no tiene duración fija, no se puede recortar.")

        self._update_estimate()
        if self.empty.isVisible():
            self.empty.hide()
        if not self.result.isVisible():
            fade_in(self.result, 380)

    def _fill_formats(self, info: MediaInfo) -> None:
        t = self.formats_table
        t.setRowCount(0)
        self.manual_switch.setChecked(False)
        rows = sorted(info.formats, key=lambda f: (f.has_video, f.height or 0, f.tbr or 0), reverse=True)
        for f in rows:
            r = t.rowCount()
            t.insertRow(r)
            vals = [f.format_id, f.ext, f.resolution if f.has_video else "solo audio",
                    f.vcodec if f.has_video else "—", f.acodec if f.has_audio else "—",
                    f"{int(f.tbr)}k" if f.tbr else "—", format_bytes(f.filesize), f.note]
            for col, v in enumerate(vals):
                item = QTableWidgetItem(str(v))
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, f.format_id)
                t.setItem(r, col, item)

    # ------------------------------------------------------- vista previa
    def _on_mute(self, muted: bool) -> None:
        self.preview.set_muted(muted)
        self.mute_btn.setIcon(icons.icon("volume-x" if muted else "volume", theme.TEXT, 18))

    def _on_position(self, sec: float) -> None:
        dur = self.info.duration if self.info else None
        self.time_lbl.setText(f"{format_time(sec)} / {format_time(dur)}")
        self.slider.set_playhead(sec)
        self._playhead = sec

    def _queue_seek(self, sec: float) -> None:
        self._seek_to = sec
        if not self._seek_timer.isActive():
            self._seek_timer.start()

    def _do_seek(self) -> None:
        if self.info and not self.info.is_playlist:
            self.preview.seek(self._seek_to)
            self.slider.set_playhead(self._seek_to)
            self._playhead = self._seek_to

    def _mark(self, which: str) -> None:
        pos = getattr(self, "_playhead", 0.0)
        if not self.range_switch.isChecked():
            self.range_switch.setChecked(True)
            self._on_range_toggled(True)
        lo, hi = self.slider.values()
        if which == "start":
            self.slider.set_values(min(pos, hi - self.slider.min_gap), hi)
        else:
            self.slider.set_values(lo, max(pos, lo + self.slider.min_gap))

    def _play_range(self) -> None:
        lo, hi = self.slider.values()
        self.preview.play(loop=(lo, hi))

    # ----------------------------------------------------------- rango
    def _set_range_enabled(self, enabled: bool) -> None:
        for w in (self.slider, self.start_edit, self.end_edit, self.loop_btn, self.precise_switch):
            w.setEnabled(enabled)

    def _on_range_toggled(self, on: bool) -> None:
        self._set_range_enabled(on)
        self._update_estimate()

    def _on_slider(self, lo: float, hi: float) -> None:
        self.start_edit.setText(format_time(lo))
        self.end_edit.setText(format_time(hi))
        self._update_estimate()

    def _on_time_edit(self) -> None:
        lo = parse_time(self.start_edit.text())
        hi = parse_time(self.end_edit.text())
        cur_lo, cur_hi = self.slider.values()
        self.slider.set_values(cur_lo if lo is None else lo, cur_hi if hi is None else hi)
        lo, hi = self.slider.values()
        self.start_edit.setText(format_time(lo))
        self.end_edit.setText(format_time(hi))

    # ---------------------------------------------------------- playlist
    def _check_all(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        self.playlist_list.blockSignals(True)
        for i in range(self.playlist_list.count()):
            self.playlist_list.item(i).setCheckState(state)
        self.playlist_list.blockSignals(False)
        self._update_playlist_count()

    def _checked_indices(self) -> list[int]:
        return [self.playlist_list.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(self.playlist_list.count())
                if self.playlist_list.item(i).checkState() == Qt.CheckState.Checked]

    def _update_playlist_count(self, *_):
        n = len(self._checked_indices())
        self.playlist_count.setText(f"{n} de {self.playlist_list.count()} seleccionados")
        self.download_btn.setEnabled(n > 0 or self.playlist_list.count() == 0)

    # ---------------------------------------------------------- opciones
    def _on_mode(self, index: int) -> None:
        self.mode_stack.setCurrentIndex(index)
        self.embed_subs_switch.setEnabled(index == 0)
        self.embed_chapters_switch.setEnabled(index == 0)
        self._update_estimate()

    def _on_audio_format(self) -> None:
        lossless = self.afmt_combo.currentData() in ("flac", "wav", "alac", "best")
        self.aq_combo.setEnabled(not lossless)

    def _update_manual(self) -> None:
        ids = []
        seen_rows = set()
        for idx in self.formats_table.selectionModel().selectedRows():
            if idx.row() not in seen_rows:
                seen_rows.add(idx.row())
                ids.append(self.formats_table.item(idx.row(), 0).text())
        self._manual_selector = "+".join(ids[:2]) if ids else ""
        if self.manual_switch.isChecked():
            self.manual_lbl.setText(f"Selector: -f {self._manual_selector}" if ids else "Selecciona al menos un formato.")
        else:
            self.manual_lbl.setText("")

    def _update_estimate(self, *_):
        if not self.info or self.info.is_playlist:
            self.estimate_lbl.setText("")
            return
        size = self.info.estimate_size(self.collect_options())
        self.estimate_lbl.setText(f"Tamaño estimado: ~{format_bytes(size)}" if size else "")

    def collect_options(self) -> DownloadOptions:
        o = DownloadOptions()
        o.mode = "audio" if self.mode.index() == 1 else "video"
        o.video_container = self.container_combo.currentData()
        o.resolution = self.res_combo.currentData() or 0
        o.vcodec = self.vcodec_combo.currentData()
        o.fps_pref = self.fps_combo.currentData()
        o.audio_format = self.afmt_combo.currentData()
        o.audio_quality = self.aq_combo.currentData()
        if self.manual_switch.isChecked() and getattr(self, "_manual_selector", ""):
            o.format_override = self._manual_selector
        if self.range_switch.isChecked() and not self.slider.is_full() and self.info and not self.info.is_playlist:
            o.start, o.end = self.slider.values()
            if o.start <= 0.05:
                o.start = 0.0
            if o.end >= self.slider.maximum() - 0.05:
                o.end = None
            o.precise_cuts = self.precise_switch.isChecked()
        o.subtitles = self.subs_switch.isChecked()
        o.auto_subs = self.autosubs_switch.isChecked()
        o.embed_subs = self.embed_subs_switch.isChecked()
        o.sub_langs = self.sub_langs.text().strip() or "es,en"
        o.sub_format = self.sub_fmt.currentData()
        o.embed_thumbnail = self.embed_thumb_switch.isChecked()
        o.write_thumbnail = self.write_thumb_switch.isChecked()
        o.embed_metadata = self.embed_meta_switch.isChecked()
        o.embed_chapters = self.embed_chapters_switch.isChecked()
        o.split_chapters = self.split_chapters_switch.isChecked()
        o.write_description = self.write_desc_switch.isChecked()
        o.write_info_json = self.write_json_switch.isChecked()
        o.sponsorblock_remove = [k for k, sw in self.sb_switches.items() if sw.isChecked()]
        o.sponsorblock_mark = self.sb_mark_switch.isChecked()
        o.keep_original = self.keep_switch.isChecked()
        o.extra_args = self.extra_edit.text().strip()
        if self.info and self.info.is_playlist:
            idx = self._checked_indices()
            if len(idx) != self.playlist_list.count():
                o.playlist_items = _compress_indices(idx)
            o.playlist_reverse = self.reverse_switch.isChecked()
        return o

    def apply_options(self, o: DownloadOptions) -> None:
        self.mode.set_index(1 if o.mode == "audio" else 0, animate=False)
        self.mode_stack.setCurrentIndex(1 if o.mode == "audio" else 0)
        set_combo_data(self.container_combo, o.video_container)
        set_combo_data(self.res_combo, o.resolution)
        set_combo_data(self.vcodec_combo, o.vcodec)
        set_combo_data(self.fps_combo, o.fps_pref)
        set_combo_data(self.afmt_combo, o.audio_format)
        set_combo_data(self.aq_combo, o.audio_quality)
        self.precise_switch.setChecked(o.precise_cuts)
        self.subs_switch.setChecked(o.subtitles)
        self.autosubs_switch.setChecked(o.auto_subs)
        self.embed_subs_switch.setChecked(o.embed_subs)
        self.sub_langs.setText(o.sub_langs)
        set_combo_data(self.sub_fmt, o.sub_format)
        self.embed_thumb_switch.setChecked(o.embed_thumbnail)
        self.write_thumb_switch.setChecked(o.write_thumbnail)
        self.embed_meta_switch.setChecked(o.embed_metadata)
        self.embed_chapters_switch.setChecked(o.embed_chapters)
        self.split_chapters_switch.setChecked(o.split_chapters)
        self.write_desc_switch.setChecked(o.write_description)
        self.write_json_switch.setChecked(o.write_info_json)
        for k, sw in self.sb_switches.items():
            sw.setChecked(k in o.sponsorblock_remove)
        self.sb_mark_switch.setChecked(o.sponsorblock_mark)
        self.keep_switch.setChecked(o.keep_original)
        self.extra_edit.setText(o.extra_args)
        self._on_audio_format()
        self._on_mode(self.mode.index())

    def _save_defaults(self) -> None:
        opts = self.collect_options()
        opts.start = opts.end = None
        opts.playlist_items = ""
        opts.format_override = ""
        self.settings.defaults = opts
        self._save_settings()
        Toast.show_message(self.window(), "Opciones guardadas como predeterminadas.", "success")

    # ------------------------------------------------------------ salida
    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Carpeta de descargas", self.folder_edit.text())
        if folder:
            self.folder_edit.setText(folder)
            self._folder_edited()

    def _folder_edited(self) -> None:
        path = self.folder_edit.text().strip()
        if path and path != self.settings.output_dir:
            self.settings.output_dir = path
            self._save_settings()

    def refresh_from_settings(self) -> None:
        self.folder_edit.setText(self.settings.output_dir)

    def enqueue(self) -> None:
        if not self.info:
            return
        self._folder_edited()
        opts = self.collect_options()
        if self.info.is_playlist and not self._checked_indices():
            Toast.show_message(self.window(), "Selecciona al menos un elemento de la playlist.", "warning")
            return
        if opts.format_override == "" and self.manual_switch.isChecked():
            Toast.show_message(self.window(), "Selecciona un formato en la tabla o desactiva la selección manual.",
                               "warning")
            return
        count = len(self._checked_indices()) if self.info.is_playlist else 0
        task = DownloadTask(
            url=self.info.url if not self.info.url.startswith("ytsearch") else self.url_edit.text(),
            title=self.info.title,
            options=opts,
            thumbnail=ImageLoader.resolved(self.info.thumbnails),
            duration=self.info.duration,
            uploader=self.info.uploader,
            is_playlist=self.info.is_playlist,
            playlist_count=count,
        )
        self.preview.stop()
        self.manager.add(task)
        what = "MP3" if opts.mode == "audio" and opts.audio_format == "mp3" else (
            opts.audio_format.upper() if opts.mode == "audio" else opts.video_container.upper())
        Toast.show_message(self.window(), f"Añadido a la cola ({what}): {self.info.title}", "success")
        self.queued.emit()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(1200, 800)
