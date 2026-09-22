#!/usr/bin/env python3
"""Entry point: launch the MS SERVICE desktop GUI (PySide6)."""

from __future__ import annotations

import sys


def _hide_windows_console() -> None:
    """Detach a console window so the packaged app stays window-only."""
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return
    try:
        import ctypes

        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)
        ctypes.windll.kernel32.FreeConsole()
    except (AttributeError, OSError):
        pass


_hide_windows_console()

from gui_app import main

if __name__ == "__main__":
    main()
