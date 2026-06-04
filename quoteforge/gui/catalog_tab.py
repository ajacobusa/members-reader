"""Phase 14: Bulk Catalog Generator Tab.

Generates 800+ listing-ready rows across 8 core relationships.
Also shows Phase 11 SEO packs and Phase 1 validation checklist.
"""
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import sys

from quoteforge.config import OUTPUT_DIR, PHASE1_NICHES, BULK_CATALOG_RELATIONSHIPS
from quoteforge.etsy.bulk_catalog import generate_bulk_catalog, generate_seo_pack
from quoteforge.etsy.order_processor import NICHE_LISTING_TITLES


class CatalogTab(tk.Frame):
    def __init__(self, parent: tk.Widget):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        pad = {"padx": 14, "pady": 4}

        tk.Label(self, text="Bulk Catalog & SEO Pack Generator",
                 font=("Helvetica", 14, "bold")).grid(
            row=0, column=0, columnspan=4, pady=(14, 2), padx=14, sticky="w")
        tk.Label(self, text="Phase 14: Generate 800+ listing-ready rows. Phase 11: SEO title/tag packs.",
                 font=("Helvetica", 9), fg="#555").grid(
            row=1, column=0, columnspan=4, padx=14, sticky="w")
        ttk.Separator(self, orient="horizontal").grid(
            row=2, column=0, columnspan=4, sticky="ew", padx=14, pady=8)

        # ── Phase 1 Validation Checklist ────────────────────────
        tk.Label(self, text="Phase 1 — Validate These Niches First (20-30 manual listings):",
                 font=("Helvetica", 10, "bold"), anchor="w").grid(
            row=3, column=0, columnspan=4, sticky="w", **pad)

        for i, niche in enumerate(PHASE1_NICHES, start=4):
            tk.Label(self, text=f"  ☐  {niche}", anchor="w", font=("Helvetica", 9)).grid(
                row=i, column=0, columnspan=4, sticky="w", padx=24)

        row = 4 + len(PHASE1_NICHES)
        ttk.Separator(self, orient="horizontal").grid(
            row=row, column=0, columnspan=4, sticky="ew", padx=14, pady=8)
        row += 1

        # ── Bulk Catalog Generator ───────────────────────────────
        tk.Label(self, text="Phase 14 — Bulk Catalog Generator",
                 font=("Helvetica", 10, "bold"), anchor="w").grid(
            row=row, column=0, columnspan=4, sticky="w", **pad)
        row += 1

        tk.Label(self, text="Quotes per relationship (8 × N = total rows):",
                 anchor="w").grid(row=row, column=0, sticky="w", **pad)
        self._qty_var = tk.IntVar(value=100)
        ttk.Spinbox(self, from_=10, to=500, increment=10,
                    textvariable=self._qty_var, width=7).grid(
            row=row, column=1, sticky="w", padx=4)
        row += 1

        self._cat_btn = ttk.Button(self, text="✦ Generate Bulk Catalog CSV",
                                   command=self._on_catalog)
        self._cat_btn.grid(row=row, column=0, columnspan=2, pady=6, padx=14, sticky="w")

        open_btn = ttk.Button(self, text="Open Output Folder",
                              command=self._open_folder)
        open_btn.grid(row=row, column=2, columnspan=2, pady=6, sticky="w")
        row += 1

        ttk.Separator(self, orient="horizontal").grid(
            row=row, column=0, columnspan=4, sticky="ew", padx=14, pady=8)
        row += 1

        # ── SEO Pack Generator ───────────────────────────────────
        tk.Label(self, text="Phase 11 — SEO Title & Tag Pack",
                 font=("Helvetica", 10, "bold"), anchor="w").grid(
            row=row, column=0, columnspan=4, sticky="w", **pad)
        row += 1

        tk.Label(self, text="Select Niche:", anchor="w").grid(
            row=row, column=0, sticky="w", **pad)
        self._niche_var = tk.StringVar(value=list(NICHE_LISTING_TITLES.keys())[0])
        ttk.Combobox(self, textvariable=self._niche_var,
                     values=list(NICHE_LISTING_TITLES.keys()),
                     state="readonly", width=38).grid(
            row=row, column=1, columnspan=3, sticky="w", padx=4)
        row += 1

        ttk.Button(self, text="Generate SEO Pack",
                   command=self._on_seo).grid(row=row, column=0, columnspan=2,
                                              pady=4, padx=14, sticky="w")
        row += 1

        # Progress + status
        self._bar = ttk.Progressbar(self, length=480, mode="indeterminate")
        self._bar.grid(row=row, column=0, columnspan=4, padx=14, pady=4)
        row += 1
        self._status = tk.Label(self, text="Ready.", anchor="w",
                                wraplength=500, font=("Helvetica", 9))
        self._status.grid(row=row, column=0, columnspan=4, sticky="w", padx=14)
        row += 1

        # Output display
        tk.Label(self, text="Output:", anchor="w",
                 font=("Helvetica", 10, "bold")).grid(
            row=row, column=0, columnspan=4, sticky="w", padx=14, pady=(8, 2))
        row += 1
        self._output = tk.Text(self, width=64, height=16, wrap="word",
                               font=("Helvetica", 10), state="disabled",
                               bg="#f9f9f9", relief="flat")
        self._output.grid(row=row, column=0, columnspan=4, padx=14, pady=4, sticky="ew")
        row += 1
        ttk.Button(self, text="Copy to Clipboard",
                   command=self._copy).grid(row=row, column=0, columnspan=4, pady=4)

    def _set_output(self, text: str) -> None:
        self._output.configure(state="normal")
        self._output.delete("1.0", "end")
        self._output.insert("1.0", text)
        self._output.configure(state="disabled")

    def _copy(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self._output.get("1.0", "end").strip())
        messagebox.showinfo("Copied", "Output copied to clipboard!")

    def _open_folder(self) -> None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.Popen(f'explorer "{OUTPUT_DIR}"')

    def _on_catalog(self) -> None:
        self._cat_btn.configure(state="disabled")
        self._bar.start(10)
        qty = self._qty_var.get()
        self._status.configure(text=f"Generating {8 * qty} rows across 8 relationships...")
        threading.Thread(target=self._run_catalog, args=(qty,), daemon=True).start()

    def _run_catalog(self, qty: int) -> None:
        try:
            path = generate_bulk_catalog(quotes_per_relationship=qty)
            total = 8 * qty
            summary = (
                f"✓ Bulk catalog generated!\n\n"
                f"  Total rows: {total} ({qty} per relationship)\n"
                f"  Relationships: {', '.join(BULK_CATALOG_RELATIONSHIPS)}\n"
                f"  Saved to: {path}\n\n"
                f"Next steps:\n"
                f"  1. Open the CSV in Excel\n"
                f"  2. Use each row as a separate Etsy listing\n"
                f"  3. Upload the quote to Bannerbear → download PNG\n"
                f"  4. Upload PNG to Gelato → publish to Etsy\n\n"
                f"Phase 12 tip: Create 3 listings per design:\n"
                f"  • Poster 18x24 (~$18)\n"
                f"  • Canvas 16x20 (~$45)\n"
                f"  • Framed 11x14 (~$55)\n"
                f"  = 3× revenue from the same design."
            )
            self.after(0, self._set_output, summary)
            self.after(0, self._status.configure, {"text": f"✓ {total} rows saved to {path.name}"})
            self.after(0, self._bar.stop)
            self.after(0, self._cat_btn.configure, {"state": "normal"})
        except Exception as exc:
            self.after(0, messagebox.showerror, "Error", str(exc))
            self.after(0, self._bar.stop)
            self.after(0, self._cat_btn.configure, {"state": "normal"})

    def _on_seo(self) -> None:
        niche = self._niche_var.get()
        pack = generate_seo_pack(niche)
        lines = [
            f"SEO Pack: {pack['niche']}\n",
            "── TITLES (use one per listing) ──",
        ]
        for t in pack["titles"]:
            lines.append(f"  • {t}")
        lines.append("\n── TAGS (13 tags, paste into Etsy tag boxes) ──")
        lines.append("  " + ", ".join(pack["tags"]))
        lines.append("\n── DESCRIPTION STARTERS ──")
        for d in pack["description_starters"]:
            lines.append(f"  • {d}")
        self._set_output("\n".join(lines))
        self._status.configure(text=f"SEO pack generated for: {niche}")
