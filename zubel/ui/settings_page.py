"""Ajustes globales y gestión de componentes (yt-dlp, ffmpeg, deno)."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QLineEdit, QPushButton, QScrollArea, QSpinBox, QVBoxLayout,
    QWidget,
)

from zubel import __version__, config, deps, paths
from zubel.config import Settings
from zubel.ui import icons, theme
from zubel.ui.forms import combo, field, grid, set_combo_data
from zubel.ui.widgets import (
    LabeledSwitch, SmoothProgressBar, Toast, button, card, icon_button, label,
)
from zubel.workers import DepsWorker, VersionChecker


def section(title: str, icon_name: str, subtitle: str = "") -> tuple[QFrame, QVBoxLayout]:
    c = card()
    lay = QVBoxLayout(c)
    lay.setContentsMargins(20, 18, 20, 18)
    lay.setSpacing(12)
    head = QHBoxLayout()
    ic = label()
    ic.setPixmap(icons.pixmap(icon_name, theme.lighten(theme.ACCENT, 130), 18))
    head.addWidget(ic)
    head.addWidget(label(title, "h2"))
    head.addStretch(1)
    lay.addLayout(head)
    if subtitle:
        lay.addWidget(label(subtitle, "muted", wrap=True))
    return c, lay


class ComponentRow(QFrame):
    def __init__(self, comp: deps.Component) -> None:
        super().__init__()
        self.comp = comp
        self.setProperty("card", "inner")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(6)
        row = QHBoxLayout()
        ic = label()
        ic.setPixmap(icons.pixmap("package", theme.MUTED, 18))
        row.addWidget(ic)
        col = QVBoxLayout()
        col.setSpacing(1)
        name = comp.name + ("" if comp.required else "  (recomendado)")
        col.addWidget(label(name, "h3"))
        col.addWidget(label(comp.description, "subtle"))
        row.addLayout(col, 1)
        self.version = label("Comprobando…", "muted")
        row.addWidget(self.version)
        self.action = button("Actualizar", "refresh")
        row.addWidget(self.action)
        lay.addLayout(row)
        self.bar = SmoothProgressBar()
        self.bar.hide()
        lay.addWidget(self.bar)

    def set_versions(self, local: str, latest: str) -> None:
        if not local:
            self.version.setText("No instalado")
            self.version.setProperty("role", "error")
            self.action.setText("Instalar")
        elif latest and self.comp.key != "ffmpeg" and latest.lstrip("v") != local.lstrip("v"):
            self.version.setText(f"{local}  →  {latest} disponible")
            self.version.setProperty("role", "badge")
            self.action.setText("Actualizar")
        else:
            self.version.setText(local + ("  · al día" if latest else ""))
            self.version.setProperty("role", "success" if latest else "muted")
            self.action.setText("Reinstalar" if self.comp.key != "ffmpeg" else "Actualizar")
        theme.repolish(self.version)
        if not self.comp.url():
            self.action.setEnabled(False)
            self.action.setToolTip("Sin descarga automática en esta plataforma")


class SettingsPage(QWidget):
    accent_changed = Signal(str)
    settings_changed = Signal()

    def __init__(self, settings: Settings, save_settings, can_update) -> None:
        super().__init__()
        self.settings = settings
        self._save = save_settings
        self._can_update = can_update  # callable → bool (no hay descargas en curso)
        self._worker: DepsWorker | None = None
        self._checker: VersionChecker | None = None
        self._save_timer = QTimer(self, singleShot=True, interval=400)
        self._save_timer.timeout.connect(self._commit)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(32, 28, 32, 28)
        lay.setSpacing(18)
        lay.addWidget(label("Ajustes", "h1"))
        lay.addWidget(label("Los cambios se guardan automáticamente.", "muted"))

        lay.addWidget(self._general())
        lay.addWidget(self._downloads())
        lay.addWidget(self._network())
        lay.addWidget(self._interface())
        lay.addWidget(self._components())
        lay.addWidget(self._about())
        lay.addStretch(1)

    # ----------------------------------------------------------------- secciones
    def _general(self) -> QWidget:
        c, lay = section("Archivos", "folder", "Dónde y con qué nombre se guardan las descargas.")
        row = QHBoxLayout()
        self.out_edit = QLineEdit(self.settings.output_dir)
        self.out_edit.textChanged.connect(self._changed)
        row.addWidget(self.out_edit, 1)
        browse = icon_button("folder", "Elegir carpeta", "ghost")
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        holder = QWidget()
        row.setContentsMargins(0, 0, 0, 0)
        holder.setLayout(row)

        self.tpl_combo = combo([(f"{n}  —  {t}", t) for n, t in config.FILENAME_PRESETS], editable=True)
        set_combo_data(self.tpl_combo, self.settings.filename_template)
        self.tpl_combo.currentTextChanged.connect(self._changed)
        lay.addWidget(field("Carpeta de descargas", holder))
        lay.addWidget(field("Plantilla de nombre", self.tpl_combo,
                            "Usa campos de yt-dlp: %(title)s, %(uploader)s, %(id)s, %(upload_date)s, %(ext)s…"))
        self.sw_playlist_dir = LabeledSwitch("Crear carpeta por playlist", "Playlist/001 - Título.ext",
                                             self.settings.playlist_subfolder)
        self.sw_overwrite = LabeledSwitch("Sobrescribir archivos existentes", "", self.settings.overwrite)
        self.sw_restrict = LabeledSwitch("Nombres de archivo seguros", "Solo ASCII, sin espacios ni símbolos.",
                                         self.settings.restrict_filenames)
        self.sw_mtime = LabeledSwitch("Usar la fecha actual como fecha del archivo",
                                      "Si se desactiva se usa la fecha de publicación.", self.settings.no_mtime)
        self.sw_archive = LabeledSwitch("Registro de descargas (archive)",
                                        "Omite videos que ya descargaste antes; útil para playlists.",
                                        self.settings.use_archive)
        for sw in (self.sw_playlist_dir, self.sw_overwrite, self.sw_restrict, self.sw_mtime, self.sw_archive):
            sw.toggled.connect(self._changed)
            lay.addWidget(sw)
        return c

    def _downloads(self) -> QWidget:
        c, lay = section("Descargas", "download")
        self.spin_concurrent = QSpinBox()
        self.spin_concurrent.setRange(1, 10)
        self.spin_concurrent.setValue(self.settings.max_concurrent)
        self.spin_fragments = QSpinBox()
        self.spin_fragments.setRange(1, 32)
        self.spin_fragments.setValue(self.settings.concurrent_fragments)
        self.spin_retries = QSpinBox()
        self.spin_retries.setRange(0, 100)
        self.spin_retries.setValue(self.settings.retries)
        self.rate_edit = QLineEdit(self.settings.rate_limit)
        self.rate_edit.setPlaceholderText("Sin límite  (ej. 2M, 500K)")
        for w in (self.spin_concurrent, self.spin_fragments, self.spin_retries):
            w.valueChanged.connect(self._changed)
        self.rate_edit.textChanged.connect(self._changed)
        lay.addWidget(grid([
            field("Descargas simultáneas", self.spin_concurrent),
            field("Fragmentos en paralelo", self.spin_fragments, "Acelera descargas DASH/HLS."),
            field("Límite de velocidad por descarga", self.rate_edit),
            field("Reintentos", self.spin_retries),
        ]))
        self.sw_single = LabeledSwitch("Si el enlace tiene video y playlist, descargar solo el video", "",
                                       self.settings.prefer_single_video)
        self.sw_single.toggled.connect(self._changed)
        lay.addWidget(self.sw_single)
        return c

    def _network(self) -> QWidget:
        c, lay = section("Red y cuenta", "globe",
                         "Las cookies permiten descargar contenido con restricción de edad, privado o de miembros.")
        self.cookie_browser = combo([("No usar", "")] + [(b.capitalize(), b) for b in config.BROWSERS if b])
        set_combo_data(self.cookie_browser, self.settings.cookies_browser)
        self.cookie_browser.currentIndexChanged.connect(self._changed)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        self.cookie_file = QLineEdit(self.settings.cookies_file)
        self.cookie_file.setPlaceholderText("cookies.txt (formato Netscape)")
        self.cookie_file.textChanged.connect(self._changed)
        row.addWidget(self.cookie_file, 1)
        pick = icon_button("file", "Elegir archivo", "ghost")
        pick.clicked.connect(self._pick_cookies)
        row.addWidget(pick)
        holder = QWidget()
        holder.setLayout(row)
        self.proxy_edit = QLineEdit(self.settings.proxy)
        self.proxy_edit.setPlaceholderText("socks5://127.0.0.1:1080")
        self.ua_edit = QLineEdit(self.settings.user_agent)
        self.ua_edit.setPlaceholderText("Predeterminado de yt-dlp")
        self.geo_edit = QLineEdit(self.settings.geo_bypass_country)
        self.geo_edit.setPlaceholderText("Código de país, ej. US")
        self.geo_edit.setMaxLength(2)
        for w in (self.proxy_edit, self.ua_edit, self.geo_edit):
            w.textChanged.connect(self._changed)
        lay.addWidget(grid([
            field("Cookies del navegador", self.cookie_browser),
            field("Archivo de cookies", holder),
            field("Proxy", self.proxy_edit),
            field("User-Agent", self.ua_edit),
            field("Simular país (geo-bypass)", self.geo_edit),
        ]))
        self.sw_ipv4 = LabeledSwitch("Forzar IPv4", "", self.settings.force_ipv4)
        self.sw_ipv4.toggled.connect(self._changed)
        lay.addWidget(self.sw_ipv4)
        return c

    def _interface(self) -> QWidget:
        c, lay = section("Interfaz", "sliders")
        swatches = QHBoxLayout()
        swatches.setSpacing(8)
        self._swatch_btns: list[QPushButton] = []
        for color in theme.ACCENT_PRESETS:
            b = QPushButton()
            b.setFixedSize(QSize(30, 30))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setCheckable(True)
            b.setChecked(color.lower() == self.settings.accent.lower())
            b.setStyleSheet(
                f"QPushButton {{ background: {color}; border-radius: 15px; border: 2px solid transparent; }}"
                f"QPushButton:checked {{ border: 2px solid white; }}"
                f"QPushButton:hover {{ border: 2px solid {theme.alpha('#FFFFFF', 0.5)}; }}")
            b.clicked.connect(lambda _=False, col=color: self._set_accent(col))
            self._swatch_btns.append(b)
            swatches.addWidget(b)
        swatches.addStretch(1)
        holder = QWidget()
        swatches.setContentsMargins(0, 0, 0, 0)
        holder.setLayout(swatches)
        lay.addWidget(field("Color de acento", holder))
        self.sw_anim = LabeledSwitch("Animaciones", "", self.settings.animations)
        self.sw_clip = LabeledSwitch("Detectar enlaces del portapapeles",
                                     "Al volver a la app, pega automáticamente el enlace copiado.",
                                     self.settings.auto_paste_clipboard)
        self.sw_auto = LabeledSwitch("Analizar automáticamente al pegar", "", self.settings.auto_analyze)
        self.sw_notify = LabeledSwitch("Notificar al terminar cada descarga", "", self.settings.notify_on_finish)
        self.sw_open = LabeledSwitch("Abrir la carpeta al terminar", "", self.settings.open_folder_on_finish)
        for sw in (self.sw_anim, self.sw_clip, self.sw_auto, self.sw_notify, self.sw_open):
            sw.toggled.connect(self._changed)
            lay.addWidget(sw)
        return c

    def _components(self) -> QWidget:
        c, lay = section("Componentes", "package",
                         f"Se guardan dentro de la instalación del programa, en «{paths.bin_dir()}». "
                         "No se instala nada de forma global.")
        self.rows: dict[str, ComponentRow] = {}
        for key, comp in deps.COMPONENTS.items():
            row = ComponentRow(comp)
            row.action.clicked.connect(lambda _=False, k=key: self.install([k]))
            self.rows[key] = row
            lay.addWidget(row)
        bottom = QHBoxLayout()
        self.sw_autoupd = LabeledSwitch("Actualizar yt-dlp automáticamente al iniciar",
                                        "Los sitios cambian a menudo; tener yt-dlp al día evita errores.",
                                        self.settings.auto_update_ytdlp)
        self.sw_autoupd.toggled.connect(self._changed)
        bottom.addWidget(self.sw_autoupd, 1)
        check = button("Buscar actualizaciones", "refresh")
        check.clicked.connect(self.check_versions)
        bottom.addWidget(check)
        opn = icon_button("folder", "Abrir carpeta de componentes", "ghost")
        opn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(paths.bin_dir()))))
        bottom.addWidget(opn)
        lay.addLayout(bottom)
        return c

    def _about(self) -> QWidget:
        c, lay = section("Acerca de", "info")
        lay.addWidget(label(f"Zubel {__version__} — interfaz gráfica para yt-dlp.", wrap=True))
        lay.addWidget(label(
            "Descarga solo contenido que tengas derecho a descargar y respeta los términos de cada sitio. "
            "yt-dlp (Unlicense), FFmpeg (GPL) y Deno (MIT) se descargan desde sus repositorios oficiales.",
            "muted", wrap=True))
        links = QHBoxLayout()
        for text, url in (("yt-dlp", "https://github.com/yt-dlp/yt-dlp"),
                          ("Sitios compatibles", "https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md"),
                          ("FFmpeg", "https://ffmpeg.org"), ("Deno", "https://deno.com")):
            b = button(text, "external", "ghost")
            b.clicked.connect(lambda _=False, u=url: QDesktopServices.openUrl(QUrl(u)))
            links.addWidget(b)
        links.addStretch(1)
        lay.addLayout(links)
        return c

    # ------------------------------------------------------------------ lógica
    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Carpeta de descargas", self.out_edit.text())
        if folder:
            self.out_edit.setText(folder)

    def _pick_cookies(self) -> None:
        f, _ = QFileDialog.getOpenFileName(self, "Archivo de cookies", "", "Cookies (*.txt);;Todos (*)")
        if f:
            self.cookie_file.setText(f)

    def _set_accent(self, color: str) -> None:
        for b, col in zip(self._swatch_btns, theme.ACCENT_PRESETS):
            b.setChecked(col == color)
        self.settings.accent = color
        self._save()
        self.accent_changed.emit(color)

    def _changed(self, *_):
        self._save_timer.start()

    def _commit(self) -> None:
        s = self.settings
        s.output_dir = self.out_edit.text().strip() or str(paths.default_download_dir())
        tpl = self.tpl_combo.currentText().strip()
        data = self.tpl_combo.currentData()
        if data and tpl == self.tpl_combo.itemText(self.tpl_combo.currentIndex()):
            tpl = data
        s.filename_template = tpl or "%(title)s.%(ext)s"
        s.playlist_subfolder = self.sw_playlist_dir.isChecked()
        s.overwrite = self.sw_overwrite.isChecked()
        s.restrict_filenames = self.sw_restrict.isChecked()
        s.no_mtime = self.sw_mtime.isChecked()
        s.use_archive = self.sw_archive.isChecked()
        s.max_concurrent = self.spin_concurrent.value()
        s.concurrent_fragments = self.spin_fragments.value()
        s.retries = self.spin_retries.value()
        s.rate_limit = self.rate_edit.text().strip()
        s.prefer_single_video = self.sw_single.isChecked()
        s.cookies_browser = self.cookie_browser.currentData() or ""
        s.cookies_file = self.cookie_file.text().strip()
        s.proxy = self.proxy_edit.text().strip()
        s.user_agent = self.ua_edit.text().strip()
        s.geo_bypass_country = self.geo_edit.text().strip()
        s.force_ipv4 = self.sw_ipv4.isChecked()
        s.animations = self.sw_anim.isChecked()
        s.auto_paste_clipboard = self.sw_clip.isChecked()
        s.auto_analyze = self.sw_auto.isChecked()
        s.notify_on_finish = self.sw_notify.isChecked()
        s.open_folder_on_finish = self.sw_open.isChecked()
        s.auto_update_ytdlp = self.sw_autoupd.isChecked()
        self._save()
        self.settings_changed.emit()

    def refresh_from_settings(self) -> None:
        if self.out_edit.text() != self.settings.output_dir:
            self.out_edit.blockSignals(True)
            self.out_edit.setText(self.settings.output_dir)
            self.out_edit.blockSignals(False)

    # -------------------------------------------------------------- componentes
    def check_versions(self) -> None:
        if self._checker and self._checker.isRunning():
            return
        for row in self.rows.values():
            row.version.setText("Comprobando…")
            row.version.setProperty("role", "muted")
            theme.repolish(row.version)
        self._checker = VersionChecker(self)
        self._checker.result.connect(lambda k, local, latest: self.rows[k].set_versions(local, latest))
        self._checker.start()

    def install(self, keys: list[str], silent: bool = False) -> bool:
        if self._worker and self._worker.isRunning():
            return False
        if not self._can_update():
            if not silent:
                Toast.show_message(self.window(), "Espera a que terminen o pausa las descargas activas.", "warning")
            return False
        self._worker = DepsWorker(keys, self)
        self._worker.component_started.connect(self._on_started)
        self._worker.progress.connect(self._on_progress)
        self._worker.component_done.connect(self._on_done)
        self._worker.component_failed.connect(self._on_failed)
        self._worker.all_done.connect(lambda _ok: self.check_versions())
        self._worker.start()
        return True

    def _on_started(self, key: str) -> None:
        row = self.rows[key]
        row.action.setEnabled(False)
        row.bar.set_fraction(0)
        row.bar.show()
        row.version.setText("Descargando…")

    def _on_progress(self, key: str, done: int, total: int) -> None:
        row = self.rows[key]
        if total:
            row.bar.set_fraction(done / total)
            row.version.setText(f"Descargando… {done / 1048576:.0f} / {total / 1048576:.0f} MB")

    def _on_done(self, key: str, version: str) -> None:
        row = self.rows[key]
        row.bar.hide()
        row.action.setEnabled(True)
        Toast.show_message(self.window(), f"{row.comp.name} actualizado a {version}.", "success")

    def _on_failed(self, key: str, error: str) -> None:
        row = self.rows[key]
        row.bar.hide()
        row.action.setEnabled(True)
        Toast.show_message(self.window(), f"No se pudo instalar {row.comp.name}: {error}", "error", 6000)
