"""Phase 6: Order Processor Tab.

Paste incoming Etsy order personalization → instant custom message generated.
10-15 minute manual fulfillment workflow, now reduced to 2 minutes.
"""
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from quoteforge.quotes.generator import OUTPUT_STYLES, OCCASIONS, SCENERY_OPTIONS, RELATIONSHIPS
from quoteforge.etsy.order_processor import (
    process_order,
    generate_post_purchase_email,
    ETSY_PERSONALIZATION_FORM,
)
from quoteforge.etsy.order_tracker import export_order_tracker
from quoteforge.config import OUTPUT_DIR

TONES = [
    "Faith & Prayer",
    "Inspirational & Motivational",
    "Emotional & Heartfelt",
    "Celebratory & Joyful",
    "Healing & Gentle",
    "Bold & Empowering",
]


class OrderTab(tk.Frame):
    """Etsy order fulfillment processor — paste order info, get message instantly."""

    def __init__(self, parent: tk.Widget):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        """Build all widgets for the order processor tab."""
        pad = {"padx": 14, "pady": 4}

        # Header
        tk.Label(self, text="Order Processor — Etsy Fulfillment",
                 font=("Helvetica", 14, "bold")).grid(
            row=0, column=0, columnspan=4, pady=(14, 2), padx=14, sticky="w")
        tk.Label(self, text="Paste customer order details → generate message in seconds.",
                 font=("Helvetica", 9), fg="#555").grid(
            row=1, column=0, columnspan=4, padx=14, sticky="w")
        ttk.Separator(self, orient="horizontal").grid(
            row=2, column=0, columnspan=4, sticky="ew", padx=14, pady=8)

        # Input fields
        labels_and_vars = [
            ("Recipient Name:", tk.StringVar(value="Emma")),
            ("Your Name (sender):", tk.StringVar(value="Mom")),
        ]
        self._recipient_var = labels_and_vars[0][1]
        self._sender_var = labels_and_vars[1][1]

        for i, (label, var) in enumerate(labels_and_vars, start=3):
            tk.Label(self, text=label, anchor="w").grid(row=i, column=0, sticky="w", **pad)
            tk.Entry(self, textvariable=var, width=36).grid(row=i, column=1, columnspan=3,
                                                             sticky="w", padx=4, pady=3)

        row = 5
        dropdowns = [
            ("Relationship:", RELATIONSHIPS, tk.StringVar(value="To My Daughter"), "_rel_var"),
            ("Occasion:", OCCASIONS, tk.StringVar(value="Graduation"), "_occ_var"),
            ("Scenery:", SCENERY_OPTIONS, tk.StringVar(value="Mountains"), "_scenery_var"),
            ("Message Tone:", TONES, tk.StringVar(value="Inspirational & Motivational"), "_tone_var"),
            ("Output Style:", OUTPUT_STYLES, tk.StringVar(value="Personal Letter"), "_style_var"),
        ]
        for label, values, var, attr in dropdowns:
            setattr(self, attr, var)
            tk.Label(self, text=label, anchor="w").grid(row=row, column=0, sticky="w", **pad)
            ttk.Combobox(self, textvariable=var, values=values,
                         state="readonly", width=34).grid(
                row=row, column=1, columnspan=3, sticky="w", padx=4, pady=3)
            row += 1

        # Memory / story
        tk.Label(self, text="Special Memory or Story:", anchor="w").grid(
            row=row, column=0, sticky="nw", **pad)
        self._memory = tk.Text(self, width=46, height=4, wrap="word", font=("Helvetica", 10))
        self._memory.grid(row=row, column=1, columnspan=3, padx=4, pady=4, sticky="w")
        row += 1

        # Variations
        tk.Label(self, text="Variations:", anchor="w").grid(row=row, column=0, sticky="w", **pad)
        self._count_var = tk.IntVar(value=3)
        ttk.Spinbox(self, from_=1, to=5, textvariable=self._count_var, width=5).grid(
            row=row, column=1, sticky="w", padx=4, pady=3)
        row += 1

        ttk.Separator(self, orient="horizontal").grid(
            row=row, column=0, columnspan=4, sticky="ew", padx=14, pady=8)
        row += 1

        # Action buttons
        btn_frame = tk.Frame(self)
        btn_frame.grid(row=row, column=0, columnspan=4, pady=4)
        self._gen_btn = ttk.Button(btn_frame, text="✦ Generate Message",
                                   command=self._on_generate)
        self._gen_btn.pack(side="left", padx=6)
        self._email_btn = ttk.Button(btn_frame, text="✉ Follow-Up Email",
                                     command=self._on_email)
        self._email_btn.pack(side="left", padx=6)
        self._form_btn = ttk.Button(btn_frame, text="📋 Copy Etsy Form",
                                    command=self._on_copy_form)
        self._form_btn.pack(side="left", padx=6)
        self._excel_btn = ttk.Button(btn_frame, text="📊 Export Excel Tracker",
                                     command=self._on_export_excel)
        self._excel_btn.pack(side="left", padx=6)
        row += 1

        # Progress
        self._bar = ttk.Progressbar(self, length=480, mode="indeterminate")
        self._bar.grid(row=row, column=0, columnspan=4, padx=14, pady=4)
        row += 1
        self._status = tk.Label(self, text="Fill in order details and click Generate.",
                                anchor="w", wraplength=500, font=("Helvetica", 9))
        self._status.grid(row=row, column=0, columnspan=4, sticky="w", padx=14)
        row += 1

        # Output
        tk.Label(self, text="Generated Output:", anchor="w",
                 font=("Helvetica", 10, "bold")).grid(
            row=row, column=0, columnspan=4, sticky="w", padx=14, pady=(10, 2))
        row += 1
        self._output = tk.Text(self, width=64, height=14, wrap="word",
                               font=("Helvetica", 10), state="disabled",
                               bg="#f9f9f9", relief="flat")
        self._output.grid(row=row, column=0, columnspan=4, padx=14, pady=4, sticky="ew")

        # Copy button
        row += 1
        ttk.Button(self, text="Copy Output to Clipboard",
                   command=self._copy_output).grid(row=row, column=0, columnspan=4, pady=4)

    def _set_output(self, text: str) -> None:
        """Replace the contents of the read-only output box."""
        self._output.configure(state="normal")
        self._output.delete("1.0", "end")
        self._output.insert("1.0", text)
        self._output.configure(state="disabled")

    def _copy_output(self) -> None:
        """Copy the output text to the clipboard."""
        text = self._output.get("1.0", "end").strip()
        self.clipboard_clear()
        self.clipboard_append(text)
        messagebox.showinfo("Copied", "Output copied to clipboard!")

    def _on_generate(self) -> None:
        """Start message generation on a background thread."""
        self._gen_btn.configure(state="disabled")
        self._bar.start(10)
        self._status.configure(text="Generating personalized message...")
        threading.Thread(target=self._run_generate, daemon=True).start()

    def _run_generate(self) -> None:
        """Process the order and display message variations (worker thread)."""
        try:
            result = process_order(
                recipient_name=self._recipient_var.get().strip() or "Friend",
                sender_name=self._sender_var.get().strip() or "Anonymous",
                relationship=self._rel_var.get(),
                occasion=self._occ_var.get(),
                scenery=self._scenery_var.get(),
                tone=self._tone_var.get(),
                memory=self._memory.get("1.0", "end").strip(),
                output_style=self._style_var.get(),
                variations=self._count_var.get(),
            )
            display = f"\n{'='*55}\n".join(result["variations"])
            self.after(0, self._set_output, display)
            self.after(0, self._status.configure,
                       {"text": f"✓ Done. {result['order_summary']}"})
            self.after(0, self._bar.stop)
            self.after(0, self._gen_btn.configure, {"state": "normal"})
        except Exception as exc:
            self.after(0, messagebox.showerror, "Error", str(exc))
            self.after(0, self._bar.stop)
            self.after(0, self._gen_btn.configure, {"state": "normal"})

    def _on_email(self) -> None:
        """Start follow-up email generation on a background thread."""
        self._email_btn.configure(state="disabled")
        self._bar.start(10)
        self._status.configure(text="Generating follow-up email...")
        threading.Thread(target=self._run_email, daemon=True).start()

    def _run_email(self) -> None:
        """Generate the post-purchase email and display it (worker thread)."""
        try:
            email = generate_post_purchase_email(
                recipient_name=self._recipient_var.get().strip() or "your recipient",
                occasion=self._occ_var.get(),
                sender_name=self._sender_var.get().strip() or "the customer",
            )
            self.after(0, self._set_output, f"--- Follow-Up Email ---\n\n{email}")
            self.after(0, self._status.configure, {"text": "✓ Email generated. Copy and send via Etsy."})
            self.after(0, self._bar.stop)
            self.after(0, self._email_btn.configure, {"state": "normal"})
        except Exception as exc:
            self.after(0, messagebox.showerror, "Error", str(exc))
            self.after(0, self._bar.stop)
            self.after(0, self._email_btn.configure, {"state": "normal"})

    def _on_export_excel(self) -> None:
        """Export the Excel order tracker and open it."""
        try:
            path = export_order_tracker()
            subprocess.Popen(f'start "" "{path}"', shell=True)
            messagebox.showinfo(
                "Excel Tracker Exported",
                f"Order tracker saved and opened:\n{path}\n\n"
                "3 sheets included:\n"
                "  • Orders — all orders with status dropdowns\n"
                "  • Dashboard — live counts by status\n"
                "  • SEO Reference — niche titles & tags",
            )
        except Exception as exc:
            messagebox.showerror("Export Error", str(exc))

    def _on_copy_form(self) -> None:
        """Copy the Etsy personalization form template to the clipboard."""
        self.clipboard_clear()
        self.clipboard_append(ETSY_PERSONALIZATION_FORM)
        self._set_output(
            "--- Etsy Personalization Form (copied to clipboard) ---\n\n"
            + ETSY_PERSONALIZATION_FORM
        )
        messagebox.showinfo("Copied",
                            "Etsy personalization form copied!\n\n"
                            "Paste this into your Etsy listing's Personalization section.")
