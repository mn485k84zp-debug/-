from __future__ import annotations

from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QWidget


def bind_window_hotkeys(
    parent: QWidget,
    toggle_listening,
    clear_context,
    regenerate,
    toggle_collapse,
) -> list[QShortcut]:
    bindings = [
        ("Ctrl+Alt+S", toggle_listening),
        ("Ctrl+Alt+C", clear_context),
        ("Ctrl+Alt+R", regenerate),
        ("Ctrl+Alt+M", toggle_collapse),
    ]
    shortcuts: list[QShortcut] = []
    for sequence, callback in bindings:
        shortcut = QShortcut(QKeySequence(sequence), parent)
        shortcut.activated.connect(callback)
        shortcuts.append(shortcut)
    return shortcuts
