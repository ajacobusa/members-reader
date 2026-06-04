import threading
import tkinter as tk
from tkinter import ttk, messagebox

from quoteforge.gui.personal_tab import PersonalTab
from quoteforge.gui.order_tab import OrderTab
from quoteforge.gui.catalog_tab import CatalogTab
from quoteforge.gui.prompts_tab import PromptsTab
from quoteforge.quotes.categories import CATEGORIES
from quoteforge.pipeline import run_pipeline
from quoteforge.etsy.exporter import export_listings_csv
from quoteforge.config import OUTPUT_DIR, BANNERBEAR_TEMPLATE_UID
from quoteforge.gui.progress import ProgressTracker


def _build_bulk_tab(frame: tk.Frame) -> None:
    """Standard bulk generator UI embedded in a tab."""
    pad = {"padx": 16, "pady": 5}

    tk.Label(frame, text="QuoteForge", font=("Helvetica", 20, "bold")).pack(pady=(18, 2))
    tk.Label(frame, text="Bulk Wall Art Generator — Etsy + Gelato",
             font=("Helvetica", 10)).pack()
    ttk.Separator(frame, orient="horizontal").pack(fill="x", pady=10)

    tk.Label(frame, text="Category:", anchor="w").pack(fill="x", **pad)
    cat_var = tk.StringVar(value=list(CATEGORIES.keys())[0])
    cat_menu = ttk.Combobox(frame, textvariable=cat_var,
                            values=list(CATEGORIES.keys()), state="readonly", width=52)
    cat_menu.pack(**pad)

    tk.Label(frame, text="Sub-category:", anchor="w").pack(fill="x", **pad)
    sub_var = tk.StringVar()
    sub_menu = ttk.Combobox(frame, textvariable=sub_var, state="readonly", width=52)
    sub_menu.pack(**pad)

    def on_cat_change(*_: object) -> None:
        subs = CATEGORIES.get(cat_var.get(), {}).get("subcategories", [])
        sub_menu["values"] = subs
        if subs:
            sub_var.set(subs[0])

    cat_menu.bind("<<ComboboxSelected>>", on_cat_change)
    on_cat_change()

    tk.Label(frame, text="Number of designs:", anchor="w").pack(fill="x", **pad)
    count_var = tk.IntVar(value=5)
    ttk.Spinbox(frame, from_=1, to=50, textvariable=count_var, width=6).pack(**pad)

    bar = ttk.Progressbar(frame, length=520, mode="determinate")
    status = tk.Label(frame, text="Ready — select a category and click Generate.",
                      anchor="w", wraplength=520, font=("Helvetica", 9))

    def on_done(count: int) -> None:
        bar["value"] = 100
        status.configure(text=f"Done! {count} designs saved to {OUTPUT_DIR}")
        messagebox.showinfo(
            "QuoteForge",
            f"{count} designs saved!\n\nFolder: {OUTPUT_DIR}\n\nAlso saved: etsy_listings.csv",
        )
        btn.configure(state="normal")

    def run_gen() -> None:
        root = frame.winfo_toplevel()
        tracker = ProgressTracker(root, bar, status)

        def on_progress(current: int, total: int, quote: str) -> None:
            tracker.update(current, total, f"Rendering: {quote[:50]}")

        try:
            results = run_pipeline(
                category=cat_var.get(),
                subcategory=sub_var.get(),
                count=count_var.get(),
                template_uid=BANNERBEAR_TEMPLATE_UID,
                output_dir=OUTPUT_DIR,
                on_progress=on_progress,
            )
            listings = [
                {**r["listing"], "quote": r["quote"], "category": cat_var.get()}
                for r in results
            ]
            export_listings_csv(listings, OUTPUT_DIR)
            root.after(0, on_done, len(results))
        except Exception as exc:
            frame.winfo_toplevel().after(0, messagebox.showerror, "Error", str(exc))
            frame.winfo_toplevel().after(0, btn.configure, {"state": "normal"})

    def on_generate() -> None:
        btn.configure(state="disabled")
        bar["value"] = 0
        status.configure(text="Starting generation...")
        threading.Thread(target=run_gen, daemon=True).start()

    btn = ttk.Button(frame, text="✦ Generate Designs", command=on_generate)
    btn.pack(pady=12)
    bar.pack(padx=16, pady=4)
    status.pack(fill="x", padx=16, pady=4)


def main() -> None:
    root = tk.Tk()
    root.title("QuoteForge — Professional Wall Art Generator")
    root.geometry("680x860")
    root.resizable(False, False)

    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True)

    # Tab 1: Bulk generator
    tab1 = tk.Frame(notebook)
    notebook.add(tab1, text="  Bulk Generator  ")
    _build_bulk_tab(tab1)

    # Tab 2: Premium personalized messages
    tab2 = PersonalTab(notebook)
    notebook.add(tab2, text="  Custom Messages ✦  ")

    # Tab 3: Order processor (Etsy fulfillment workflow)
    tab3 = OrderTab(notebook)
    notebook.add(tab3, text="  Order Processor  ")

    # Tab 4: Bulk catalog + SEO packs
    tab4 = CatalogTab(notebook)
    notebook.add(tab4, text="  Catalog & SEO  ")

    # Tab 5: Quote prompts + customer messages
    tab5 = PromptsTab(notebook)
    notebook.add(tab5, text="  Prompts & Messages  ")

    root.mainloop()


if __name__ == "__main__":
    main()
