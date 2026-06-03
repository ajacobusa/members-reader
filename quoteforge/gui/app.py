import threading
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

from quoteforge.quotes.categories import CATEGORIES
from quoteforge.pipeline import run_pipeline
from quoteforge.etsy.exporter import export_listings_csv
from quoteforge.config import OUTPUT_DIR
from quoteforge.gui.progress import ProgressTracker

DEFAULT_TEMPLATE_UID = "YOUR_BANNERBEAR_TEMPLATE_UID"


class QuoteForgeApp:
    def __init__(self, root: tk.Tk):
        self._root = root
        root.title("QuoteForge — Wall Art Generator")
        root.geometry("520x480")
        root.resizable(False, False)
        self._build_ui()

    def _build_ui(self) -> None:
        pad = {"padx": 16, "pady": 6}

        tk.Label(self._root, text="QuoteForge", font=("Helvetica", 20, "bold")).pack(pady=(20, 4))
        tk.Label(self._root, text="Professional Wall Art for Etsy + Gelato", font=("Helvetica", 10)).pack()
        ttk.Separator(self._root, orient="horizontal").pack(fill="x", pady=12)

        tk.Label(self._root, text="Category:", anchor="w").pack(fill="x", **pad)
        self._cat_var = tk.StringVar(value=list(CATEGORIES.keys())[0])
        self._cat_menu = ttk.Combobox(self._root, textvariable=self._cat_var,
                                      values=list(CATEGORIES.keys()), state="readonly", width=45)
        self._cat_menu.pack(**pad)
        self._cat_menu.bind("<<ComboboxSelected>>", self._on_category_change)

        tk.Label(self._root, text="Sub-category:", anchor="w").pack(fill="x", **pad)
        self._sub_var = tk.StringVar()
        self._sub_menu = ttk.Combobox(self._root, textvariable=self._sub_var, state="readonly", width=45)
        self._sub_menu.pack(**pad)
        self._on_category_change()

        tk.Label(self._root, text="Number of designs:", anchor="w").pack(fill="x", **pad)
        self._count_var = tk.IntVar(value=5)
        ttk.Spinbox(self._root, from_=1, to=50, textvariable=self._count_var, width=6).pack(**pad)

        self._btn = ttk.Button(self._root, text="Generate Designs", command=self._on_generate)
        self._btn.pack(pady=14)

        self._bar = ttk.Progressbar(self._root, length=440, mode="determinate")
        self._bar.pack(**pad)
        self._status = tk.Label(self._root, text="Ready.", anchor="w", wraplength=460)
        self._status.pack(fill="x", **pad)

    def _on_category_change(self, *_) -> None:
        cat = self._cat_var.get()
        subs = CATEGORIES.get(cat, {}).get("subcategories", [])
        self._sub_menu["values"] = subs
        if subs:
            self._sub_var.set(subs[0])

    def _on_generate(self) -> None:
        self._btn.configure(state="disabled")
        self._bar["value"] = 0
        self._status.configure(text="Starting...")
        threading.Thread(target=self._run_generation, daemon=True).start()

    def _run_generation(self) -> None:
        cat = self._cat_var.get()
        sub = self._sub_var.get()
        count = self._count_var.get()
        tracker = ProgressTracker(self._root, self._bar, self._status)

        def on_progress(current, total, quote):
            tracker.update(current, total, f"Rendering: {quote}")

        try:
            results = run_pipeline(
                category=cat,
                subcategory=sub,
                count=count,
                template_uid=DEFAULT_TEMPLATE_UID,
                output_dir=OUTPUT_DIR,
                on_progress=on_progress,
            )
            listings = [
                {**r["listing"], "quote": r["quote"], "category": cat}
                for r in results
            ]
            export_listings_csv(listings, OUTPUT_DIR)
            self._root.after(0, self._on_done, len(results))
        except Exception as exc:
            self._root.after(0, messagebox.showerror, "Error", str(exc))
            self._root.after(0, self._btn.configure, {"state": "normal"})

    def _on_done(self, count: int) -> None:
        self._bar["value"] = 100
        self._status.configure(text=f"Done! {count} designs saved to {OUTPUT_DIR}")
        messagebox.showinfo("QuoteForge", f"{count} designs saved!\n\nFolder: {OUTPUT_DIR}\n\nAlso saved: etsy_listings.csv")
        self._btn.configure(state="normal")
