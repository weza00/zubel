"""Asistente que descarga yt-dlp, FFmpeg y Deno en la carpeta del programa.

Se muestra en la primera ejecución y lo lanza el instalador (``--install-deps``).
"""
from __future__ import annotations


from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QVBoxLayout, QWidget

from zubel import deps, paths
from zubel.ui import icons, theme
from zubel.ui.widgets import SmoothProgressBar, Spinner, button, label
from zubel.workers import DepsWorker


class _Row(QFrame):
    def __init__(self, comp: deps.Component) -> None:
        super().__init__()
        self.setProperty("card", "inner")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 12)
        lay.setSpacing(6)
        top = QHBoxLayout()
        self.icon = label()
        self.icon.setPixmap(icons.pixmap("package", theme.MUTED, 18))
        top.addWidget(self.icon)
        top.addWidget(label(comp.name, "h3"))
        top.addWidget(label(comp.description, "subtle"), 1)
        self.spinner = Spinner(16, 2)
        top.addWidget(self.spinner)
        self.status = label("En espera", "muted")
        top.addWidget(self.status)
        lay.addLayout(top)
        self.bar = SmoothProgressBar()
        lay.addWidget(self.bar)

    def set_state(self, state: str, text: str = "") -> None:
        if state == "running":
            self.spinner.start()
        else:
            self.spinner.stop()
        color = {"done": theme.SUCCESS, "error": theme.ERROR}.get(state, theme.MUTED)
        name = {"done": "check", "error": "alert"}.get(state, "package")
        self.icon.setPixmap(icons.pixmap(name, color, 18))
        if state == "done":
            self.bar.set_state("done")
            self.bar.set_fraction(1)
        elif state == "error":
            self.bar.set_state("error")
        self.status.setText(text)


class SetupDialog(QDialog):
    def __init__(self, keys: list[str] | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Zubel — preparando componentes")
        self.setWindowIcon(icons.app_icon())
        self.setMinimumWidth(620)
        self.keys = keys or [c.key for c in deps.missing_components()]
        self._ok = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 26, 28, 22)
        lay.setSpacing(14)
        head = QHBoxLayout()
        logo = label()
        logo.setPixmap(icons.app_icon_pixmap(56, theme.ACCENT, theme.ACCENT_2))
        head.addWidget(logo)
        titles = QVBoxLayout()
        titles.addWidget(label("Preparando Zubel", "h1"))
        titles.addWidget(label("Descargando las últimas versiones desde los repositorios oficiales.", "muted"))
        head.addLayout(titles, 1)
        lay.addLayout(head)

        self.rows: dict[str, _Row] = {}
        for key in self.keys:
            row = _Row(deps.COMPONENTS[key])
            self.rows[key] = row
            lay.addWidget(row)
        lay.addWidget(label(f"Destino: {paths.bin_dir()}", "subtle", wrap=True))
        self.error = label("", "error", wrap=True)
        self.error.hide()
        lay.addWidget(self.error)

        actions = QHBoxLayout()
        actions.addStretch(1)
        self.cancel_btn = button("Cancelar", variant="ghost")
        self.cancel_btn.clicked.connect(self._cancel)
        self.retry_btn = button("Reintentar", "refresh")
        self.retry_btn.clicked.connect(self.start)
        self.retry_btn.hide()
        self.continue_btn = button("Continuar", "check", "primary")
        self.continue_btn.clicked.connect(self.accept)
        self.continue_btn.hide()
        actions.addWidget(self.cancel_btn)
        actions.addWidget(self.retry_btn)
        actions.addWidget(self.continue_btn)
        lay.addLayout(actions)
        self.worker: DepsWorker | None = None

    def showEvent(self, e) -> None:  # noqa: N802
        super().showEvent(e)
        if self.worker is None:
            self.start()

    def start(self) -> None:
        pending = [k for k in self.keys if not deps.COMPONENTS[k].installed()] or self.keys
        self.error.hide()
        self.retry_btn.hide()
        self.worker = DepsWorker(pending, self)
        self.worker.component_started.connect(lambda k: self.rows[k].set_state("running", "Conectando…"))
        self.worker.progress.connect(self._progress)
        self.worker.component_done.connect(lambda k, v: self.rows[k].set_state("done", v or "Listo"))
        self.worker.component_failed.connect(self._failed)
        self.worker.all_done.connect(self._finished)
        self.worker.start()

    def _progress(self, key: str, done: int, total: int) -> None:
        row = self.rows[key]
        if total:
            row.bar.set_fraction(done / total)
            row.status.setText(f"{done / 1048576:.1f} / {total / 1048576:.1f} MB")
        else:
            row.status.setText(f"{done / 1048576:.1f} MB")

    def _failed(self, key: str, message: str) -> None:
        self.rows[key].set_state("error", "Error")
        self.error.setText(f"{deps.COMPONENTS[key].name}: {message}")
        self.error.show()

    def _finished(self, ok: bool) -> None:
        self._ok = ok and not deps.missing_components(include_optional=False)
        if self._ok:
            self.cancel_btn.hide()
            self.continue_btn.show()
            self.continue_btn.setFocus()
        else:
            self.retry_btn.show()

    def _cancel(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(5000)
        self.reject()

    def closeEvent(self, e) -> None:  # noqa: N802
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(5000)
        super().closeEvent(e)
