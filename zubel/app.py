"""Punto de entrada de Zubel.

Uso:
    zubel                  abre la aplicación
    zubel --install-deps   descarga yt-dlp, FFmpeg y Deno (lo usa el instalador)
"""
from __future__ import annotations

import os
import sys


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Zubel.App")
        except (AttributeError, OSError):
            pass

    from PySide6.QtWidgets import QApplication, QDialog

    from zubel import __app_name__, config, deps
    from zubel.ui import icons, theme

    app = QApplication(argv)
    app.setApplicationName(__app_name__)
    app.setOrganizationName(__app_name__)
    app.setQuitOnLastWindowClosed(False)
    settings = config.load_settings()
    theme.apply(app, settings.accent)
    app.setWindowIcon(icons.app_icon())

    from zubel.ui.setup_dialog import SetupDialog

    if "--install-deps" in argv:
        keys = [c.key for c in deps.COMPONENTS.values() if c.url()]
        dialog = SetupDialog(keys)
        return 0 if dialog.exec() == QDialog.DialogCode.Accepted else 1

    missing = deps.missing_components()
    if missing:
        dialog = SetupDialog([c.key for c in missing])
        if dialog.exec() != QDialog.DialogCode.Accepted and deps.missing_components(include_optional=False):
            return 1

    from zubel.ui.main_window import MainWindow

    window = MainWindow(settings)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
