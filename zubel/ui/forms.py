"""Pequeños ayudantes para construir formularios."""
from __future__ import annotations

from typing import Any, Iterable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QGridLayout, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget

from zubel.ui.widgets import label


def combo(items: Iterable[tuple[str, Any]], editable: bool = False) -> QComboBox:
    box = QComboBox()
    box.setEditable(editable)
    box.setCursor(Qt.CursorShape.PointingHandCursor)
    for text, data in items:
        box.addItem(text, data)
    box.setMaxVisibleItems(14)
    return box


def set_combo_data(box: QComboBox, value: Any) -> None:
    idx = box.findData(value)
    if idx >= 0:
        box.setCurrentIndex(idx)
    elif box.isEditable() and value is not None:
        box.setEditText(str(value))


def field(title: str, widget: QWidget, hint: str = "") -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(5)
    lay.addWidget(label(title, "muted"))
    lay.addWidget(widget)
    if hint:
        lay.addWidget(label(hint, "subtle", wrap=True))
    return w


def grid(widgets: list[QWidget], columns: int = 2, spacing: int = 14) -> QWidget:
    w = QWidget()
    lay = QGridLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setHorizontalSpacing(spacing)
    lay.setVerticalSpacing(spacing)
    for i, child in enumerate(widgets):
        lay.addWidget(child, i // columns, i % columns, Qt.AlignmentFlag.AlignTop)
    for c in range(columns):
        lay.setColumnStretch(c, 1)
    return w


def vbox(*widgets: QWidget, spacing: int = 10, margins: tuple[int, int, int, int] = (0, 0, 0, 0)) -> QWidget:
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(*margins)
    lay.setSpacing(spacing)
    for child in widgets:
        lay.addWidget(child)
    lay.addStretch(1)
    return w


def fit_stack(stack: QStackedWidget) -> None:
    """Hace que un QStackedWidget mida lo que la página visible (no la más grande)."""
    def apply(index: int) -> None:
        for i in range(stack.count()):
            policy = QSizePolicy.Policy.Preferred if i == index else QSizePolicy.Policy.Ignored
            stack.widget(i).setSizePolicy(policy, policy)
        stack.adjustSize()
    stack.currentChanged.connect(apply)
    apply(stack.currentIndex())
