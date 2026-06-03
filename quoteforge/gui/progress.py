import tkinter as tk
from tkinter import ttk


class ProgressTracker:
    """Thread-safe progress updates for the Tkinter GUI."""

    def __init__(self, root: tk.Tk, bar: ttk.Progressbar, label: tk.Label):
        self._root = root
        self._bar = bar
        self._label = label

    def update(self, current: int, total: int, message: str) -> None:
        pct = int((current / total) * 100) if total > 0 else 0
        self._root.after(0, self._bar.configure, {"value": pct})
        self._root.after(0, self._label.configure, {"text": f"({current}/{total}) {message[:60]}"})
