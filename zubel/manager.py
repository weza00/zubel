"""Cola de descargas con varias descargas simultáneas (un proceso yt-dlp por tarea)."""
from __future__ import annotations

import json
import shutil
import subprocess
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal

from zubel import deps, paths, ytdlp
from zubel.config import DownloadOptions, Settings, options_from_dict

QUEUED, RUNNING, PAUSED, DONE, ERROR, CANCELED = (
    "queued", "running", "paused", "done", "error", "canceled")
ACTIVE_STATES = (QUEUED, RUNNING)

STATUS_LABELS = {
    QUEUED: "En cola",
    RUNNING: "Descargando",
    PAUSED: "En pausa",
    DONE: "Completado",
    ERROR: "Error",
    CANCELED: "Cancelado",
}


@dataclass
class DownloadTask:
    url: str
    title: str
    options: DownloadOptions
    thumbnail: str | None = None
    duration: float | None = None
    uploader: str = ""
    is_playlist: bool = False
    playlist_count: int = 0
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: str = QUEUED
    created: float = field(default_factory=time.time)
    # Progreso (no persistente)
    fraction: float = 0.0
    speed: float | None = None
    eta: float | None = None
    downloaded: float | None = None
    total: float | None = None
    phase: str = ""
    item_index: int = 0  # elemento actual de la playlist
    files: list[str] = field(default_factory=list)
    error: str = ""
    log: list[str] = field(default_factory=list)

    @property
    def temp_dir(self) -> str:
        return str(paths.temp_root() / self.id)

    @property
    def status_label(self) -> str:
        return STATUS_LABELS.get(self.status, self.status)

    def to_dict(self) -> dict:
        data = asdict(self)
        for key in ("fraction", "speed", "eta", "downloaded", "total", "phase", "log", "item_index"):
            data.pop(key, None)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "DownloadTask":
        opts = options_from_dict(data.pop("options", None))
        allowed = {f for f in cls.__dataclass_fields__}
        task = cls(options=opts, **{k: v for k, v in data.items() if k in allowed and k != "options"})
        if task.status == RUNNING:
            task.status = QUEUED
        if task.status == DONE:
            task.fraction = 1.0
        return task


def _kill_tree(process: QProcess) -> None:
    pid = process.processId()
    if paths.IS_WINDOWS and pid:
        # yt-dlp lanza ffmpeg como proceso hijo; hay que matar el árbol completo.
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True,
                       creationflags=deps.NO_WINDOW)
    process.kill()


class DownloadManager(QObject):
    task_added = Signal(object)
    task_updated = Signal(object)
    task_removed = Signal(str)
    task_finished = Signal(object)  # completada o con error
    counts_changed = Signal(int, int)  # activas, total

    def __init__(self, settings: Settings, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.tasks: list[DownloadTask] = []
        self._procs: dict[str, QProcess] = {}
        self._buffers: dict[str, dict[str, str]] = {}
        self._stopping: set[str] = set()
        self._save_timer = QTimer(self, singleShot=True, interval=800)
        self._save_timer.timeout.connect(self.save)
        self._emit_timer: dict[str, float] = {}

    # -- persistencia ----------------------------------------------------------
    def load(self) -> None:
        try:
            data = json.loads(paths.queue_file().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for raw in data:
            try:
                task = DownloadTask.from_dict(raw)
            except TypeError:
                continue
            self.tasks.append(task)
            self.task_added.emit(task)
        self._schedule()
        self._emit_counts()

    def save(self) -> None:
        try:
            paths.queue_file().write_text(
                json.dumps([t.to_dict() for t in self.tasks], ensure_ascii=False, indent=1),
                encoding="utf-8")
        except OSError:
            pass

    def _changed(self, task: DownloadTask, throttle: bool = False) -> None:
        now = time.monotonic()
        if throttle and now - self._emit_timer.get(task.id, 0) < 0.12:
            return
        self._emit_timer[task.id] = now
        self.task_updated.emit(task)

    # -- API -------------------------------------------------------------------
    def get(self, task_id: str) -> DownloadTask | None:
        return next((t for t in self.tasks if t.id == task_id), None)

    def add(self, task: DownloadTask, start: bool = True) -> DownloadTask:
        task.status = QUEUED if start else PAUSED
        self.tasks.append(task)
        self.task_added.emit(task)
        self._after_change()
        return task

    def pause(self, task_id: str) -> None:
        task = self.get(task_id)
        if not task or task.status not in ACTIVE_STATES:
            return
        self._stop_process(task)
        task.status = PAUSED
        task.speed = task.eta = None
        self._changed(task)
        self._after_change()

    def resume(self, task_id: str) -> None:
        task = self.get(task_id)
        if not task or task.status not in (PAUSED, ERROR, CANCELED):
            return
        task.status = QUEUED
        task.error = ""
        self._changed(task)
        self._after_change()

    def retry(self, task_id: str) -> None:
        task = self.get(task_id)
        if task and task.status in (ERROR, CANCELED, DONE):
            task.fraction = 0.0
            task.files.clear()
            task.error = ""
            task.status = QUEUED
            self._changed(task)
            self._after_change()

    def cancel(self, task_id: str) -> None:
        task = self.get(task_id)
        if not task or task.status in (DONE, CANCELED):
            return
        self._stop_process(task)
        task.status = CANCELED
        task.speed = task.eta = None
        shutil.rmtree(task.temp_dir, ignore_errors=True)
        self._changed(task)
        self._after_change()

    def remove(self, task_id: str) -> None:
        task = self.get(task_id)
        if not task:
            return
        if task.status in ACTIVE_STATES or task.status == PAUSED:
            self._stop_process(task)
            shutil.rmtree(task.temp_dir, ignore_errors=True)
        self.tasks.remove(task)
        self.task_removed.emit(task_id)
        self._after_change()

    def clear_finished(self) -> None:
        for task in [t for t in self.tasks if t.status in (DONE, CANCELED)]:
            self.remove(task.id)

    def pause_all(self) -> None:
        for task in list(self.tasks):
            if task.status in ACTIVE_STATES:
                self.pause(task.id)

    def resume_all(self) -> None:
        for task in list(self.tasks):
            if task.status == PAUSED:
                self.resume(task.id)

    def active_count(self) -> int:
        return sum(1 for t in self.tasks if t.status in ACTIVE_STATES)

    def running_count(self) -> int:
        return len(self._procs)

    def shutdown(self) -> None:
        """Detiene todo al cerrar la app; lo que estaba activo se reanuda al volver."""
        for task in self.tasks:
            if task.id in self._procs:
                self._stop_process(task)
                task.status = QUEUED
        self.save()

    # -- internos --------------------------------------------------------------
    def _after_change(self) -> None:
        self._schedule()
        self._emit_counts()
        self._save_timer.start()

    def _emit_counts(self) -> None:
        self.counts_changed.emit(self.active_count(), len(self.tasks))

    def _schedule(self) -> None:
        limit = max(1, self.settings.max_concurrent)
        for task in self.tasks:
            if len(self._procs) >= limit:
                break
            if task.status == QUEUED and task.id not in self._procs:
                self._start(task)

    def _start(self, task: DownloadTask) -> None:
        exe = paths.ytdlp_path()
        if not exe.exists():
            task.status = ERROR
            task.error = "yt-dlp no está instalado. Ve a Ajustes → Componentes."
            self._changed(task)
            return
        try:
            Path(self.settings.output_dir).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            task.status = ERROR
            task.error = f"No se puede usar la carpeta de destino: {exc}"
            self._changed(task)
            return
        try:
            args = ytdlp.download_args(task.url, task.options, self.settings,
                                       task.is_playlist, task.temp_dir)
        except ValueError as exc:  # argumentos extra mal formados
            task.status = ERROR
            task.error = f"Argumentos extra inválidos: {exc}"
            self._changed(task)
            return

        self._clean_temp(task)
        proc = QProcess(self)
        env = QProcessEnvironment()
        for key, value in deps.subprocess_env().items():
            env.insert(key, value)
        proc.setProcessEnvironment(env)
        proc.setProgram(str(exe))
        proc.setArguments(args)
        self._procs[task.id] = proc
        self._buffers[task.id] = {"out": "", "err": ""}
        proc.readyReadStandardOutput.connect(lambda t=task, p=proc: self._read(t, p, "out"))
        proc.readyReadStandardError.connect(lambda t=task, p=proc: self._read(t, p, "err"))
        proc.finished.connect(lambda code, _status, t=task, p=proc: self._finished(t, p, code))
        proc.errorOccurred.connect(lambda err, t=task, p=proc: self._proc_error(t, p, err))

        task.status = RUNNING
        task.error = ""
        task.phase = "Iniciando…"
        task.log = [f"$ yt-dlp {' '.join(args)}"]
        task.item_index = 0
        self._changed(task)
        proc.start()

    @staticmethod
    def _clean_temp(task: DownloadTask) -> None:
        """Antes de (re)lanzar: conserva solo lo que sirve para reanudar (.part/.ytdl).

        Los restos de un post-procesado interrumpido hacen fallar a ffmpeg, y las
        descargas por rango (que usan ffmpeg) no pueden reanudarse de todos modos.
        """
        folder = Path(task.temp_dir)
        if not folder.exists():
            return
        if task.options.start is not None or task.options.end is not None:
            shutil.rmtree(folder, ignore_errors=True)
            return
        for item in folder.rglob("*"):
            if item.is_file() and not (item.name.endswith((".part", ".ytdl")) or ".part-Frag" in item.name):
                try:
                    item.unlink()
                except OSError:
                    pass

    def _stop_process(self, task: DownloadTask) -> None:
        proc = self._procs.pop(task.id, None)
        if proc is None:
            return
        self._stopping.add(task.id)
        _kill_tree(proc)
        proc.waitForFinished(3000)
        self._stopping.discard(task.id)
        proc.deleteLater()

    def _read(self, task: DownloadTask, proc: QProcess, channel: str) -> None:
        raw = proc.readAllStandardOutput() if channel == "out" else proc.readAllStandardError()
        buf = self._buffers.get(task.id)
        if buf is None:
            return
        text = buf[channel] + bytes(raw.data()).decode("utf-8", "replace")
        *lines, buf[channel] = text.replace("\r", "\n").split("\n")
        for line in lines:
            if line.strip():
                self._handle_line(task, line.rstrip())

    def _handle_line(self, task: DownloadTask, line: str) -> None:
        if (event := ytdlp.parse_progress(line)) is not None:
            if event.status == "downloading" and task.fraction >= 0.999 and (event.fraction or 0) < 0.5:
                task.item_index += 1  # empezó otro archivo (audio tras video o siguiente item)
            if event.fraction is not None:
                task.fraction = event.fraction
            task.speed = event.speed
            task.eta = event.eta
            task.downloaded = event.downloaded
            task.total = event.total
            labels = {"video": "Descargando video", "audio": "Descargando audio",
                      "video+audio": "Descargando"}
            task.phase = labels[event.stream] if event.status == "downloading" else "Procesando"
            self._changed(task, throttle=event.status == "downloading")
            return
        if (label := ytdlp.parse_postprocess(line)) is not None:
            task.phase = label
            task.speed = task.eta = None
            self._changed(task)
            return
        if line.startswith(ytdlp.FILE_PREFIX):
            path = line[len(ytdlp.FILE_PREFIX):].strip()
            if path and path not in task.files:
                task.files.append(path)
            self._changed(task)
            return
        task.log.append(line)
        if len(task.log) > 500:
            del task.log[1:100]
        if line.startswith("ERROR:"):
            task.error = line[6:].strip()

    def _proc_error(self, task: DownloadTask, proc: QProcess, err) -> None:
        if err == QProcess.ProcessError.FailedToStart:
            self._procs.pop(task.id, None)
            task.status = ERROR
            task.error = f"No se pudo iniciar yt-dlp: {proc.errorString()}"
            self._changed(task)
            self.task_finished.emit(task)
            self._after_change()

    def _finished(self, task: DownloadTask, proc: QProcess, code: int) -> None:
        if task.id in self._stopping or self._procs.get(task.id) is not proc:
            return
        for channel in ("out", "err"):
            rest = self._buffers.get(task.id, {}).get(channel, "")
            if rest.strip():
                self._handle_line(task, rest.strip())
        self._procs.pop(task.id, None)
        self._buffers.pop(task.id, None)
        proc.deleteLater()
        task.speed = task.eta = None
        if code == 0:
            task.status = DONE
            task.fraction = 1.0
            task.phase = ""
            task.error = ""
            shutil.rmtree(task.temp_dir, ignore_errors=True)
        else:
            task.status = ERROR
            if not task.error:
                tail = [l for l in task.log[1:] if l.strip()][-3:]
                task.error = " ".join(tail) or f"yt-dlp terminó con código {code}"
        self._changed(task)
        self.task_finished.emit(task)
        self._after_change()
