"""Widgets personalizados y animados."""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import (
    QAbstractAnimation, QEasingCurve, QParallelAnimationGroup, QPoint, QPointF, QPropertyAnimation,
    QRectF, QSize, Qt, QTimer, QUrl, QVariantAnimation, Property, Signal,
)
from PySide6.QtGui import (
    QBrush, QColor, QFont, QImage, QLinearGradient, QMouseEvent, QPainter, QPainterPath, QPen,
    QPixmap,
)
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QAbstractButton, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QProgressBar,
    QPushButton, QSizePolicy, QStackedWidget, QToolButton, QVBoxLayout, QWidget,
)

from zubel.ui import icons, theme
from zubel.ytdlp import format_time

ANIMATIONS_ENABLED = True


def duration(ms: int) -> int:
    return ms if ANIMATIONS_ENABLED else 0


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------
def label(text: str = "", role: str | None = None, wrap: bool = False) -> QLabel:
    lbl = QLabel(text)
    if role:
        lbl.setProperty("role", role)
    lbl.setWordWrap(wrap)
    return lbl


def card(inner: bool = False) -> QFrame:
    frame = QFrame()
    frame.setProperty("card", "inner" if inner else "true")
    return frame


def icon_button(name: str, tooltip: str = "", variant: str = "icon", size: int = 18,
                color: str = theme.TEXT) -> QToolButton:
    btn = QToolButton()
    btn.setIcon(icons.icon(name, color, size))
    btn.setIconSize(QSize(size, size))
    btn.setToolTip(tooltip)
    btn.setProperty("variant", variant)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    return btn


def button(text: str, icon_name: str | None = None, variant: str | None = None,
           size: str | None = None, icon_color: str | None = None) -> QPushButton:
    btn = QPushButton(text)
    if icon_name:
        color = icon_color or ("#FFFFFF" if variant == "primary" else theme.TEXT)
        btn.setIcon(icons.icon(icon_name, color, 18 if size == "lg" else 16))
    if variant:
        btn.setProperty("variant", variant)
    if size:
        btn.setProperty("size", size)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    return btn


def fade_in(widget: QWidget, ms: int = 260, offset: int = 0) -> None:
    """Aparición suave. El efecto se elimina al terminar para no anidar efectos."""
    if not ANIMATIONS_ENABLED:
        widget.show()
        return
    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(0.0)
    widget.setGraphicsEffect(effect)
    widget.show()
    anim = QPropertyAnimation(effect, b"opacity", widget)
    anim.setDuration(ms)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)
    anim.finished.connect(lambda: widget.setGraphicsEffect(None))
    anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)


def rounded(pixmap: QPixmap, size: QSize, radius: float, cover: bool = True) -> QPixmap:
    dpr = 2.0
    out = QPixmap(size * dpr)
    out.setDevicePixelRatio(dpr)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size.width(), size.height()), radius, radius)
    p.setClipPath(path)
    p.fillPath(path, QColor(theme.SURFACE_3))
    if not pixmap.isNull():
        mode = Qt.AspectRatioMode.KeepAspectRatioByExpanding if cover else Qt.AspectRatioMode.KeepAspectRatio
        scaled = pixmap.scaled(size * dpr, mode, Qt.TransformationMode.SmoothTransformation)
        scaled.setDevicePixelRatio(dpr)
        w, h = scaled.width() / dpr, scaled.height() / dpr
        p.drawPixmap(QPointF((size.width() - w) / 2, (size.height() - h) / 2), scaled)
    p.end()
    return out


# ---------------------------------------------------------------------------
# Carga de imágenes remotas (miniaturas)
# ---------------------------------------------------------------------------
class ImageLoader:
    """Descarga imágenes con caché. Acepta varias URL y usa la primera que funcione."""

    _manager: QNetworkAccessManager | None = None
    _cache: dict[str, QPixmap] = {}
    _resolved: dict[str, str] = {}  # primera URL de la lista → URL que funcionó
    _pending: dict[str, list[Callable[[QPixmap], None]]] = {}

    @classmethod
    def resolved(cls, urls: str | list[str] | None) -> str | None:
        urls = [urls] if isinstance(urls, str) else list(urls or [])
        return cls._resolved.get(urls[0], urls[0]) if urls else None

    @classmethod
    def load(cls, urls: str | list[str] | None, callback: Callable[[QPixmap], None]) -> None:
        urls = [urls] if isinstance(urls, str) else [u for u in (urls or []) if u]
        if not urls:
            return
        key = urls[0]
        if key in cls._cache:
            callback(cls._cache[key])
            return
        if key in cls._pending:
            cls._pending[key].append(callback)
            return
        if cls._manager is None:
            cls._manager = QNetworkAccessManager()
        cls._pending[key] = [callback]
        cls._request(key, urls)

    @classmethod
    def _request(cls, key: str, urls: list[str]) -> None:
        req = QNetworkRequest(QUrl(urls[0]))
        req.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                         QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
        req.setHeader(QNetworkRequest.KnownHeaders.UserAgentHeader, "Mozilla/5.0 Zubel")
        reply = cls._manager.get(req)
        reply.finished.connect(lambda r=reply: cls._finished(key, urls, r))

    @classmethod
    def _finished(cls, key: str, urls: list[str], reply: QNetworkReply) -> None:
        pix = QPixmap()
        if reply.error() == QNetworkReply.NetworkError.NoError:
            pix.loadFromData(reply.readAll())
        reply.deleteLater()
        if pix.isNull() and len(urls) > 1:
            cls._request(key, urls[1:])
            return
        if not pix.isNull():
            cls._cache[key] = pix
            cls._resolved[key] = urls[0]
        for cb in cls._pending.pop(key, []):
            if not pix.isNull():
                try:
                    cb(pix)
                except RuntimeError:  # el widget destino ya no existe
                    pass


# ---------------------------------------------------------------------------
# Interruptor animado
# ---------------------------------------------------------------------------
class ToggleSwitch(QAbstractButton):
    def __init__(self, checked: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(40, 22)
        self._offset = 1.0 if checked else 0.0
        self._anim = QPropertyAnimation(self, b"offset", self)
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate)

    def _animate(self, checked: bool) -> None:
        self._anim.stop()
        self._anim.setDuration(duration(180))
        self._anim.setStartValue(self._offset)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def get_offset(self) -> float:
        return self._offset

    def set_offset(self, value: float) -> None:
        self._offset = value
        self.update()

    offset = Property(float, get_offset, set_offset)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(40, 22)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        off = QColor(theme.SURFACE_3)
        on = QColor(theme.ACCENT)
        t = self._offset
        bg = QColor(
            int(off.red() + (on.red() - off.red()) * t),
            int(off.green() + (on.green() - off.green()) * t),
            int(off.blue() + (on.blue() - off.blue()) * t),
        )
        if not self.isEnabled():
            bg.setAlpha(110)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        d = r.height() - 6
        x = r.left() + 3 + (r.width() - d - 6) * t
        p.setBrush(QColor("white"))
        p.drawEllipse(QRectF(x, r.top() + 3, d, d))


class LabeledSwitch(QWidget):
    """Interruptor con texto y descripción opcional."""

    toggled = Signal(bool)

    def __init__(self, text: str, description: str = "", checked: bool = False) -> None:
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setSpacing(12)
        col = QVBoxLayout()
        col.setSpacing(1)
        self.title = label(text)
        col.addWidget(self.title)
        if description:
            col.addWidget(label(description, "subtle", wrap=True))
        lay.addLayout(col, 1)
        self.switch = ToggleSwitch(checked)
        self.switch.toggled.connect(self.toggled)
        lay.addWidget(self.switch, 0, Qt.AlignmentFlag.AlignVCenter)

    def isChecked(self) -> bool:  # noqa: N802
        return self.switch.isChecked()

    def setChecked(self, value: bool) -> None:  # noqa: N802
        self.switch.blockSignals(True)
        self.switch.setChecked(value)
        self.switch.set_offset(1.0 if value else 0.0)
        self.switch.blockSignals(False)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self.isEnabled() and event.button() == Qt.MouseButton.LeftButton:
            self.switch.toggle()


# ---------------------------------------------------------------------------
# Spinner de carga
# ---------------------------------------------------------------------------
class Spinner(QWidget):
    def __init__(self, size: int = 22, width: float = 2.6, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._width = width
        self._angle = 0
        self._timer = QTimer(self, interval=16)
        self._timer.timeout.connect(self._tick)
        self.hide()

    def _tick(self) -> None:
        self._angle = (self._angle + 7) % 360
        self.update()

    def start(self) -> None:
        self.show()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        m = self._width
        r = QRectF(m, m, self.width() - 2 * m, self.height() - 2 * m)
        p.setPen(QPen(QColor(theme.SURFACE_3), self._width))
        p.drawEllipse(r)
        pen = QPen(QColor(theme.ACCENT), self._width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawArc(r, -self._angle * 16, 100 * 16)


# ---------------------------------------------------------------------------
# Barra de progreso con animación suave
# ---------------------------------------------------------------------------
class SmoothProgressBar(QProgressBar):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setRange(0, 1000)
        self.setTextVisible(False)
        self.setFixedHeight(8)
        self._anim = QPropertyAnimation(self, b"value", self)
        self._anim.setDuration(350)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def set_fraction(self, fraction: float) -> None:
        target = int(max(0.0, min(1.0, fraction)) * 1000)
        if target == self._anim.endValue() and self._anim.state() == QAbstractAnimation.State.Running:
            return
        if target < self.value() - 50 or not ANIMATIONS_ENABLED:
            self._anim.stop()
            self.setValue(target)
            return
        self._anim.stop()
        self._anim.setStartValue(self.value())
        self._anim.setEndValue(target)
        self._anim.start()

    def set_state(self, state: str) -> None:
        if self.property("state") != state:
            self.setProperty("state", state)
            theme.repolish(self)


# ---------------------------------------------------------------------------
# Control segmentado (Video | Audio) con píldora animada
# ---------------------------------------------------------------------------
class SegmentedControl(QWidget):
    changed = Signal(int)

    def __init__(self, items: list[tuple[str, str]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._items = items
        self._index = 0
        self._pill_x = 0.0
        self._hover = -1
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(42)
        self.setMinimumWidth(110 * len(items))
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(260)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._set_pill)

    def _set_pill(self, value) -> None:
        self._pill_x = float(value)
        self.update()

    def index(self) -> int:
        return self._index

    def set_index(self, index: int, animate: bool = True) -> None:
        if index == self._index and self._pill_x == index:
            return
        self._index = index
        if animate and ANIMATIONS_ENABLED:
            self._anim.stop()
            self._anim.setStartValue(self._pill_x)
            self._anim.setEndValue(float(index))
            self._anim.start()
        else:
            self._pill_x = float(index)
            self.update()
        self.changed.emit(index)

    def _seg_width(self) -> float:
        return (self.width() - 8) / len(self._items)

    def mouseMoveEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        hover = int((e.position().x() - 4) // self._seg_width())
        if hover != self._hover:
            self._hover = hover
            self.update()

    def leaveEvent(self, _e) -> None:  # noqa: N802
        self._hover = -1
        self.update()

    def mousePressEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        idx = int((e.position().x() - 4) // self._seg_width())
        if 0 <= idx < len(self._items) and idx != self._index:
            self.set_index(idx)

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(theme.BORDER), 1))
        p.setBrush(QColor(theme.SURFACE_2))
        p.drawRoundedRect(r, 11, 11)
        w = self._seg_width()
        pill = QRectF(4 + self._pill_x * w, 4, w, self.height() - 8)
        grad = QLinearGradient(pill.topLeft(), pill.bottomRight())
        grad.setColorAt(0, QColor(theme.ACCENT))
        grad.setColorAt(1, QColor(theme.lighten(theme.ACCENT, 118)))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        p.drawRoundedRect(pill, 8, 8)
        font = QFont(self.font())
        font.setWeight(QFont.Weight.DemiBold)
        p.setFont(font)
        for i, (text, icon_name) in enumerate(self._items):
            seg = QRectF(4 + i * w, 4, w, self.height() - 8)
            active = abs(self._pill_x - i) < 0.5
            color = "#FFFFFF" if active else (theme.TEXT if i == self._hover else theme.MUTED)
            fm = p.fontMetrics()
            tw = fm.horizontalAdvance(text) + 24
            x = seg.center().x() - tw / 2
            p.drawPixmap(QPointF(x, seg.center().y() - 8), icons.pixmap(icon_name, color, 16))
            p.setPen(QColor(color))
            p.drawText(QRectF(x + 24, seg.top(), tw, seg.height()),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)


# ---------------------------------------------------------------------------
# Pila de páginas con transición deslizante
# ---------------------------------------------------------------------------
class AnimatedStack(QStackedWidget):
    def slide_to(self, index: int) -> None:
        if index == self.currentIndex():
            return
        direction = 1 if index > self.currentIndex() else -1
        new = self.widget(index)
        self.setCurrentIndex(index)
        if not ANIMATIONS_ENABLED:
            return
        effect = QGraphicsOpacityEffect(new)
        new.setGraphicsEffect(effect)
        end = new.pos()
        start = end + QPoint(0, 28 * direction)
        group = QParallelAnimationGroup(self)
        pos = QPropertyAnimation(new, b"pos")
        pos.setDuration(320)
        pos.setStartValue(start)
        pos.setEndValue(end)
        pos.setEasingCurve(QEasingCurve.Type.OutCubic)
        op = QPropertyAnimation(effect, b"opacity")
        op.setDuration(280)
        op.setStartValue(0.0)
        op.setEndValue(1.0)
        group.addAnimation(pos)
        group.addAnimation(op)
        group.finished.connect(lambda: (new.setGraphicsEffect(None), new.move(end)))
        group.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)


# ---------------------------------------------------------------------------
# Barra lateral con indicador deslizante
# ---------------------------------------------------------------------------
class NavButton(QAbstractButton):
    def __init__(self, text: str, icon_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setText(text)
        self.icon_name = icon_name
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(42)
        self.badge = 0
        self._hover = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(160)
        self._anim.valueChanged.connect(self._set_hover)

    def _set_hover(self, v) -> None:
        self._hover = float(v)
        self.update()

    def enterEvent(self, _e) -> None:  # noqa: N802
        self._anim.stop()
        self._anim.setStartValue(self._hover)
        self._anim.setEndValue(1.0)
        self._anim.start()

    def leaveEvent(self, _e) -> None:  # noqa: N802
        self._anim.stop()
        self._anim.setStartValue(self._hover)
        self._anim.setEndValue(0.0)
        self._anim.start()

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._hover > 0 and not self.isChecked():
            c = QColor(theme.SURFACE_2)
            c.setAlphaF(self._hover)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c)
            p.drawRoundedRect(QRectF(self.rect()), 10, 10)
        active = self.isChecked()
        color = theme.TEXT if active else (theme.TEXT if self._hover > 0.5 else theme.MUTED)
        p.drawPixmap(QPointF(16, (self.height() - 18) / 2), icons.pixmap(
            self.icon_name, theme.lighten(theme.ACCENT, 140) if active else color, 18))
        font = QFont(self.font())
        font.setWeight(QFont.Weight.DemiBold if active else QFont.Weight.Medium)
        p.setFont(font)
        p.setPen(QColor(color))
        p.drawText(QRectF(46, 0, self.width() - 46, self.height()),
                   Qt.AlignmentFlag.AlignVCenter, self.text())
        if self.badge:
            text = str(self.badge) if self.badge < 100 else "99+"
            w = max(20, p.fontMetrics().horizontalAdvance(text) + 12)
            r = QRectF(self.width() - w - 12, (self.height() - 20) / 2, w, 20)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(theme.ACCENT))
            p.drawRoundedRect(r, 10, 10)
            p.setPen(QColor("white"))
            small = QFont(font)
            small.setPointSizeF(font.pointSizeF() * 0.85)
            small.setWeight(QFont.Weight.Bold)
            p.setFont(small)
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, text)

    def set_badge(self, n: int) -> None:
        self.badge = n
        self.update()


class Sidebar(QFrame):
    changed = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(220)
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(12, 18, 12, 14)
        self._lay.setSpacing(4)
        self.buttons: list[NavButton] = []
        self._indicator = QFrame(self)
        self._indicator.setStyleSheet(
            f"background: {theme.alpha(theme.ACCENT, 0.16)}; border-radius: 10px;"
            f"border-left: 3px solid {theme.ACCENT};")
        self._indicator.lower()
        self._indicator.hide()
        self._anim = QPropertyAnimation(self._indicator, b"geometry", self)
        self._anim.setDuration(300)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._current = -1

    def add_header(self, widget: QWidget) -> None:
        self._lay.addWidget(widget)
        self._lay.addSpacing(18)

    def add_item(self, text: str, icon_name: str) -> NavButton:
        btn = NavButton(text, icon_name, self)
        idx = len(self.buttons)
        btn.clicked.connect(lambda _=False, i=idx: self.select(i))
        self.buttons.append(btn)
        self._lay.addWidget(btn)
        return btn

    def add_stretch(self) -> None:
        self._lay.addStretch(1)

    def add_footer(self, widget: QWidget) -> None:
        self._lay.addWidget(widget)

    def select(self, index: int, animate: bool = True) -> None:
        for i, b in enumerate(self.buttons):
            b.setChecked(i == index)
        changed = index != self._current
        self._current = index
        self._move_indicator(animate)
        if changed:
            self.changed.emit(index)

    def _move_indicator(self, animate: bool) -> None:
        if not (0 <= self._current < len(self.buttons)):
            return
        target = self.buttons[self._current].geometry()
        if not self._indicator.isVisible() or not animate or not ANIMATIONS_ENABLED:
            self._indicator.setGeometry(target)
            self._indicator.show()
            return
        self._anim.stop()
        self._anim.setStartValue(self._indicator.geometry())
        self._anim.setEndValue(target)
        self._anim.start()

    def resizeEvent(self, e) -> None:  # noqa: N802
        super().resizeEvent(e)
        QTimer.singleShot(0, lambda: self._move_indicator(False))

    def showEvent(self, e) -> None:  # noqa: N802
        super().showEvent(e)
        QTimer.singleShot(0, lambda: self._move_indicator(False))


# ---------------------------------------------------------------------------
# Sección plegable
# ---------------------------------------------------------------------------
class Collapsible(QWidget):
    def __init__(self, title: str, icon_name: str = "sliders", expanded: bool = False) -> None:
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.header = QPushButton(title)
        self.header.setProperty("variant", "ghost")
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header.setIcon(icons.icon(icon_name, theme.MUTED, 16))
        self.header.setStyleSheet("text-align: left; padding: 10px 12px; font-weight: 600;")
        hl = QHBoxLayout(self.header)
        hl.setContentsMargins(0, 0, 12, 0)
        hl.addStretch(1)
        self.chevron = QLabel()
        self.chevron.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        hl.addWidget(self.chevron)
        lay.addWidget(self.header)
        self.body = QWidget()
        self.body.setMaximumHeight(0 if not expanded else 16777215)
        lay.addWidget(self.body)
        self._expanded = expanded
        self._anim = QPropertyAnimation(self.body, b"maximumHeight", self)
        self._anim.setDuration(300)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._anim.finished.connect(self._done)
        self.header.clicked.connect(self.toggle)
        self._update_chevron()

    def set_content(self, widget: QWidget) -> None:
        lay = QVBoxLayout(self.body)
        lay.setContentsMargins(0, 6, 0, 0)
        lay.addWidget(widget)

    def _update_chevron(self) -> None:
        self.chevron.setPixmap(icons.pixmap("chevron-down" if self._expanded else "chevron-right",
                                            theme.MUTED, 16))

    def toggle(self) -> None:
        self._expanded = not self._expanded
        self._update_chevron()
        full = self.body.sizeHint().height()
        self._anim.stop()
        self._anim.setDuration(duration(300))
        self._anim.setStartValue(self.body.height() if self._expanded else self.body.height())
        self._anim.setEndValue(full if self._expanded else 0)
        self._anim.start()

    def _done(self) -> None:
        if self._expanded:
            self.body.setMaximumHeight(16777215)


# ---------------------------------------------------------------------------
# Notificaciones flotantes
# ---------------------------------------------------------------------------
class Toast(QFrame):
    COLORS = {"info": theme.ACCENT_2, "success": theme.SUCCESS, "error": theme.ERROR,
              "warning": theme.WARNING}
    ICONS = {"info": "info", "success": "check", "error": "alert", "warning": "alert"}

    _active: list["Toast"] = []

    def __init__(self, parent: QWidget, text: str, kind: str = "info", ms: int = 3200) -> None:
        super().__init__(parent)
        color = self.COLORS.get(kind, theme.ACCENT)
        self.setStyleSheet(
            f"QFrame {{ background: {theme.SURFACE_3}; border: 1px solid {theme.alpha(color, 0.55)};"
            f" border-radius: 12px; }} QLabel {{ background: transparent; border: none; }}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 16, 10)
        lay.setSpacing(10)
        ic = QLabel()
        ic.setPixmap(icons.pixmap(self.ICONS.get(kind, "info"), color, 18))
        lay.addWidget(ic)
        msg = QLabel(text)
        msg.setWordWrap(True)
        msg.setMaximumWidth(460)
        lay.addWidget(msg)
        self.adjustSize()
        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._ms = ms

    @classmethod
    def show_message(cls, parent: QWidget, text: str, kind: str = "info", ms: int = 3200) -> None:
        toast = cls(parent, text, kind, ms)
        cls._active.append(toast)
        toast._popup()

    def _target_pos(self, index: int) -> QPoint:
        parent = self.parentWidget()
        y = parent.height() - 24 - self.height()
        for other in Toast._active[index + 1:]:
            y -= other.height() + 10
        return QPoint(parent.width() - self.width() - 24, y)

    @classmethod
    def _relayout(cls) -> None:
        for i, t in enumerate(cls._active):
            t.move(t._target_pos(i))

    def _popup(self) -> None:
        self.show()
        self.raise_()
        Toast._relayout()
        end = self.pos()
        self.move(end + QPoint(0, 20))
        group = QParallelAnimationGroup(self)
        a = QPropertyAnimation(self, b"pos")
        a.setDuration(duration(280))
        a.setStartValue(end + QPoint(0, 20))
        a.setEndValue(end)
        a.setEasingCurve(QEasingCurve.Type.OutBack)
        b = QPropertyAnimation(self._effect, b"opacity")
        b.setDuration(duration(220))
        b.setStartValue(0.0)
        b.setEndValue(1.0)
        group.addAnimation(a)
        group.addAnimation(b)
        group.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
        QTimer.singleShot(self._ms, self._dismiss)

    def _dismiss(self) -> None:
        anim = QPropertyAnimation(self._effect, b"opacity", self)
        anim.setDuration(duration(250))
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.finished.connect(self._remove)
        anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)

    def _remove(self) -> None:
        if self in Toast._active:
            Toast._active.remove(self)
        self.deleteLater()
        Toast._relayout()

    def mousePressEvent(self, _e) -> None:  # noqa: N802
        self._dismiss()


# ---------------------------------------------------------------------------
# Slider de rango con dos puntos
# ---------------------------------------------------------------------------
class RangeSlider(QWidget):
    """Selector visual de inicio/fin. Valores en segundos (float)."""

    rangeChanged = Signal(float, float)
    handleDragged = Signal(float)  # posición del punto que se arrastra (para previsualizar)
    dragFinished = Signal()

    HANDLE_R = 9
    TRACK_H = 6
    BUBBLE_H = 24

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._max = 100.0
        self._lo = 0.0
        self._hi = 100.0
        self._playhead: float | None = None
        self._drag: str | None = None  # "lo" | "hi" | "range"
        self._drag_origin = (0.0, 0.0, 0.0)
        self._hover: str | None = None
        self._grow = {"lo": 0.0, "hi": 0.0}
        self.min_gap = 1.0
        self.setMouseTracking(True)
        self.setFixedHeight(self.BUBBLE_H + 6 + 2 * self.HANDLE_R + 6 + 22)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._grow_anim = QTimer(self, interval=16)
        self._grow_anim.timeout.connect(self._step_grow)

    # -- API --------------------------------------------------------------
    def set_maximum(self, maximum: float) -> None:
        self._max = max(0.1, float(maximum))
        self.min_gap = min(1.0, self._max / 10)
        self._lo, self._hi = 0.0, self._max
        self._playhead = None
        self.update()
        self.rangeChanged.emit(self._lo, self._hi)

    def maximum(self) -> float:
        return self._max

    def values(self) -> tuple[float, float]:
        return self._lo, self._hi

    def set_values(self, lo: float, hi: float, emit: bool = True) -> None:
        lo = max(0.0, min(lo, self._max))
        hi = max(0.0, min(hi, self._max))
        if hi - lo < self.min_gap:
            if lo + self.min_gap <= self._max:
                hi = lo + self.min_gap
            else:
                lo = hi - self.min_gap
        if (lo, hi) == (self._lo, self._hi):
            return
        self._lo, self._hi = lo, hi
        self.update()
        if emit:
            self.rangeChanged.emit(lo, hi)

    def set_playhead(self, seconds: float | None) -> None:
        self._playhead = seconds
        self.update()

    def is_full(self) -> bool:
        return self._lo <= 0.05 and self._hi >= self._max - 0.05

    # -- geometría ----------------------------------------------------------
    def _track_rect(self) -> QRectF:
        m = self.HANDLE_R + 4
        y = self.BUBBLE_H + 6 + self.HANDLE_R - self.TRACK_H / 2
        return QRectF(m, y, self.width() - 2 * m, self.TRACK_H)

    def _x(self, value: float) -> float:
        t = self._track_rect()
        return t.left() + t.width() * (value / self._max)

    def _value(self, x: float) -> float:
        t = self._track_rect()
        return max(0.0, min(self._max, (x - t.left()) / t.width() * self._max))

    def _hit(self, pos: QPointF) -> str | None:
        cy = self._track_rect().center().y()
        for name, val in (("hi", self._hi), ("lo", self._lo)):
            if abs(pos.x() - self._x(val)) <= self.HANDLE_R + 4 and abs(pos.y() - cy) <= self.HANDLE_R + 8:
                return name
        if self._x(self._lo) < pos.x() < self._x(self._hi) and abs(pos.y() - cy) <= self.HANDLE_R:
            return "range"
        return None

    # -- animación de agrandado de los puntos ------------------------------------
    def _step_grow(self) -> None:
        active = False
        for name in ("lo", "hi"):
            target = 1.0 if (self._hover == name or self._drag == name) else 0.0
            cur = self._grow[name]
            if abs(cur - target) > 0.01:
                self._grow[name] = cur + (target - cur) * 0.25
                active = True
            else:
                self._grow[name] = target
        self.update()
        if not active:
            self._grow_anim.stop()

    # -- eventos --------------------------------------------------------------
    def mousePressEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        if e.button() != Qt.MouseButton.LeftButton or not self.isEnabled():
            return
        hit = self._hit(e.position())
        if hit is None:
            v = self._value(e.position().x())
            hit = "lo" if abs(v - self._lo) < abs(v - self._hi) else "hi"
            if hit == "lo":
                self.set_values(min(v, self._hi - self.min_gap), self._hi)
            else:
                self.set_values(self._lo, max(v, self._lo + self.min_gap))
            self.handleDragged.emit(self._lo if hit == "lo" else self._hi)
        self._drag = hit
        self._drag_origin = (e.position().x(), self._lo, self._hi)
        self._grow_anim.start()
        self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        if self._drag is None:
            hover = self._hit(e.position())
            if hover != self._hover:
                self._hover = hover
                self._grow_anim.start()
                self.setCursor(Qt.CursorShape.OpenHandCursor if hover == "range"
                               else Qt.CursorShape.PointingHandCursor if hover else Qt.CursorShape.ArrowCursor)
            return
        v = self._value(e.position().x())
        if self._drag == "lo":
            self.set_values(min(v, self._hi - self.min_gap), self._hi)
            self.handleDragged.emit(self._lo)
        elif self._drag == "hi":
            self.set_values(self._lo, max(v, self._lo + self.min_gap))
            self.handleDragged.emit(self._hi)
        else:
            x0, lo0, hi0 = self._drag_origin
            delta = self._value(e.position().x()) - self._value(x0)
            span = hi0 - lo0
            lo = max(0.0, min(self._max - span, lo0 + delta))
            self.set_values(lo, lo + span)
            self.handleDragged.emit(self._lo)

    def mouseReleaseEvent(self, _e: QMouseEvent) -> None:  # noqa: N802
        if self._drag is not None:
            self._drag = None
            self._grow_anim.start()
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.dragFinished.emit()

    def leaveEvent(self, _e) -> None:  # noqa: N802
        self._hover = None
        self._grow_anim.start()

    def keyPressEvent(self, e) -> None:  # noqa: N802
        step = 5.0 if e.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1.0
        if e.key() == Qt.Key.Key_Left:
            self.set_values(self._lo - step, self._hi)
        elif e.key() == Qt.Key.Key_Right:
            self.set_values(self._lo + step, self._hi)
        elif e.key() == Qt.Key.Key_Down:
            self.set_values(self._lo, self._hi - step)
        elif e.key() == Qt.Key.Key_Up:
            self.set_values(self._lo, self._hi + step)
        else:
            super().keyPressEvent(e)

    # -- pintado --------------------------------------------------------------
    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = self._track_rect()
        enabled = self.isEnabled()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(theme.SURFACE_3))
        p.drawRoundedRect(t, t.height() / 2, t.height() / 2)

        x1, x2 = self._x(self._lo), self._x(self._hi)
        sel = QRectF(x1, t.top(), max(0.0, x2 - x1), t.height())
        grad = QLinearGradient(sel.topLeft(), sel.topRight())
        grad.setColorAt(0, QColor(theme.ACCENT if enabled else theme.SUBTLE))
        grad.setColorAt(1, QColor(theme.ACCENT_2 if enabled else theme.SUBTLE))
        p.setBrush(grad)
        p.drawRoundedRect(sel, t.height() / 2, t.height() / 2)

        if self._playhead is not None:
            px = self._x(min(self._max, max(0.0, self._playhead)))
            p.setPen(QPen(QColor(255, 255, 255, 200), 2))
            p.drawLine(QPointF(px, t.top() - 7), QPointF(px, t.bottom() + 7))

        cy = t.center().y()
        for name, x, val in (("lo", x1, self._lo), ("hi", x2, self._hi)):
            g = self._grow[name]
            r = self.HANDLE_R + 3 * g
            if g > 0.01:
                halo = QColor(theme.ACCENT)
                halo.setAlphaF(0.25 * g)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(halo)
                p.drawEllipse(QPointF(x, cy), r + 6 * g, r + 6 * g)
            p.setPen(QPen(QColor(theme.ACCENT if enabled else theme.SUBTLE), 3))
            p.setBrush(QColor("white"))
            p.drawEllipse(QPointF(x, cy), r, r)

            # Burbuja con el tiempo
            text = format_time(val)
            font = QFont(self.font())
            font.setPointSizeF(font.pointSizeF() * 0.9)
            font.setWeight(QFont.Weight.DemiBold)
            p.setFont(font)
            tw = p.fontMetrics().horizontalAdvance(text) + 14
            bx = max(0.0, min(self.width() - tw, x - tw / 2))
            bubble = QRectF(bx, 0, tw, self.BUBBLE_H - 4)
            active = g > 0.3
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(theme.ACCENT) if active else QColor(theme.SURFACE_3))
            p.drawRoundedRect(bubble, 6, 6)
            p.setPen(QColor("white" if active else theme.TEXT))
            p.drawText(bubble, Qt.AlignmentFlag.AlignCenter, text)

        # Duración del rango
        span = self._hi - self._lo
        p.setPen(QColor(theme.MUTED))
        small = QFont(self.font())
        small.setPointSizeF(small.pointSizeF() * 0.85)
        p.setFont(small)
        p.drawText(QRectF(0, t.bottom() + self.HANDLE_R + 2, self.width(), 16),
                   Qt.AlignmentFlag.AlignCenter, f"Duración seleccionada: {format_time(span)}")
        p.drawText(QRectF(t.left() - self.HANDLE_R, t.bottom() + self.HANDLE_R + 2, 80, 16),
                   Qt.AlignmentFlag.AlignLeft, "00:00")
        p.drawText(QRectF(t.right() - 80 + self.HANDLE_R, t.bottom() + self.HANDLE_R + 2, 80, 16),
                   Qt.AlignmentFlag.AlignRight, format_time(self._max))


# ---------------------------------------------------------------------------
# Vista previa de video
# ---------------------------------------------------------------------------
class VideoPreview(QWidget):
    """Reproduce el stream directo del video (o muestra la miniatura).

    Se dibuja a mano a partir de los frames de ``QVideoSink`` para poder tener
    esquinas redondeadas y animaciones sin los problemas de las ventanas nativas.
    """

    positionChanged = Signal(float)
    stateChanged = Signal(bool)  # reproduciendo

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(320, 180)
        policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._thumb = QPixmap()
        self._frame: QImage | None = None
        self._url: str | None = None
        self._loaded = False
        self._pending_seek: float | None = None
        self._play_after_load = False
        self._loop: tuple[float, float] | None = None
        self._message = ""
        self._hover = False
        self._overlay = 1.0
        self._overlay_anim = QVariantAnimation(self)
        self._overlay_anim.setDuration(200)
        self._overlay_anim.valueChanged.connect(self._set_overlay)
        self._buffering = False
        self._spin = 0
        self._spin_timer = QTimer(self, interval=16)
        self._spin_timer.timeout.connect(self._tick)
        self.player = None
        self._init_player()

    def _init_player(self) -> None:
        try:
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink
        except ImportError:
            self._message = "Vista previa no disponible (QtMultimedia)"
            return
        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(0.6)
        self.player.setAudioOutput(self.audio)
        self.sink = QVideoSink(self)
        self.player.setVideoSink(self.sink)
        self.sink.videoFrameChanged.connect(self._on_frame)
        self.player.positionChanged.connect(self._on_position)
        self.player.playbackStateChanged.connect(self._on_state)
        self.player.mediaStatusChanged.connect(self._on_status)
        self.player.errorOccurred.connect(self._on_error)
        self._QMediaPlayer = QMediaPlayer

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return max(180, int(width * 9 / 16))

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(640, 360)

    # -- API ------------------------------------------------------------------
    def set_media(self, url: str | None, thumbnail_url: str | list[str] | None,
                  message: str = "Vista previa de video no disponible") -> None:
        self.stop()
        self._url = url
        self._loaded = False
        self._frame = None
        self._thumb = QPixmap()
        self._loop = None
        self._message = "" if url else message
        if self.player is not None:
            self.player.setSource(QUrl())
        ImageLoader.load(thumbnail_url, self._set_thumb)
        self.update()

    def _set_thumb(self, pix: QPixmap) -> None:
        self._thumb = pix
        self.update()

    def clear(self) -> None:
        self.set_media(None, None)
        self._message = ""

    def is_playing(self) -> bool:
        return bool(self.player and self.player.playbackState() == self._QMediaPlayer.PlaybackState.PlayingState)

    def toggle(self) -> None:
        if self.is_playing():
            self.player.pause()
        else:
            self.play()

    def play(self, loop: tuple[float, float] | None = None) -> None:
        if self.player is None or not self._url:
            return
        self._loop = loop
        if loop is not None:
            self.seek(loop[0])
        if not self._ensure_loaded(play=True):
            return
        self.player.play()

    def stop(self) -> None:
        if self.player is not None:
            self.player.stop()

    def set_muted(self, muted: bool) -> None:
        if self.player is not None:
            self.audio.setMuted(muted)

    def seek(self, seconds: float) -> None:
        if self.player is None or not self._url:
            return
        if not self._loaded:
            self._pending_seek = seconds
            self._ensure_loaded(play=False)
            return
        self.player.setPosition(int(seconds * 1000))

    def _ensure_loaded(self, play: bool) -> bool:
        if self._loaded:
            return True
        self._play_after_load = self._play_after_load or play
        if self.player.source().isEmpty():
            self._buffering = True
            self._spin_timer.start()
            self.player.setSource(QUrl(self._url))
            if not play:
                self.player.pause()  # carga y muestra el primer frame
        return False

    # -- señales del reproductor -------------------------------------------
    def _on_status(self, status) -> None:
        S = self._QMediaPlayer.MediaStatus
        if status in (S.LoadedMedia, S.BufferedMedia) and not self._loaded:
            self._loaded = True
            if self._pending_seek is not None:
                self.player.setPosition(int(self._pending_seek * 1000))
                self._pending_seek = None
            if self._play_after_load:
                self._play_after_load = False
                self.player.play()
            elif self.player.playbackState() != self._QMediaPlayer.PlaybackState.PlayingState:
                self.player.pause()
        self._buffering = status in (S.LoadingMedia, S.BufferingMedia, S.StalledMedia)
        if self._buffering:
            self._spin_timer.start()
        else:
            self._spin_timer.stop()
        self.update()

    def _on_error(self, _err, message: str = "") -> None:
        self._buffering = False
        self._spin_timer.stop()
        self._loaded = False
        self._message = "No se pudo reproducir la vista previa"
        self.update()

    def _on_frame(self, frame) -> None:
        if frame.isValid():
            self._frame = frame.toImage()
            self.update()

    def _on_position(self, ms: int) -> None:
        sec = ms / 1000
        if self._loop and self.is_playing() and sec >= self._loop[1]:
            self.player.setPosition(int(self._loop[0] * 1000))
            return
        self.positionChanged.emit(sec)

    def _on_state(self, _state) -> None:
        playing = self.is_playing()
        if not playing:
            self._loop = None
        self._animate_overlay(0.0 if playing and not self._hover else 1.0)
        self.stateChanged.emit(playing)

    # -- interacción / pintado ----------------------------------------------
    def _set_overlay(self, v) -> None:
        self._overlay = float(v)
        self.update()

    def _animate_overlay(self, target: float) -> None:
        self._overlay_anim.stop()
        self._overlay_anim.setStartValue(self._overlay)
        self._overlay_anim.setEndValue(target)
        self._overlay_anim.start()

    def _tick(self) -> None:
        self._spin = (self._spin + 8) % 360
        self.update()

    def enterEvent(self, _e) -> None:  # noqa: N802
        self._hover = True
        self._animate_overlay(1.0)

    def leaveEvent(self, _e) -> None:  # noqa: N802
        self._hover = False
        if self.is_playing():
            self._animate_overlay(0.0)

    def mousePressEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            self.toggle()

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = QRectF(self.rect())
        path = QPainterPath()
        path.addRoundedRect(r, 12, 12)
        p.setClipPath(path)
        p.fillRect(r, QColor("#07080C"))

        img: QImage | QPixmap | None = self._frame if self._frame is not None else (
            self._thumb if not self._thumb.isNull() else None)
        if img is not None:
            size = QSize(img.width(), img.height()).scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
            target = QRectF((self.width() - size.width()) / 2, (self.height() - size.height()) / 2,
                            size.width(), size.height())
            if isinstance(img, QImage):
                p.drawImage(target, img)
            else:
                p.drawPixmap(target.toRect(), img)

        # Degradado inferior + botón central
        if self._overlay > 0.01:
            grad = QLinearGradient(0, r.height() * 0.5, 0, r.height())
            grad.setColorAt(0, QColor(0, 0, 0, 0))
            grad.setColorAt(1, QColor(0, 0, 0, int(150 * self._overlay)))
            p.fillRect(r, QBrush(grad))
            if self._url and not self._buffering:
                c = r.center()
                rad = 30
                circle = QColor(theme.ACCENT)
                circle.setAlphaF(0.85 * self._overlay)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(circle)
                p.drawEllipse(c, rad, rad)
                p.setOpacity(self._overlay)
                name = "pause" if self.is_playing() else "play"
                p.drawPixmap(QPointF(c.x() - 11 + (2 if name == "play" else 0), c.y() - 11),
                             icons.pixmap(name, "#FFFFFF", 22))
                p.setOpacity(1.0)

        if self._buffering:
            c = r.center()
            p.setPen(QPen(QColor(255, 255, 255, 60), 4))
            p.drawEllipse(c, 22, 22)
            p.setPen(QPen(QColor("white"), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawArc(QRectF(c.x() - 22, c.y() - 22, 44, 44), -self._spin * 16, 90 * 16)

        if self._message:
            p.setPen(QColor(theme.MUTED))
            p.drawText(r.adjusted(10, 0, -10, -12), Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
                       self._message)
        if img is None and not self._url and not self._message and not self._buffering:
            p.drawPixmap(QPointF(r.center().x() - 24, r.center().y() - 24),
                         icons.pixmap("video", theme.SUBTLE, 48))
