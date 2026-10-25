"""Página de descargas: cola, progreso y acciones por tarea."""
from __future__ import annotations

import subprocess
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QPlainTextEdit, QScrollArea, QVBoxLayout, QWidget,
)

from zubel import paths
from zubel.config import AUDIO_QUALITIES, Settings
from zubel.manager import CANCELED, DONE, ERROR, PAUSED, QUEUED, RUNNING, DownloadManager, DownloadTask
from zubel.ui import icons, theme
from zubel.ui.widgets import (
    ImageLoader, SmoothProgressBar, button, card, duration, fade_in, icon_button, label, rounded,
)
from zubel.ytdlp import format_bytes, format_time

THUMB = QSize(144, 81)
STATUS_COLORS = {
    QUEUED: theme.MUTED, RUNNING: theme.ACCENT_2, PAUSED: theme.WARNING,
    DONE: theme.SUCCESS, ERROR: theme.ERROR, CANCELED: theme.SUBTLE,
}


def describe(task: DownloadTask) -> str:
    o = task.options
    if o.mode == "audio":
        fmt = "Audio original" if o.audio_format == "best" else o.audio_format.upper()
        q = next((t for t, v in AUDIO_QUALITIES if v == o.audio_quality), "")
        parts = [fmt] + ([q] if o.audio_format not in ("flac", "wav", "alac", "best") else [])
    else:
        parts = [o.video_container.upper(), f"{o.resolution}p" if o.resolution else "Mejor calidad"]
    if o.format_override:
        parts.append(f"-f {o.format_override}")
    if o.start is not None or o.end is not None:
        parts.append(f"{format_time(o.start or 0)}–{format_time(o.end if o.end is not None else task.duration)}")
    if task.is_playlist:
        parts.append(f"Playlist · {task.playlist_count or 'todos'} elementos")
    if o.subtitles or o.auto_subs:
        parts.append("Subtítulos")
    if o.sponsorblock_remove:
        parts.append("SponsorBlock")
    return "  ·  ".join(parts)


def open_in_explorer(path: str) -> None:
    p = Path(path)
    if paths.IS_WINDOWS and p.exists() and p.is_file():
        subprocess.Popen(["explorer", "/select,", str(p)])
        return
    target = p if p.is_dir() else p.parent
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))


class LogDialog(QDialog):
    def __init__(self, task: DownloadTask, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Registro — {task.title}")
        self.resize(860, 520)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setStyleSheet("font-family: Consolas, 'Cascadia Mono', monospace; font-size: 12px;")
        text.setPlainText("\n".join(task.log) or "Sin registro todavía.")
        lay.addWidget(text)
        close = button("Cerrar")
        close.clicked.connect(self.accept)
        lay.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)


class TaskCard(QFrame):
    def __init__(self, task: DownloadTask, manager: DownloadManager, settings: Settings) -> None:
        super().__init__()
        self.task = task
        self.manager = manager
        self.settings = settings
        self.setProperty("card", "true")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 12, 14, 12)
        lay.setSpacing(14)

        self.thumb = label()
        self.thumb.setFixedSize(THUMB)
        self.thumb.setPixmap(rounded(QPixmap(), THUMB, 8))
        lay.addWidget(self.thumb)
        ImageLoader.load(task.thumbnail, self._set_thumb)

        col = QVBoxLayout()
        col.setSpacing(5)
        top = QHBoxLayout()
        self.title = label(task.title, "h3")
        self.title.setMinimumWidth(100)
        top.addWidget(self.title, 1)
        self.status = label("")
        top.addWidget(self.status)
        col.addLayout(top)
        self.desc = label(describe(task), "subtle")
        col.addWidget(self.desc)
        self.bar = SmoothProgressBar()
        col.addWidget(self.bar)
        bottom = QHBoxLayout()
        self.stats = label("", "muted")
        bottom.addWidget(self.stats, 1)
        col.addLayout(bottom)
        lay.addLayout(col, 1)

        actions = QHBoxLayout()
        actions.setSpacing(2)
        self.pause_btn = icon_button("pause", "Pausar")
        self.pause_btn.clicked.connect(self._toggle_pause)
        self.retry_btn = icon_button("refresh", "Reintentar / descargar de nuevo")
        self.retry_btn.clicked.connect(lambda: manager.retry(task.id))
        self.folder_btn = icon_button("folder", "Mostrar en la carpeta")
        self.folder_btn.clicked.connect(self._open_folder)
        self.play_btn = icon_button("external", "Abrir archivo")
        self.play_btn.clicked.connect(self._open_file)
        self.log_btn = icon_button("terminal", "Ver registro de yt-dlp")
        self.log_btn.clicked.connect(lambda: LogDialog(self.task, self.window()).exec())
        self.cancel_btn = icon_button("x", "Cancelar", color=theme.ERROR)
        self.cancel_btn.clicked.connect(lambda: manager.cancel(task.id))
        self.remove_btn = icon_button("trash", "Quitar de la lista")
        self.remove_btn.clicked.connect(lambda: manager.remove(task.id))
        for b in (self.pause_btn, self.retry_btn, self.folder_btn, self.play_btn, self.log_btn,
                  self.cancel_btn, self.remove_btn):
            actions.addWidget(b)
        lay.addLayout(actions)
        self.refresh()

    def _set_thumb(self, pix: QPixmap) -> None:
        self.thumb.setPixmap(rounded(pix, THUMB, 8))

    def resizeEvent(self, e) -> None:  # noqa: N802
        super().resizeEvent(e)
        self._elide()

    def _elide(self) -> None:
        fm = self.title.fontMetrics()
        self.title.setText(fm.elidedText(self.task.title, Qt.TextElideMode.ElideRight,
                                         max(80, self.title.width())))
        self.title.setToolTip(self.task.title)

    def _toggle_pause(self) -> None:
        if self.task.status in (QUEUED, RUNNING):
            self.manager.pause(self.task.id)
        else:
            self.manager.resume(self.task.id)

    def _open_folder(self) -> None:
        if self.task.files and Path(self.task.files[-1]).exists():
            open_in_explorer(self.task.files[-1])
        else:
            open_in_explorer(self.settings.output_dir)

    def _open_file(self) -> None:
        if self.task.files:
            f = self.task.files[-1]
            if Path(f).exists():
                QDesktopServices.openUrl(QUrl.fromLocalFile(f))

    def refresh(self) -> None:
        t = self.task
        color = STATUS_COLORS.get(t.status, theme.MUTED)
        text = t.status_label
        if t.status == RUNNING and t.phase:
            text = t.phase
        self.status.setText(text)
        self.status.setStyleSheet(f"color: {color}; font-weight: 600;")
        state = {DONE: "done", ERROR: "error", PAUSED: "paused", CANCELED: "error"}.get(t.status, "")
        self.bar.set_state(state)
        self.bar.set_fraction(t.fraction)

        if t.status == RUNNING:
            bits = []
            if t.total:
                bits.append(f"{format_bytes(t.downloaded)} de {format_bytes(t.total)}")
            bits.append(f"{t.fraction * 100:.1f}%")
            if t.speed:
                bits.append(f"{format_bytes(t.speed)}/s")
            if t.eta is not None:
                bits.append(f"quedan {format_time(t.eta)}")
            if t.is_playlist and t.item_index:
                bits.append(f"archivo {t.item_index + 1}")
            self.stats.setText("  ·  ".join(bits))
            self.stats.setProperty("role", "muted")
        elif t.status == ERROR:
            self.stats.setText(t.error or "Error desconocido")
            self.stats.setProperty("role", "error")
        elif t.status == DONE:
            name = Path(t.files[-1]).name if t.files else "Listo"
            extra = f" (+{len(t.files) - 1} más)" if len(t.files) > 1 else ""
            self.stats.setText(name + extra)
            self.stats.setProperty("role", "success")
        elif t.status == PAUSED:
            self.stats.setText(f"{t.fraction * 100:.1f}% — pulsa reanudar para continuar")
            self.stats.setProperty("role", "muted")
        elif t.status == QUEUED:
            self.stats.setText("Esperando turno…")
            self.stats.setProperty("role", "muted")
        else:
            self.stats.setText("")
        theme.repolish(self.stats)
        self.stats.setWordWrap(t.status == ERROR)

        active = t.status in (QUEUED, RUNNING)
        self.pause_btn.setVisible(t.status in (QUEUED, RUNNING, PAUSED))
        self.pause_btn.setIcon(icons.icon("pause" if active else "play", theme.TEXT, 18))
        self.pause_btn.setToolTip("Pausar" if active else "Reanudar")
        self.retry_btn.setVisible(t.status in (ERROR, CANCELED, DONE))
        self.cancel_btn.setVisible(t.status in (QUEUED, RUNNING, PAUSED))
        self.remove_btn.setVisible(t.status in (DONE, ERROR, CANCELED))
        self.play_btn.setVisible(t.status == DONE and bool(t.files))
        self.folder_btn.setVisible(t.status in (DONE, RUNNING))


class QueuePage(QWidget):
    def __init__(self, manager: DownloadManager, settings: Settings) -> None:
        super().__init__()
        self.manager = manager
        self.settings = settings
        self.cards: dict[str, TaskCard] = {}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 28, 32, 20)
        outer.setSpacing(14)
        head = QHBoxLayout()
        titles = QVBoxLayout()
        titles.addWidget(label("Descargas", "h1"))
        self.summary = label("", "muted")
        titles.addWidget(self.summary)
        head.addLayout(titles, 1)
        self.pause_all = button("Pausar todo", "pause", "ghost")
        self.pause_all.clicked.connect(manager.pause_all)
        self.resume_all = button("Reanudar todo", "play", "ghost")
        self.resume_all.clicked.connect(manager.resume_all)
        self.clear_btn = button("Limpiar terminadas", "trash", "ghost")
        self.clear_btn.clicked.connect(manager.clear_finished)
        folder = button("Abrir carpeta", "folder")
        folder.clicked.connect(lambda: open_in_explorer(settings.output_dir))
        for b in (self.pause_all, self.resume_all, self.clear_btn, folder):
            head.addWidget(b, 0, Qt.AlignmentFlag.AlignBottom)
        outer.addLayout(head)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        self.list_lay = QVBoxLayout(body)
        self.list_lay.setContentsMargins(0, 4, 6, 4)
        self.list_lay.setSpacing(10)
        self.list_lay.addStretch(1)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        self.empty = card()
        el = QVBoxLayout(self.empty)
        el.setContentsMargins(30, 60, 30, 60)
        ic = label()
        ic.setPixmap(icons.pixmap("list", theme.SUBTLE, 44))
        ic.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.addWidget(ic)
        t = label("No hay descargas todavía", "h2")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.addWidget(t)
        s = label("Lo que añadas desde «Nueva descarga» aparecerá aquí. Puedes tener varias a la vez.", "muted")
        s.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.addWidget(s)
        self.list_lay.insertWidget(0, self.empty)

        manager.task_added.connect(self._add)
        manager.task_updated.connect(self._update)
        manager.task_removed.connect(self._remove)
        manager.counts_changed.connect(self._summary)
        self._summary()

    def _add(self, task: DownloadTask) -> None:
        c = TaskCard(task, self.manager, self.settings)
        self.cards[task.id] = c
        c.hide()
        self.list_lay.insertWidget(self.list_lay.count() - 1, c)
        fade_in(c, 320)
        self._summary()

    def _update(self, task: DownloadTask) -> None:
        c = self.cards.get(task.id)
        if c:
            c.refresh()
        self._summary()

    def _remove(self, task_id: str) -> None:
        c = self.cards.pop(task_id, None)
        if not c:
            return
        anim = QPropertyAnimation(c, b"maximumHeight", c)
        anim.setDuration(duration(220))
        anim.setStartValue(c.height())
        anim.setEndValue(0)
        anim.setEasingCurve(QEasingCurve.Type.InCubic)
        anim.finished.connect(c.deleteLater)
        anim.start()
        self._summary()

    def _summary(self, *_):
        tasks = self.manager.tasks
        running = sum(1 for t in tasks if t.status == RUNNING)
        queued = sum(1 for t in tasks if t.status == QUEUED)
        done = sum(1 for t in tasks if t.status == DONE)
        errors = sum(1 for t in tasks if t.status == ERROR)
        parts = [f"{running} descargando", f"{queued} en cola", f"{done} completadas"]
        if errors:
            parts.append(f"{errors} con error")
        parts.append(f"máx. {self.settings.max_concurrent} simultáneas")
        self.summary.setText("  ·  ".join(parts))
        self.empty.setVisible(not tasks)
        self.clear_btn.setEnabled(any(t.status in (DONE, CANCELED) for t in tasks))
