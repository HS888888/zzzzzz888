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


def _run_worker() -> None:
    from gateway import run_gateway_process

    if len(sys.argv) != 5:
        raise SystemExit(2)
    run_gateway_process(sys.argv[2], sys.argv[3], sys.argv[4])


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--gateway-worker":
        _run_worker()
    else:
        _hide_windows_console()
        from gui_app import main

        main()
