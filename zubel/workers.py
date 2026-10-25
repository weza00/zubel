"""Tareas en segundo plano: análisis de URLs y descarga de componentes."""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QThread, Signal

from zubel import deps, paths, ytdlp
from zubel.config import Settings


class InfoFetcher(QObject):
    """Ejecuta ``yt-dlp -J`` sin bloquear la interfaz."""

    finished = Signal(object)  # MediaInfo
    failed = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._proc: QProcess | None = None
        self._url = ""

    def fetch(self, url: str, settings: Settings) -> None:
        self.cancel()
        if not paths.ytdlp_path().exists():
            self.failed.emit("yt-dlp no está instalado.")
            return
        self._url = url
        proc = QProcess(self)
        env = QProcessEnvironment()
        for k, v in deps.subprocess_env().items():
            env.insert(k, v)
        proc.setProcessEnvironment(env)
        proc.finished.connect(lambda code, _s, p=proc: self._done(p, code))
        proc.errorOccurred.connect(lambda _e, p=proc: self._error(p))
        self._proc = proc
        proc.start(str(paths.ytdlp_path()), ytdlp.info_args(url, settings))

    def cancel(self) -> None:
        if self._proc is not None:
            proc, self._proc = self._proc, None
            proc.kill()
            proc.waitForFinished(1000)
            proc.deleteLater()

    def _error(self, proc: QProcess) -> None:
        if proc is self._proc and proc.error() == QProcess.ProcessError.FailedToStart:
            self._proc = None
            self.failed.emit(f"No se pudo ejecutar yt-dlp: {proc.errorString()}")

    def _done(self, proc: QProcess, code: int) -> None:
        if proc is not self._proc:
            return
        self._proc = None
        out = bytes(proc.readAllStandardOutput().data()).decode("utf-8", "replace")
        err = bytes(proc.readAllStandardError().data()).decode("utf-8", "replace")
        proc.deleteLater()
        if code != 0 or not out.strip():
            lines = [l for l in err.splitlines() if l.strip()]
            msg = next((l[6:].strip() for l in reversed(lines) if l.startswith("ERROR:")), None)
            self.failed.emit(msg or (lines[-1] if lines else "No se pudo obtener información."))
            return
        try:
            self.finished.emit(ytdlp.info_from_json(out, self._url))
        except (ValueError, TypeError, KeyError) as exc:
            self.failed.emit(f"Respuesta inesperada de yt-dlp: {exc}")


class DepsWorker(QThread):
    """Instala/actualiza componentes en un hilo aparte."""

    component_started = Signal(str)
    progress = Signal(str, int, int)  # key, descargado, total
    component_done = Signal(str, str)  # key, versión
    component_failed = Signal(str, str)
    all_done = Signal(bool)

    def __init__(self, keys: list[str], parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.keys = keys
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:
        ok = True
        for key in self.keys:
            comp = deps.COMPONENTS[key]
            self.component_started.emit(key)
            try:
                deps.install(comp, lambda d, t, k=key: self.progress.emit(k, d, t), self._cancel)
                self.component_done.emit(key, comp.local_version() or "")
            except deps.Cancelled:
                self.all_done.emit(False)
                return
            except Exception as exc:  # noqa: BLE001 - se informa al usuario
                ok = ok and not comp.required
                self.component_failed.emit(key, str(exc))
        self.all_done.emit(ok)


class VersionChecker(QThread):
    """Consulta versiones local y remota de cada componente."""

    result = Signal(str, str, str)  # key, local, última

    def __init__(self, parent: QObject | None = None, keys: list[str] | None = None) -> None:
        super().__init__(parent)
        self.keys = keys or list(deps.COMPONENTS)

    def run(self) -> None:
        for key in self.keys:
            comp = deps.COMPONENTS[key]
            local = comp.local_version() or ""
            latest = deps.latest_release_tag(comp) or "" if comp.url() else ""
            self.result.emit(key, local, latest)
