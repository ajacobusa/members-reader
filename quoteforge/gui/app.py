"""Main QuoteForge application window for generating wall art designs."""
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from quoteforge.quotes.categories import CATEGORIES
from quoteforge.pipeline import run_pipeline
from quoteforge.quotes.generator import (
    generate_life_chapter,
    generate_family_legacy,
    generate_letter_to_future_self,
)
from quoteforge.etsy.exporter import export_listings_csv
from quoteforge.config import OUTPUT_DIR, BANNERBEAR_TEMPLATE_UID
from quoteforge.gui.progress import ProgressTracker

# Categories that trigger personalized input fields
PERSONALIZED_CATEGORIES = {
    "Personalized — Life Chapters",
    "Personalized — Family Legacy",
}


class QuoteForgeApp:
    """Main QuoteForge window: category-driven wall art design generator."""

    def __init__(self, root: tk.Tk):
        self._root = root
        root.title("QuoteForge — Wall Art Generator")
        root.geometry("560x600")
        root.resizable(False, False)
        self._build_ui()

    def _build_ui(self) -> None:
        """Build all widgets for the main window."""
        pad = {"padx": 16, "pady": 5}

        tk.Label(self._root, text="QuoteForge", font=("Helvetica", 20, "bold")).pack(pady=(18, 2))
        tk.Label(self._root, text="Professional Wall Art for Etsy + Gelato", font=("Helvetica", 10)).pack()
        ttk.Separator(self._root, orient="horizontal").pack(fill="x", pady=10)

        # Category
        tk.Label(self._root, text="Category:", anchor="w").pack(fill="x", **pad)
        self._cat_var = tk.StringVar(value=list(CATEGORIES.keys())[0])
        self._cat_menu = ttk.Combobox(self._root, textvariable=self._cat_var,
                                      values=list(CATEGORIES.keys()), state="readonly", width=48)
        self._cat_menu.pack(**pad)
        self._cat_menu.bind("<<ComboboxSelected>>", self._on_category_change)

        # Sub-category
        tk.Label(self._root, text="Sub-category:", anchor="w").pack(fill="x", **pad)
        self._sub_var = tk.StringVar()
        self._sub_menu = ttk.Combobox(self._root, textvariable=self._sub_var, state="readonly", width=48)
        self._sub_menu.pack(**pad)

        # Count
        tk.Label(self._root, text="Number of designs:", anchor="w").pack(fill="x", **pad)
        self._count_var = tk.IntVar(value=5)
        ttk.Spinbox(self._root, from_=1, to=50, textvariable=self._count_var, width=6).pack(**pad)

        ttk.Separator(self._root, orient="horizontal").pack(fill="x", pady=8)

        # --- Personalized fields (shown/hidden based on category) ---
        self._personal_frame = tk.Frame(self._root)
        self._personal_frame.pack(fill="x")

        # Life Chapters fields
        self._chapter_frame = tk.Frame(self._personal_frame)
        tk.Label(self._chapter_frame, text="Name:", anchor="w").grid(row=0, column=0, sticky="w", padx=16, pady=3)
        self._name_var = tk.StringVar()
        tk.Entry(self._chapter_frame, textvariable=self._name_var, width=30).grid(row=0, column=1, padx=4)
        tk.Label(self._chapter_frame, text="Age:", anchor="w").grid(row=1, column=0, sticky="w", padx=16, pady=3)
        self._age_var = tk.StringVar(value="23")
        tk.Entry(self._chapter_frame, textvariable=self._age_var, width=6).grid(row=1, column=1, sticky="w", padx=4)
        tk.Label(self._chapter_frame, text="Goal/Milestone:", anchor="w").grid(row=2, column=0, sticky="w", padx=16, pady=3)
        self._goal_var = tk.StringVar()
        tk.Entry(self._chapter_frame, textvariable=self._goal_var, width=30).grid(row=2, column=1, padx=4)

        # Family Legacy fields
        self._family_frame = tk.Frame(self._personal_frame)
        tk.Label(self._family_frame, text="Family Name:", anchor="w").grid(row=0, column=0, sticky="w", padx=16, pady=3)
        self._family_name_var = tk.StringVar()
        tk.Entry(self._family_frame, textvariable=self._family_name_var, width=30).grid(row=0, column=1, padx=4)
        tk.Label(self._family_frame, text="Core Values:", anchor="w").grid(row=1, column=0, sticky="w", padx=16, pady=3)
        self._values_var = tk.StringVar(value="Faith, Service, Generosity")
        tk.Entry(self._family_frame, textvariable=self._values_var, width=30).grid(row=1, column=1, padx=4)

        ttk.Separator(self._root, orient="horizontal").pack(fill="x", pady=8)

        self._btn = ttk.Button(self._root, text="✦ Generate Designs", command=self._on_generate)
        self._btn.pack(pady=10)

        self._bar = ttk.Progressbar(self._root, length=480, mode="determinate")
        self._bar.pack(padx=16, pady=4)
        self._status = tk.Label(self._root, text="Ready — select a category and click Generate.",
                                anchor="w", wraplength=500, font=("Helvetica", 9))
        self._status.pack(fill="x", padx=16, pady=4)

        self._on_category_change()

    def _on_category_change(self, *_) -> None:
        """Refresh sub-categories and toggle personalized fields for the category."""
        cat = self._cat_var.get()
        subs = CATEGORIES.get(cat, {}).get("subcategories", [])
        self._sub_menu["values"] = subs
        if subs:
            self._sub_var.set(subs[0])
        # Show/hide personalized fields
        self._chapter_frame.pack_forget()
        self._family_frame.pack_forget()
        if cat == "Personalized — Life Chapters":
            self._chapter_frame.pack(fill="x")
        elif cat == "Personalized — Family Legacy":
            self._family_frame.pack(fill="x")

    def _on_generate(self) -> None:
        """Start generation on a background thread and lock the UI."""
        self._btn.configure(state="disabled")
        self._bar["value"] = 0
        self._status.configure(text="Starting generation...")
        threading.Thread(target=self._run_generation, daemon=True).start()

    def _run_generation(self) -> None:
        """Dispatch generation to the right workflow (worker thread)."""
        cat = self._cat_var.get()
        sub = self._sub_var.get()
        count = self._count_var.get()
        tracker = ProgressTracker(self._root, self._bar, self._status)

        try:
            if cat == "Personalized — Life Chapters":
                self._run_life_chapters(count, tracker)
            elif cat == "Personalized — Family Legacy":
                self._run_family_legacy(count, tracker)
            else:
                self._run_standard(cat, sub, count, tracker)
        except Exception as exc:
            self._root.after(0, messagebox.showerror, "Error", str(exc))
            self._root.after(0, self._btn.configure, {"state": "normal"})

    def _run_standard(self, cat: str, sub: str, count: int, tracker: ProgressTracker) -> None:
        """Run the full design pipeline for a standard category and export listings."""
        def on_progress(current, total, quote):
            """Relay pipeline progress to the GUI tracker."""
            tracker.update(current, total, f"Rendering: {quote[:50]}")

        results = run_pipeline(
            category=cat,
            subcategory=sub,
            count=count,
            template_uid=BANNERBEAR_TEMPLATE_UID,
            output_dir=OUTPUT_DIR,
            on_progress=on_progress,
        )
        listings = [{**r["listing"], "quote": r["quote"], "category": cat} for r in results]
        export_listings_csv(listings, OUTPUT_DIR)
        self._root.after(0, self._on_done, len(results))

    def _run_life_chapters(self, count: int, tracker: ProgressTracker) -> None:
        """Generate Life Chapter poster texts and save them as .txt files."""
        name = self._name_var.get().strip()
        goal = self._goal_var.get().strip()
        age_str = self._age_var.get().strip()
        if not name or not goal:
            self._root.after(0, messagebox.showerror, "Missing Info",
                             "Please enter a Name and Goal for Life Chapters.")
            self._root.after(0, self._btn.configure, {"state": "normal"})
            return
        try:
            age = int(age_str)
        except ValueError:
            age = 23
        tracker.update(0, count, f"Generating Life Chapter for {name}...")
        variations = generate_life_chapter(name, age, goal, count=count)
        # Save text files to output folder — user pastes into Canva or Bannerbear
        out_dir = OUTPUT_DIR / "Life Chapters"
        out_dir.mkdir(parents=True, exist_ok=True)
        for i, text in enumerate(variations, 1):
            path = out_dir / f"{name.replace(' ', '_')}_chapter_{i:02d}.txt"
            path.write_text(text, encoding="utf-8")
            tracker.update(i, len(variations), f"Saved variation {i}")
        self._root.after(0, self._on_done_text, len(variations), out_dir)

    def _run_family_legacy(self, count: int, tracker: ProgressTracker) -> None:
        """Generate Family Legacy poster texts and save them as .txt files."""
        family = self._family_name_var.get().strip()
        values = self._values_var.get().strip()
        if not family:
            self._root.after(0, messagebox.showerror, "Missing Info",
                             "Please enter the Family Name.")
            self._root.after(0, self._btn.configure, {"state": "normal"})
            return
        tracker.update(0, count, f"Generating Legacy posters for the {family} Family...")
        variations = generate_family_legacy(family, values, count=count)
        out_dir = OUTPUT_DIR / "Family Legacy"
        out_dir.mkdir(parents=True, exist_ok=True)
        for i, text in enumerate(variations, 1):
            path = out_dir / f"{family.replace(' ', '_')}_legacy_{i:02d}.txt"
            path.write_text(text, encoding="utf-8")
            tracker.update(i, len(variations), f"Saved variation {i}")
        self._root.after(0, self._on_done_text, len(variations), out_dir)

    def _on_done(self, count: int) -> None:
        """Show completion state for standard design runs (main thread)."""
        self._bar["value"] = 100
        self._status.configure(text=f"Done! {count} designs saved to {OUTPUT_DIR}")
        messagebox.showinfo(
            "QuoteForge",
            f"{count} designs saved!\n\nFolder: {OUTPUT_DIR}\n\nAlso saved: etsy_listings.csv"
        )
        self._btn.configure(state="normal")

    def _on_done_text(self, count: int, out_dir) -> None:
        """Show completion state for personalized text-file runs (main thread)."""
        self._bar["value"] = 100
        self._status.configure(text=f"Done! {count} text files saved.")
        messagebox.showinfo(
            "QuoteForge — Personalized",
            f"{count} poster text files saved!\n\nFolder: {out_dir}\n\n"
            "Open each .txt file, copy the text into your Bannerbear or Canva template."
        )
        self._btn.configure(state="normal")
