"""Pipeline Monitor Tab — real-time 7-stage order status dashboard."""
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from quoteforge.config import OUTPUT_DIR


STAGE_LABELS = [
    ("1", "Order Intake",       "received"),
    ("2", "Quote Generation",   "quote_generated"),
    ("3", "Artwork Generation", "artwork_done"),
    ("4", "Drive Upload",       "artwork_stored"),
    ("5", "Proof",              "proof_sent"),
    ("6", "Gelato Production",  "in_production"),
    ("7", "Follow-up",          "shipped"),
]

STATUS_COLORS = {
    "received":        "#FFF2CC",
    "quote_generated": "#DEEBF7",
    "artwork_done":    "#E2EFDA",
    "artwork_stored":  "#E2EFDA",
    "proof_sent":      "#FCE4D6",
    "in_production":   "#D9E1F2",
    "shipped":         "#E2EFDA",
    "error":           "#FFCCCC",
    "pending":         "#F2F2F2",
}


class PipelineTab(tk.Frame):
    """Live pipeline monitor with order table, stage tracker, and action buttons."""

    def __init__(self, parent: tk.Widget):
        super().__init__(parent)
        self._build_ui()
        self._refresh()

    def _build_ui(self) -> None:
        pad = {"padx": 14, "pady": 4}

        tk.Label(self, text="Pipeline Monitor — 7-Stage Automation",
                 font=("Helvetica", 14, "bold")).pack(pady=(14, 2), padx=14, anchor="w")
        tk.Label(self,
                 text="Customer → Etsy → Quote → Artwork → Drive → Gelato → Follow-up",
                 font=("Helvetica", 9), fg="#555").pack(padx=14, anchor="w")
        ttk.Separator(self, orient="horizontal").pack(fill="x", pady=8)

        # ── Pipeline stages visual ───────────────────────────────
        stage_frame = tk.Frame(self)
        stage_frame.pack(fill="x", padx=14, pady=4)
        self._stage_labels: list[tk.Label] = []
        for num, label, _ in STAGE_LABELS:
            col_frame = tk.Frame(stage_frame)
            col_frame.pack(side="left", expand=True, fill="x", padx=2)
            num_lbl = tk.Label(col_frame, text=f"Stage {num}", font=("Helvetica", 8, "bold"),
                               bg="#1F4E79", fg="white", width=10)
            num_lbl.pack(fill="x")
            lbl = tk.Label(col_frame, text=label, font=("Helvetica", 8),
                           bg="#F2F2F2", width=10, wraplength=80)
            lbl.pack(fill="x")
            self._stage_labels.append(lbl)

        ttk.Separator(self, orient="horizontal").pack(fill="x", pady=8)

        # ── Stats row ────────────────────────────────────────────
        stats_frame = tk.Frame(self)
        stats_frame.pack(fill="x", padx=14)
        self._stat_vars: dict[str, tk.StringVar] = {}
        for stat in ["Total", "In Progress", "Shipped", "Errors"]:
            f = tk.Frame(stats_frame, relief="ridge", bd=1)
            f.pack(side="left", expand=True, fill="x", padx=4, pady=4)
            tk.Label(f, text=stat, font=("Helvetica", 9, "bold")).pack()
            var = tk.StringVar(value="—")
            self._stat_vars[stat] = var
            tk.Label(f, textvariable=var, font=("Helvetica", 18, "bold"),
                     fg="#1F4E79").pack()

        ttk.Separator(self, orient="horizontal").pack(fill="x", pady=8)

        # ── Order table ──────────────────────────────────────────
        tk.Label(self, text="Recent Orders", font=("Helvetica", 10, "bold"),
                 anchor="w").pack(fill="x", padx=14)

        table_frame = tk.Frame(self)
        table_frame.pack(fill="both", expand=True, padx=14, pady=4)

        cols = ("Order ID", "Recipient", "Occasion", "Status", "Created")
        self._tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=10)
        widths = [120, 120, 140, 140, 140]
        for col, w in zip(cols, widths):
            self._tree.heading(col, text=col)
            self._tree.column(col, width=w, anchor="center")

        sb = ttk.Scrollbar(table_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        # ── Action buttons ───────────────────────────────────────
        btn_frame = tk.Frame(self)
        btn_frame.pack(fill="x", padx=14, pady=8)
        ttk.Button(btn_frame, text="↻ Refresh",
                   command=self._refresh).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="▶ Run Pipeline for Selected",
                   command=self._on_run_selected).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="✓ Approve Proof",
                   command=self._on_approve_proof).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="📊 Open Order Tracker",
                   command=self._open_tracker).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="🚀 Start Webhook Server",
                   command=self._start_webhook).pack(side="left", padx=4)

        self._status_lbl = tk.Label(self, text="", anchor="w", font=("Helvetica", 9))
        self._status_lbl.pack(fill="x", padx=14)

    def _refresh(self) -> None:
        threading.Thread(target=self._load_orders, daemon=True).start()

    def _load_orders(self) -> None:
        try:
            from quoteforge.db.database import init_db, get_all_orders, get_order_stats
            init_db()
            orders = get_all_orders(limit=50)
            stats = get_order_stats()
            self.after(0, self._update_table, orders, stats)
        except Exception as exc:
            self.after(0, self._status_lbl.configure,
                       {"text": f"DB not ready yet: {exc}"})

    def _update_table(self, orders: list[dict], stats: dict) -> None:
        # Update stats
        by_status = stats.get("by_status", {})
        in_progress = sum(v for k, v in by_status.items()
                          if k not in ("shipped", "delivered", "error"))
        self._stat_vars["Total"].set(str(stats.get("total", 0)))
        self._stat_vars["In Progress"].set(str(in_progress))
        self._stat_vars["Shipped"].set(str(by_status.get("shipped", 0)))
        self._stat_vars["Errors"].set(str(by_status.get("error", 0)))

        # Update table
        for row in self._tree.get_children():
            self._tree.delete(row)
        for o in orders:
            status = o.get("status", "")
            bg = STATUS_COLORS.get(status, "#F2F2F2")
            self._tree.insert("", "end", values=(
                o.get("order_id", "")[:16],
                o.get("recipient_name", ""),
                o.get("occasion", ""),
                status,
                (o.get("created_at", "") or "")[:16],
            ), tags=(status,))
        for status, color in STATUS_COLORS.items():
            self._tree.tag_configure(status, background=color)

        self._status_lbl.configure(
            text=f"Last refreshed: {__import__('datetime').datetime.now().strftime('%H:%M:%S')} — {len(orders)} orders loaded")

    def _get_selected_order_id(self) -> str:
        sel = self._tree.selection()
        if not sel:
            messagebox.showwarning("No Selection", "Please select an order first.")
            return ""
        return self._tree.item(sel[0])["values"][0]

    def _on_run_selected(self) -> None:
        oid = self._get_selected_order_id()
        if not oid:
            return
        messagebox.showinfo("Pipeline",
                            f"To run the pipeline for order {oid}:\n\n"
                            "The Order Processor tab can generate the quote.\n"
                            "The full automated pipeline runs via the webhook server\n"
                            "or Make.com → POST /order")

    def _on_approve_proof(self) -> None:
        oid = self._get_selected_order_id()
        if not oid:
            return
        try:
            from quoteforge.db.database import update_order, log_pipeline_stage
            update_order(oid, proof_approved=1, status="artwork_done")
            log_pipeline_stage(oid, "proof", "approved", "Approved via GUI")
            messagebox.showinfo("Approved", f"Proof for {oid} approved!\nGelato upload can now proceed.")
            self._refresh()
        except Exception as exc:
            messagebox.showerror("Error", str(exc))

    def _open_tracker(self) -> None:
        path = OUTPUT_DIR / "QuoteForge_Order_Tracker.xlsx"
        if path.exists():
            subprocess.Popen(f'start "" "{path}"', shell=True)
        else:
            messagebox.showinfo("Not Found",
                                "Order Tracker not yet generated.\nGo to Order Processor tab → Export Excel Tracker.")

    def _start_webhook(self) -> None:
        messagebox.showinfo(
            "Start Webhook Server",
            "To start the webhook server:\n\n"
            "1. Open a new Command Prompt\n"
            "2. Run: python -m quoteforge.automation.webhook_server\n"
            "3. Server starts on port 5050\n"
            "4. Use ngrok or port forwarding for Zapier/Make.com\n\n"
            "See docs/MAKE_WORKFLOW.md for full setup."
        )
