"""Tema oscuro moderno (QSS) con color de acento configurable."""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

BG = "#0E1016"
SIDEBAR = "#12141C"
SURFACE = "#171A24"
SURFACE_2 = "#1E2230"
SURFACE_3 = "#262B3B"
BORDER = "#2A2F40"
TEXT = "#E6E8EF"
MUTED = "#8A90A2"
SUBTLE = "#5D6377"
SUCCESS = "#22C55E"
ERROR = "#EF4444"
WARNING = "#F59E0B"
ACCENT_2 = "#22D3EE"

ACCENT = "#7C5CFF"

ACCENT_PRESETS = ["#7C5CFF", "#3B82F6", "#22C55E", "#F43F5E", "#F59E0B", "#14B8A6", "#EC4899"]


def lighten(color: str, factor: int = 120) -> str:
    return QColor(color).lighter(factor).name()


def darken(color: str, factor: int = 130) -> str:
    return QColor(color).darker(factor).name()


def alpha(color: str, a: float) -> str:
    c = QColor(color)
    return f"rgba({c.red()},{c.green()},{c.blue()},{a})"


def stylesheet(accent: str) -> str:
    return f"""
* {{
    font-family: "Segoe UI Variable Text", "Segoe UI", "Inter", sans-serif;
    font-size: 13px;
    color: {TEXT};
    outline: none;
}}
QMainWindow, #Root {{ background: {BG}; }}
QToolTip {{
    background: {SURFACE_3}; color: {TEXT}; border: 1px solid {BORDER};
    border-radius: 6px; padding: 6px 8px;
}}

/* ---------- Sidebar ---------- */
#Sidebar {{ background: {SIDEBAR}; border-right: 1px solid {BORDER}; }}
#Brand {{ font-size: 18px; font-weight: 700; }}
#BrandSub {{ color: {MUTED}; font-size: 11px; }}

/* ---------- Tipografía ---------- */
QLabel[role="h1"] {{ font-size: 22px; font-weight: 700; }}
QLabel[role="h2"] {{ font-size: 16px; font-weight: 600; }}
QLabel[role="h3"] {{ font-size: 14px; font-weight: 600; }}
QLabel[role="muted"] {{ color: {MUTED}; }}
QLabel[role="subtle"] {{ color: {SUBTLE}; font-size: 12px; }}
QLabel[role="badge"] {{
    background: {alpha(accent, 0.18)}; color: {lighten(accent, 135)};
    border-radius: 9px; padding: 2px 8px; font-size: 11px; font-weight: 600;
}}
QLabel[role="error"] {{ color: {ERROR}; }}
QLabel[role="success"] {{ color: {SUCCESS}; }}

/* ---------- Tarjetas ---------- */
#Card, QFrame[card="true"] {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 14px;
}}
QFrame[card="inner"] {{
    background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 10px;
}}

/* ---------- Botones ---------- */
QPushButton, QToolButton {{
    background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 9px;
    padding: 8px 14px; font-weight: 500;
}}
QPushButton:hover, QToolButton:hover {{ background: {SURFACE_3}; border-color: {lighten(BORDER, 140)}; }}
QPushButton:pressed, QToolButton:pressed {{ background: {SURFACE}; }}
QPushButton:disabled, QToolButton:disabled {{ color: {SUBTLE}; background: {SURFACE}; }}
QPushButton[variant="primary"] {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {accent}, stop:1 {lighten(accent, 118)});
    border: none; color: white; font-weight: 600;
}}
QPushButton[variant="primary"]:hover {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {lighten(accent, 112)}, stop:1 {lighten(accent, 130)});
}}
QPushButton[variant="primary"]:pressed {{ background: {darken(accent, 115)}; }}
QPushButton[variant="primary"]:disabled {{ background: {SURFACE_3}; color: {SUBTLE}; }}
QPushButton[variant="ghost"], QToolButton[variant="ghost"] {{
    background: transparent; border: 1px solid transparent;
}}
QPushButton[variant="ghost"]:hover, QToolButton[variant="ghost"]:hover {{ background: {SURFACE_2}; border-color: {BORDER}; }}
QPushButton[variant="danger"]:hover, QToolButton[variant="danger"]:hover {{
    background: {alpha(ERROR, 0.15)}; border-color: {alpha(ERROR, 0.5)};
}}
QPushButton[size="lg"] {{ padding: 12px 22px; font-size: 14px; border-radius: 11px; }}
QToolButton[variant="icon"] {{ background: transparent; border: none; border-radius: 8px; padding: 6px; }}
QToolButton[variant="icon"]:hover {{ background: {SURFACE_3}; }}

/* ---------- Entradas ---------- */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit, QTextEdit {{
    background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 9px;
    padding: 7px 10px; selection-background-color: {accent};
}}
QLineEdit:hover, QSpinBox:hover, QComboBox:hover {{ border-color: {lighten(BORDER, 140)}; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {{
    border-color: {accent};
}}
QLineEdit[size="xl"] {{ font-size: 15px; padding: 12px 14px; border-radius: 12px; background: {SURFACE}; }}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{ color: {SUBTLE}; background: {SURFACE}; }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox::down-arrow {{ image: none; width: 0; }}
QComboBox QAbstractItemView {{
    background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 8px; padding: 4px;
    selection-background-color: {alpha(accent, 0.3)};
}}
QSpinBox::up-button, QSpinBox::down-button {{ width: 0; border: none; }}

QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{
    width: 18px; height: 18px; border-radius: 5px; border: 1px solid {lighten(BORDER, 150)};
    background: {SURFACE_2};
}}
QCheckBox::indicator:hover {{ border-color: {accent}; }}
QCheckBox::indicator:checked {{ background: {accent}; border-color: {accent}; image: url(zubelui:check.png); }}

/* ---------- Pestañas ---------- */
QTabWidget::pane {{ border: none; background: transparent; top: -1px; }}
QTabBar::tab {{
    background: transparent; color: {MUTED}; padding: 8px 8px; margin-right: 1px;
    border: none; border-bottom: 2px solid transparent;
}}
QTabBar::tab:hover {{ color: {TEXT}; }}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {accent}; }}

/* ---------- Progreso ---------- */
QProgressBar {{
    background: {SURFACE_3}; border: none; border-radius: 4px; height: 8px; text-align: center;
    font-size: 0px;
}}
QProgressBar::chunk {{
    border-radius: 4px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {accent}, stop:1 {ACCENT_2});
}}
QProgressBar[state="done"]::chunk {{ background: {SUCCESS}; }}
QProgressBar[state="error"]::chunk {{ background: {ERROR}; }}
QProgressBar[state="paused"]::chunk {{ background: {WARNING}; }}

/* ---------- Scroll ---------- */
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {SURFACE_3}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {lighten(SURFACE_3, 140)}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {SURFACE_3}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{
    width: 0; height: 0; background: none;
}}

/* ---------- Tablas / listas ---------- */
QTableWidget, QListWidget, QTreeWidget {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px;
    gridline-color: {BORDER}; alternate-background-color: {SURFACE_2};
    selection-background-color: {alpha(accent, 0.28)}; selection-color: {TEXT};
}}
QListWidget::item {{ padding: 6px; border-radius: 6px; }}
QListWidget::item:hover {{ background: {SURFACE_2}; }}
QHeaderView::section {{
    background: {SURFACE_2}; color: {MUTED}; border: none; border-bottom: 1px solid {BORDER};
    padding: 6px 8px; font-weight: 600;
}}
QTableCornerButton::section {{ background: {SURFACE_2}; border: none; }}

QMenu {{ background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 7px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {alpha(accent, 0.25)}; }}
QDialog {{ background: {BG}; }}
QSplitter::handle {{ background: transparent; }}
"""


def apply(app: QApplication, accent: str) -> None:
    global ACCENT
    ACCENT = accent
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(BG))
    pal.setColor(QPalette.ColorRole.Base, QColor(SURFACE_2))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(SURFACE))
    pal.setColor(QPalette.ColorRole.Text, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.Button, QColor(SURFACE_2))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(accent))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("white"))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(SUBTLE))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(SURFACE_3))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(TEXT))
    app.setPalette(pal)
    font = QFont("Segoe UI Variable Text")
    font.setPointSizeF(9.75)
    app.setFont(font)
    _register_check_image()
    app.setStyleSheet(stylesheet(accent))


def _register_check_image() -> None:
    """Guarda el icono ✓ del checkbox en un recurso accesible desde QSS."""
    from PySide6.QtCore import QDir

    from zubel import paths
    from zubel.ui import icons

    folder = paths.thumbs_cache_dir().parent / "ui"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / "check.png"
    if not target.exists():
        icons.pixmap("check", "#FFFFFF", 14, 1.0).save(str(target))
    QDir.addSearchPath("zubelui", str(folder))


def repolish(widget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)
