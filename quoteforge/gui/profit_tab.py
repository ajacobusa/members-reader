"""Profit Calculator Tab — live business math for every product and scenario."""
import tkinter as tk
from tkinter import ttk, messagebox
import csv
import os

from quoteforge.etsy.profit_calculator import (
    calculate_order_profit,
    monthly_revenue_forecast,
    scaling_milestones,
)
from quoteforge.etsy.gelato_catalog import GELATO_CATALOG, calculate_profit, get_by_category

# ---------------------------------------------------------------------------
# Colour constants
# ---------------------------------------------------------------------------
_GREEN = "#1a7a1a"
_YELLOW = "#9c7a00"
_RED = "#b30000"
_BG_GREEN = "#d4f4d4"
_BG_YELLOW = "#fff3cc"
_BG_RED = "#ffd6d6"
_BG_HEADER = "#2c3e50"
_FG_HEADER = "#ecf0f1"


def _profit_color(profit: float) -> tuple[str, str]:
    """Return (foreground, background) colour pair based on profit level."""
    if profit >= 15:
        return (_GREEN, _BG_GREEN)
    if profit >= 5:
        return (_YELLOW, _BG_YELLOW)
    return (_RED, _BG_RED)


class _ScrollableFrame(tk.Frame):
    """A frame with an embedded vertical scrollbar."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        canvas = tk.Canvas(self, borderwidth=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.inner = tk.Frame(canvas)
        self.inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=self.inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        canvas.bind_all(
            "<MouseWheel>",
            lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"),
        )


def _header_label(parent, text: str, col: int, row: int, colspan: int = 1) -> None:
    tk.Label(
        parent,
        text=text,
        bg=_BG_HEADER,
        fg=_FG_HEADER,
        font=("Segoe UI", 9, "bold"),
        padx=8,
        pady=4,
    ).grid(row=row, column=col, columnspan=colspan, sticky="ew", padx=1, pady=1)


def _value_label(
    parent,
    text: str,
    col: int,
    row: int,
    fg: str = "#1a1a1a",
    bg: str = "#f9f9f9",
    bold: bool = False,
) -> tk.Label:
    font = ("Segoe UI", 9, "bold") if bold else ("Segoe UI", 9)
    lbl = tk.Label(parent, text=text, bg=bg, fg=fg, font=font, padx=6, pady=3, anchor="e")
    lbl.grid(row=row, column=col, sticky="ew", padx=1, pady=1)
    return lbl


# ===========================================================================
# Order Profit Tab
# ===========================================================================

class _OrderProfitTab(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg="#f5f5f5")
        self._build()

    def _build(self):
        # --- Input panel ---------------------------------------------------
        inp = tk.LabelFrame(self, text="Order Details", font=("Segoe UI", 10, "bold"),
                            bg="#f5f5f5", padx=12, pady=8)
        inp.pack(fill="x", padx=12, pady=(12, 6))

        fields = [
            ("Sale Price ($)", 5, 200, 29.99, 0.01),
            ("Gelato Cost ($)", 4, 80, 11.00, 0.01),
            ("Shipping Collected ($)", 0, 50, 0.00, 0.01),
            ("Shipping Cost ($)", 0, 50, 0.00, 0.01),
        ]
        self._vars: list[tk.DoubleVar] = []
        for i, (label, lo, hi, default, inc) in enumerate(fields):
            tk.Label(inp, text=label, bg="#f5f5f5",
                     font=("Segoe UI", 9)).grid(row=i, column=0, sticky="w", pady=3)
            var = tk.DoubleVar(value=default)
            self._vars.append(var)
            sb = ttk.Spinbox(inp, from_=lo, to=hi, increment=inc,
                             textvariable=var, width=10, format="%.2f")
            sb.grid(row=i, column=1, sticky="w", padx=(8, 0), pady=3)

        ttk.Button(inp, text="Calculate Profit", command=self._calculate).grid(
            row=len(fields), column=0, columnspan=2, pady=(10, 2), sticky="ew"
        )

        # --- Result panel --------------------------------------------------
        self._result_frame = tk.LabelFrame(
            self, text="Profit Breakdown", font=("Segoe UI", 10, "bold"),
            bg="#f5f5f5", padx=12, pady=8
        )
        self._result_frame.pack(fill="x", padx=12, pady=6)
        self._result_labels: dict[str, tk.Label] = {}
        rows = [
            ("Revenue", "revenue"),
            ("Shipping Collected", "shipping_in"),
            ("Gelato Cost", "gelato_cost"),
            ("Shipping Cost", "shipping_out"),
            ("Etsy Transaction Fee (6.5%)", "txn_fee"),
            ("Etsy Payment Fee (3.0%)", "pay_fee"),
            ("Etsy Listing Fee", "lst_fee"),
            ("Total Fees", "total_fees"),
            ("Net Profit", "net_profit"),
            ("Margin %", "margin"),
        ]
        for i, (label, key) in enumerate(rows):
            tk.Label(self._result_frame, text=label, bg="#f5f5f5",
                     font=("Segoe UI", 9)).grid(row=i, column=0, sticky="w", pady=2)
            lbl = tk.Label(self._result_frame, text="—", bg="#f5f5f5",
                           font=("Segoe UI", 9), anchor="e", width=12)
            lbl.grid(row=i, column=1, sticky="ew", padx=(8, 0), pady=2)
            self._result_labels[key] = lbl

        # Profit verdict label
        self._verdict = tk.Label(self._result_frame, text="", bg="#f5f5f5",
                                  font=("Segoe UI", 11, "bold"))
        self._verdict.grid(row=len(rows), column=0, columnspan=2, pady=(8, 2))

    def _calculate(self):
        sale, gelato, ship_in, ship_out = (v.get() for v in self._vars)
        r = calculate_order_profit(sale, gelato, ship_in, ship_out)

        self._result_labels["revenue"].config(text=f"${sale:.2f}")
        self._result_labels["shipping_in"].config(text=f"${ship_in:.2f}")
        self._result_labels["gelato_cost"].config(text=f"${gelato:.2f}")
        self._result_labels["shipping_out"].config(text=f"${ship_out:.2f}")
        self._result_labels["txn_fee"].config(text=f"${r['etsy_transaction_fee']:.2f}")
        self._result_labels["pay_fee"].config(text=f"${r['etsy_payment_fee']:.2f}")
        self._result_labels["lst_fee"].config(text=f"${r['etsy_listing_fee']:.2f}")
        self._result_labels["total_fees"].config(text=f"${r['total_fees']:.2f}")

        profit = r["net_profit"]
        margin = r["margin_pct"]
        fg, bg = _profit_color(profit)
        self._result_labels["net_profit"].config(
            text=f"${profit:.2f}", fg=fg, bg=bg, font=("Segoe UI", 10, "bold")
        )
        self._result_labels["margin"].config(
            text=f"{margin:.1f}%", fg=fg, bg=bg, font=("Segoe UI", 10, "bold")
        )
        verdict_map = {
            profit >= 15: ("GREAT PROFIT!", _GREEN),
            5 <= profit < 15: ("MARGINAL PROFIT", _YELLOW),
            profit < 5: ("LOW / NO PROFIT", _RED),
        }
        for cond, (text, color) in verdict_map.items():
            if cond:
                self._verdict.config(text=text, fg=color)
                break


# ===========================================================================
# Monthly Forecast Tab
# ===========================================================================

class _MonthlyForecastTab(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg="#f5f5f5")
        self._build()

    def _build(self):
        inp = tk.LabelFrame(self, text="Forecast Inputs", font=("Segoe UI", 10, "bold"),
                            bg="#f5f5f5", padx=12, pady=8)
        inp.pack(fill="x", padx=12, pady=(12, 6))

        fields = [
            ("Avg Daily Sales", 0.1, 50, 5.0, 0.1),
            ("Avg Order Value ($)", 10, 200, 29.0, 0.5),
            ("Avg Gelato Cost ($)", 5, 80, 11.0, 0.5),
            ("Active Listings", 1, 5000, 100, 1),
            ("Monthly Ad Spend ($)", 0, 5000, 0.0, 5.0),
        ]
        self._vars: list[tk.DoubleVar] = []
        for i, (label, lo, hi, default, inc) in enumerate(fields):
            tk.Label(inp, text=label, bg="#f5f5f5",
                     font=("Segoe UI", 9)).grid(row=i, column=0, sticky="w", pady=3)
            var = tk.DoubleVar(value=default)
            self._vars.append(var)
            sb = ttk.Spinbox(inp, from_=lo, to=hi, increment=inc,
                             textvariable=var, width=12)
            sb.grid(row=i, column=1, sticky="w", padx=(8, 0), pady=3)

        ttk.Button(inp, text="Run Forecast", command=self._forecast).grid(
            row=len(fields), column=0, columnspan=2, pady=(10, 2), sticky="ew"
        )

        # Results
        self._res_frame = tk.LabelFrame(
            self, text="Monthly Forecast", font=("Segoe UI", 10, "bold"),
            bg="#f5f5f5", padx=12, pady=8
        )
        self._res_frame.pack(fill="x", padx=12, pady=6)
        self._res_labels: dict[str, tk.Label] = {}
        result_rows = [
            ("Monthly Orders", "orders"),
            ("Gross Revenue", "revenue"),
            ("Gelato Costs", "gelato"),
            ("Etsy Fees", "fees"),
            ("Listing Renewals", "renewals"),
            ("Ad Spend", "ads"),
            ("Net Profit", "profit"),
            ("ROI %", "roi"),
            ("Break-Even Orders", "breakeven"),
        ]
        for i, (label, key) in enumerate(result_rows):
            tk.Label(self._res_frame, text=label, bg="#f5f5f5",
                     font=("Segoe UI", 9)).grid(row=i, column=0, sticky="w", pady=2)
            lbl = tk.Label(self._res_frame, text="—", bg="#f5f5f5",
                           font=("Segoe UI", 9), anchor="e", width=14)
            lbl.grid(row=i, column=1, sticky="ew", padx=(8, 0), pady=2)
            self._res_labels[key] = lbl

        self._milestone_lbl = tk.Label(
            self._res_frame, text="", bg="#f5f5f5",
            font=("Segoe UI", 10, "bold"), wraplength=380, justify="left"
        )
        self._milestone_lbl.grid(
            row=len(result_rows), column=0, columnspan=2, pady=(10, 2), sticky="w"
        )

    def _forecast(self):
        daily, aov, cost, listings, ads = (v.get() for v in self._vars)
        r = monthly_revenue_forecast(daily, aov, cost, int(listings), ads)

        mapping = {
            "orders": f"{r['monthly_orders']:.0f}",
            "revenue": f"${r['gross_revenue']:,.2f}",
            "gelato": f"${r['gelato_costs']:,.2f}",
            "fees": f"${r['etsy_fees']:,.2f}",
            "renewals": f"${r['listing_renewals']:,.2f}",
            "ads": f"${r['ad_spend']:,.2f}",
            "profit": f"${r['net_profit']:,.2f}",
            "roi": f"{r['roi_pct']:.1f}%",
            "breakeven": f"{r['break_even_orders']:.1f} orders",
        }
        for key, val in mapping.items():
            self._res_labels[key].config(text=val)

        profit = r["net_profit"]
        fg, bg = _profit_color(profit)
        self._res_labels["profit"].config(fg=fg, bg=bg, font=("Segoe UI", 10, "bold"))

        # Determine which milestone
        milestones = scaling_milestones()
        current = milestones[0]
        for m in milestones:
            if listings >= m["listings"]:
                current = m
        self._milestone_lbl.config(
            text=f"Current Phase: {current['milestone']}\nFocus: {current['focus']}",
            fg=_GREEN,
        )


# ===========================================================================
# Scaling Milestones Tab
# ===========================================================================

class _ScalingMilestonesTab(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg="#f5f5f5")
        self._current_listings = tk.IntVar(value=0)
        self._build()

    def _build(self):
        ctrl = tk.Frame(self, bg="#f5f5f5")
        ctrl.pack(fill="x", padx=12, pady=(10, 4))
        tk.Label(ctrl, text="My Current Listings:", bg="#f5f5f5",
                 font=("Segoe UI", 9)).pack(side="left")
        ttk.Spinbox(
            ctrl, from_=0, to=5000, increment=1,
            textvariable=self._current_listings, width=8
        ).pack(side="left", padx=6)
        ttk.Button(ctrl, text="Highlight My Phase", command=self._refresh).pack(side="left", padx=4)
        ttk.Button(ctrl, text="Export to CSV", command=self._export).pack(side="left", padx=4)

        scroll = _ScrollableFrame(self, bg="#f5f5f5")
        scroll.pack(fill="both", expand=True, padx=12, pady=6)
        self._table = scroll.inner
        self._draw_table()

    def _draw_table(self, highlight_listings: int = -1):
        for w in self._table.winfo_children():
            w.destroy()

        headers = ["Phase", "Listings", "Daily Sales", "Monthly Revenue", "Monthly Profit", "Focus"]
        for col, h in enumerate(headers):
            _header_label(self._table, h, col, 0)

        milestones = scaling_milestones()
        for r, m in enumerate(milestones, start=1):
            is_current = highlight_listings >= 0 and m["listings"] <= highlight_listings
            bg = "#d0eaf8" if is_current else ("#ffffff" if r % 2 == 0 else "#f2f2f2")
            font = ("Segoe UI", 9, "bold") if is_current else ("Segoe UI", 9)
            vals = [
                m["milestone"],
                str(m["listings"]),
                str(m["daily_sales"]),
                f"${m['monthly_revenue']:,}",
                f"${m['monthly_profit']:,}",
                m["focus"],
            ]
            for col, val in enumerate(vals):
                anchor = "w" if col in (0, 5) else "center"
                tk.Label(self._table, text=val, bg=bg, font=font,
                         padx=6, pady=4, anchor=anchor).grid(
                    row=r, column=col, sticky="ew", padx=1, pady=1
                )

        for col in range(len(headers)):
            self._table.columnconfigure(col, weight=1)

    def _refresh(self):
        self._draw_table(self._current_listings.get())

    def _export(self):
        path = os.path.join(os.path.expanduser("~"), "Desktop", "scaling_milestones.csv")
        milestones = scaling_milestones()
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(milestones[0].keys()))
            writer.writeheader()
            writer.writerows(milestones)
        messagebox.showinfo("Exported", f"Saved to:\n{path}")


# ===========================================================================
# Product Margins Tab
# ===========================================================================

class _ProductMarginsTab(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg="#f5f5f5")
        self._category = tk.StringVar(value="poster")
        self._build()

    def _build(self):
        ctrl = tk.Frame(self, bg="#f5f5f5")
        ctrl.pack(fill="x", padx=12, pady=(10, 4))
        tk.Label(ctrl, text="Category:", bg="#f5f5f5",
                 font=("Segoe UI", 9)).pack(side="left")
        categories = sorted({p.category for p in GELATO_CATALOG})
        cb = ttk.Combobox(ctrl, textvariable=self._category,
                          values=categories, state="readonly", width=14)
        cb.pack(side="left", padx=6)
        ttk.Button(ctrl, text="Show Margins", command=self._refresh).pack(side="left", padx=4)

        scroll = _ScrollableFrame(self, bg="#f5f5f5")
        scroll.pack(fill="both", expand=True, padx=12, pady=6)
        self._table = scroll.inner
        self._draw_table("poster")

    def _draw_table(self, category: str):
        for w in self._table.winfo_children():
            w.destroy()

        products = get_by_category(category)
        if not products:
            tk.Label(self._table, text="No products found.", bg="#f5f5f5").pack()
            return

        headers = [
            "Product", "Gelato Cost",
            "Budget Price", "Budget Profit",
            "Mid Price", "Mid Profit",
            "Premium Price", "Premium Profit",
        ]
        for col, h in enumerate(headers):
            _header_label(self._table, h, col, 0)

        for r, p in enumerate(products, start=1):
            bg_row = "#ffffff" if r % 2 == 0 else "#f2f2f2"
            cells = [
                (p.name, "#1a1a1a", bg_row),
                (f"${p.gelato_cost_usd:.2f}", "#1a1a1a", bg_row),
            ]
            for tier in ("budget", "mid", "premium"):
                price = p.suggested_price.get(tier, 0.0)
                profit = p.profit_margin.get(tier, 0.0)
                fg, bg = _profit_color(profit)
                cells.append((f"${price:.2f}", "#1a1a1a", bg_row))
                cells.append((f"${profit:.2f}", fg, bg))

            for col, (text, fg, bg) in enumerate(cells):
                anchor = "w" if col == 0 else "center"
                tk.Label(self._table, text=text, bg=bg, fg=fg,
                         font=("Segoe UI", 9), padx=6, pady=3, anchor=anchor).grid(
                    row=r, column=col, sticky="ew", padx=1, pady=1
                )

        for col in range(len(headers)):
            self._table.columnconfigure(col, weight=1)

    def _refresh(self):
        self._draw_table(self._category.get())


# ===========================================================================
# Main ProfitTab
# ===========================================================================

class ProfitTab(tk.Frame):
    """Top-level Profit Calculator tab for the QuoteForge GUI."""

    def __init__(self, parent):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        inner = ttk.Notebook(self)
        inner.pack(fill="both", expand=True, padx=6, pady=6)

        tab_order = _OrderProfitTab(inner)
        inner.add(tab_order, text="  Order Profit  ")

        tab_monthly = _MonthlyForecastTab(inner)
        inner.add(tab_monthly, text="  Monthly Forecast  ")

        tab_scale = _ScalingMilestonesTab(inner)
        inner.add(tab_scale, text="  Scaling Milestones  ")

        tab_products = _ProductMarginsTab(inner)
        inner.add(tab_products, text="  Product Margins  ")
