"""Personalized Custom Message tab — the premium product generator."""
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

from quoteforge.quotes.generator import (
    generate_personal_message,
    OUTPUT_STYLES,
    RELATIONSHIPS,
    OCCASIONS,
    SCENERY_OPTIONS,
)
from quoteforge.config import OUTPUT_DIR

# Pricing tiers shown to the user as a reference
PRICING_TIERS = {
    "Custom Quote only ($14.99)": 1,
    "Custom Quote + Name ($24.99)": 2,
    "Full Personal Story ($39.99)": 3,
    "Premium Framed Poster ($59.99)": 3,
}


class PersonalTab(tk.Frame):
    """A Tkinter Frame that renders the full personalized message generator UI."""

    def __init__(self, parent: tk.Widget):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        pad = {"padx": 14, "pady": 4}

        # ── Header ──────────────────────────────────────────────
        tk.Label(self, text="Custom Personal Message Generator",
                 font=("Helvetica", 14, "bold")).grid(row=0, column=0, columnspan=4,
                                                       pady=(14, 2), padx=14, sticky="w")
        tk.Label(self, text="Create personalized posters customers pay premium prices for.",
                 font=("Helvetica", 9), fg="#555").grid(row=1, column=0, columnspan=4,
                                                         padx=14, sticky="w")
        ttk.Separator(self, orient="horizontal").grid(row=2, column=0, columnspan=4,
                                                       sticky="ew", padx=14, pady=8)

        # ── Row labels & fields ─────────────────────────────────
        fields = [
            ("Relationship:", "relationship"),
            ("Recipient Name:", "recipient"),
            ("Your Name (sender):", "sender"),
            ("Occasion:", "occasion"),
            ("Favorite Scenery:", "scenery"),
            ("Output Style:", "style"),
            ("Pricing Tier:", "tier"),
        ]

        self._relationship_var = tk.StringVar(value=RELATIONSHIPS[6])   # To My Daughter
        self._recipient_var = tk.StringVar(value="Emma")
        self._sender_var = tk.StringVar(value="Mom")
        self._occasion_var = tk.StringVar(value="Graduation")
        self._scenery_var = tk.StringVar(value="Mountains")
        self._style_var = tk.StringVar(value="Personal Letter")
        self._tier_var = tk.StringVar(value=list(PRICING_TIERS.keys())[2])

        widgets = [
            ttk.Combobox(self, textvariable=self._relationship_var,
                         values=RELATIONSHIPS, state="readonly", width=32),
            tk.Entry(self, textvariable=self._recipient_var, width=35),
            tk.Entry(self, textvariable=self._sender_var, width=35),
            ttk.Combobox(self, textvariable=self._occasion_var,
                         values=OCCASIONS, state="readonly", width=32),
            ttk.Combobox(self, textvariable=self._scenery_var,
                         values=SCENERY_OPTIONS, state="readonly", width=32),
            ttk.Combobox(self, textvariable=self._style_var,
                         values=OUTPUT_STYLES, state="readonly", width=32),
            ttk.Combobox(self, textvariable=self._tier_var,
                         values=list(PRICING_TIERS.keys()), state="readonly", width=32),
        ]

        for i, ((label, _), widget) in enumerate(zip(fields, widgets), start=3):
            tk.Label(self, text=label, anchor="w").grid(row=i, column=0, sticky="w", **pad)
            widget.grid(row=i, column=1, columnspan=3, sticky="w", padx=4, pady=3)

        # ── Memory / Story (multi-line) ──────────────────────────
        row = 3 + len(fields)
        tk.Label(self, text="Special Memory or Story:", anchor="w").grid(
            row=row, column=0, sticky="nw", **pad)
        self._memory_text = tk.Text(self, width=45, height=4, wrap="word",
                                    font=("Helvetica", 10))
        self._memory_text.grid(row=row, column=1, columnspan=3, padx=4, pady=4, sticky="w")
        self._memory_text.insert("1.0",
            "She worked so hard for four years and never gave up, even when it was really difficult.")

        # ── Variations count ────────────────────────────────────
        row += 1
        tk.Label(self, text="Variations to generate:", anchor="w").grid(
            row=row, column=0, sticky="w", **pad)
        self._count_var = tk.IntVar(value=3)
        ttk.Spinbox(self, from_=1, to=5, textvariable=self._count_var, width=5).grid(
            row=row, column=1, sticky="w", padx=4, pady=3)

        ttk.Separator(self, orient="horizontal").grid(
            row=row + 1, column=0, columnspan=4, sticky="ew", padx=14, pady=8)

        # ── Generate button ──────────────────────────────────────
        self._btn = ttk.Button(self, text="✦ Generate Personal Message",
                               command=self._on_generate)
        self._btn.grid(row=row + 2, column=0, columnspan=4, pady=6)

        # ── Progress bar + status ────────────────────────────────
        self._bar = ttk.Progressbar(self, length=460, mode="indeterminate")
        self._bar.grid(row=row + 3, column=0, columnspan=4, padx=14, pady=4)
        self._status = tk.Label(self, text="Fill in the details above and click Generate.",
                                anchor="w", wraplength=480, font=("Helvetica", 9))
        self._status.grid(row=row + 4, column=0, columnspan=4, sticky="w", padx=14)

        # ── Output preview ───────────────────────────────────────
        tk.Label(self, text="Generated Output (preview — saved to Desktop folder):",
                 anchor="w", font=("Helvetica", 10, "bold")).grid(
            row=row + 5, column=0, columnspan=4, sticky="w", padx=14, pady=(10, 2))
        self._output_text = tk.Text(self, width=62, height=12, wrap="word",
                                    font=("Helvetica", 10), state="disabled",
                                    bg="#f9f9f9", relief="flat")
        self._output_text.grid(row=row + 6, column=0, columnspan=4,
                               padx=14, pady=4, sticky="ew")

    # ── Helpers ──────────────────────────────────────────────────

    def _set_output(self, text: str) -> None:
        self._output_text.configure(state="normal")
        self._output_text.delete("1.0", "end")
        self._output_text.insert("1.0", text)
        self._output_text.configure(state="disabled")

    def _set_status(self, text: str) -> None:
        self._status.configure(text=text)

    # ── Event handlers ───────────────────────────────────────────

    def _on_generate(self) -> None:
        self._btn.configure(state="disabled")
        self._bar.start(10)
        self._set_status("Generating your personalized message...")
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        try:
            relationship = self._relationship_var.get()
            recipient = self._recipient_var.get().strip() or "Friend"
            sender = self._sender_var.get().strip() or "Anonymous"
            occasion = self._occasion_var.get()
            scenery = self._scenery_var.get()
            style = self._style_var.get()
            memory = self._memory_text.get("1.0", "end").strip()
            count = self._count_var.get()

            variations = generate_personal_message(
                relationship=relationship,
                recipient_name=recipient,
                sender_name=sender,
                occasion=occasion,
                memory_or_story=memory,
                scenery=scenery,
                output_style=style,
                count=count,
            )

            # Save to output folder
            out_dir = OUTPUT_DIR / "Custom Messages" / occasion
            out_dir.mkdir(parents=True, exist_ok=True)
            safe_name = recipient.replace(" ", "_")
            saved_paths = []
            for i, text in enumerate(variations, 1):
                path = out_dir / f"{safe_name}_{style.replace(' ', '_')}_{i:02d}.txt"
                path.write_text(text, encoding="utf-8")
                saved_paths.append(path)

            display = f"\n{'='*50}\n".join(variations)
            self.after(0, self._set_output, display)
            self.after(0, self._set_status,
                       f"✓ {len(variations)} variations saved to: {out_dir}")
            self.after(0, self._bar.stop)
            self.after(0, self._btn.configure, {"state": "normal"})

        except Exception as exc:
            self.after(0, messagebox.showerror, "Error", str(exc))
            self.after(0, self._bar.stop)
            self.after(0, self._btn.configure, {"state": "normal"})
