"""Ventana principal."""
from __future__ import annotations

import ctypes

from PySide6.QtCore import QByteArray, QEvent, Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QMainWindow, QMenu, QMessageBox, QSystemTrayIcon, QVBoxLayout, QWidget,
)

from zubel import __version__, config, paths
from zubel.config import Settings
from zubel.manager import DONE, ERROR, DownloadManager, DownloadTask
from zubel.ui import icons, theme, widgets
from zubel.ui.download_page import DownloadPage
from zubel.ui.queue_page import QueuePage, open_in_explorer
from zubel.ui.settings_page import SettingsPage
from zubel.ui.widgets import AnimatedStack, Sidebar, Toast, label
from zubel.workers import VersionChecker


def _dark_title_bar(win_id: int) -> None:
    """Barra de título oscura en Windows 10/11."""
    if not paths.IS_WINDOWS:
        return
    try:
        value = ctypes.c_int(1)
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (nuevo / antiguo)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    ctypes.c_void_p(win_id), attr, ctypes.byref(value), ctypes.sizeof(value)) == 0:
                break
        color = ctypes.c_int(0x00161410)  # BGR de theme.BG aprox.
        ctypes.windll.dwmapi.DwmSetWindowAttribute(ctypes.c_void_p(win_id), 35, ctypes.byref(color),
                                                   ctypes.sizeof(color))
    except (AttributeError, OSError):
        pass


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings
        widgets.ANIMATIONS_ENABLED = settings.animations
        self.setWindowTitle("Zubel")
        self.setWindowIcon(icons.app_icon())
        self.setMinimumSize(1080, 700)
        self.resize(1320, 860)
        if settings.window_geometry:
            self.restoreGeometry(QByteArray.fromBase64(settings.window_geometry.encode()))

        self.manager = DownloadManager(settings, self)
        self.manager.task_finished.connect(self._on_task_finished)
        self.manager.counts_changed.connect(self._on_counts)

        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        lay = QHBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.sidebar = Sidebar()
        brand = QWidget()
        bl = QHBoxLayout(brand)
        bl.setContentsMargins(6, 0, 0, 0)
        bl.setSpacing(10)
        logo = label()
        logo.setPixmap(icons.app_icon_pixmap(64, theme.ACCENT, theme.ACCENT_2).scaledToHeight(
            36, Qt.TransformationMode.SmoothTransformation))
        bl.addWidget(logo)
        names = QVBoxLayout()
        names.setSpacing(0)
        t = label("Zubel")
        t.setObjectName("Brand")
        s = label("para yt-dlp")
        s.setObjectName("BrandSub")
        names.addWidget(t)
        names.addWidget(s)
        bl.addLayout(names, 1)
        self.sidebar.add_header(brand)
        self.nav_download = self.sidebar.add_item("Nueva descarga", "download")
        self.nav_queue = self.sidebar.add_item("Descargas", "list")
        self.nav_settings = self.sidebar.add_item("Ajustes", "settings")
        self.sidebar.add_stretch()
        self.footer = label("", "subtle", wrap=True)
        self.footer.setContentsMargins(8, 0, 8, 0)
        self.sidebar.add_footer(self.footer)
        self.sidebar.add_footer(label(f"v{__version__}", "subtle"))
        lay.addWidget(self.sidebar)

        self.stack = AnimatedStack()
        self.download_page = DownloadPage(settings, self.manager, self.save_settings)
        self.queue_page = QueuePage(self.manager, settings)
        self.settings_page = SettingsPage(settings, self.save_settings,
                                          lambda: self.manager.running_count() == 0)
        for page in (self.download_page, self.queue_page, self.settings_page):
            self.stack.addWidget(page)
        lay.addWidget(self.stack, 1)

        self.sidebar.changed.connect(self.stack.slide_to)
        self.sidebar.changed.connect(self._on_page)
        self.sidebar.select(0, animate=False)
        self.download_page.queued.connect(self._pulse_queue)
        self.settings_page.settings_changed.connect(self._on_settings_changed)
        self.settings_page.accent_changed.connect(self._on_accent)

        for i in range(3):
            QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self, activated=lambda i=i: self.sidebar.select(i))
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self._focus_url)

        self._setup_tray()
        self._on_counts(0, 0)
        QTimer.singleShot(150, self._startup)

    # ---------------------------------------------------------------- arranque
    def _startup(self) -> None:
        if self.settings.auto_update_ytdlp and paths.ytdlp_path().exists():
            checker = VersionChecker(self, ["yt-dlp"])
            checker.result.connect(self._on_ytdlp_version)
            checker.finished.connect(checker.deleteLater)
            self._checker = checker
            self._load_fallback = QTimer(self, singleShot=True, interval=15000)
            self._load_fallback.timeout.connect(self._load_queue)
            self._load_fallback.start()
            checker.start()
        else:
            self._load_queue()
        if self.settings.check_updates_on_start:
            QTimer.singleShot(2500, self.settings_page.check_versions)

    def _on_ytdlp_version(self, _key: str, local: str, latest: str) -> None:
        if latest and local and latest > local and self.settings_page.install(["yt-dlp"], silent=True):
            Toast.show_message(self, f"Actualizando yt-dlp {local} → {latest}…", "info")
            self.settings_page._worker.all_done.connect(lambda _ok: self._load_queue())
        else:
            self._load_queue()

    def _load_queue(self) -> None:
        if getattr(self, "_queue_loaded", False):
            return
        self._queue_loaded = True
        if hasattr(self, "_load_fallback"):
            self._load_fallback.stop()
        self.manager.load()

    # ---------------------------------------------------------------- bandeja
    def _setup_tray(self) -> None:
        self.tray = None
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(icons.app_icon(), self)
        self.tray.setToolTip("Zubel")
        menu = QMenu()
        menu.addAction("Mostrar Zubel", self._restore)
        menu.addAction("Abrir carpeta de descargas", lambda: open_in_explorer(self.settings.output_dir))
        menu.addSeparator()
        menu.addAction("Salir", self.close)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda reason: self._restore() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.messageClicked.connect(lambda: (self._restore(), self.sidebar.select(1)))
        self.tray.show()

    def _restore(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    # ---------------------------------------------------------------- eventos
    def showEvent(self, e) -> None:  # noqa: N802
        super().showEvent(e)
        _dark_title_bar(int(self.winId()))

    def changeEvent(self, e) -> None:  # noqa: N802
        super().changeEvent(e)
        if e.type() == QEvent.Type.ActivationChange and self.isActiveWindow():
            if self.stack.currentIndex() == 0:
                QTimer.singleShot(100, self.download_page.check_clipboard)

    def closeEvent(self, e) -> None:  # noqa: N802
        if self.manager.running_count():
            box = QMessageBox(self)
            box.setWindowTitle("Descargas en curso")
            box.setText("Hay descargas en curso. Se pausarán y se reanudarán la próxima vez que abras Zubel.")
            box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
            box.button(QMessageBox.StandardButton.Yes).setText("Salir")
            box.button(QMessageBox.StandardButton.Cancel).setText("Cancelar")
            if box.exec() != QMessageBox.StandardButton.Yes:
                e.ignore()
                return
        self.download_page.preview.stop()
        self.download_page.fetcher.cancel()
        self.manager.shutdown()
        self.settings.window_geometry = bytes(self.saveGeometry().toBase64().data()).decode()
        self.save_settings()
        if self.tray:
            self.tray.hide()
        super().closeEvent(e)
        QApplication.quit()

    # ---------------------------------------------------------------- otros
    def save_settings(self) -> None:
        config.save_settings(self.settings)

    def _focus_url(self) -> None:
        self.sidebar.select(0)
        self.download_page.url_edit.setFocus()
        self.download_page.url_edit.selectAll()

    def _on_page(self, index: int) -> None:
        if index != 0:
            self.download_page.preview.stop()
        if index == 0:
            self.download_page.refresh_from_settings()
        elif index == 2:
            self.settings_page.refresh_from_settings()

    def _pulse_queue(self) -> None:
        self.nav_queue.set_badge(self.manager.active_count())

    def _on_counts(self, active: int, _total: int) -> None:
        self.nav_queue.set_badge(active)
        running = self.manager.running_count()
        if active:
            self.footer.setText(f"{running} descargando · {active - running} en espera")
        else:
            self.footer.setText("Sin descargas activas")

    def _on_settings_changed(self) -> None:
        widgets.ANIMATIONS_ENABLED = self.settings.animations
        self.download_page.refresh_from_settings()
        self.manager._schedule()
        self.queue_page._summary()

    def _on_accent(self, color: str) -> None:
        theme.apply(QApplication.instance(), color)
        self.sidebar._indicator.setStyleSheet(
            f"background: {theme.alpha(color, 0.16)}; border-radius: 10px; border-left: 3px solid {color};")
        self.update()
        for w in self.findChildren(QWidget):
            w.update()

    def _on_task_finished(self, task: DownloadTask) -> None:
        if task.status == DONE:
            if self.settings.notify_on_finish:
                if self.tray and not self.isActiveWindow():
                    self.tray.showMessage("Descarga completada", task.title, icons.app_icon(), 4000)
                else:
                    Toast.show_message(self, f"Completado: {task.title}", "success")
            if self.settings.open_folder_on_finish:
                open_in_explorer(task.files[-1] if task.files else self.settings.output_dir)
        elif task.status == ERROR:
            if self.tray and not self.isActiveWindow():
                self.tray.showMessage("Error en la descarga", task.title, QSystemTrayIcon.MessageIcon.Warning, 5000)
            else:
                Toast.show_message(self, f"Error: {task.error[:160]}", "error", 6000)
