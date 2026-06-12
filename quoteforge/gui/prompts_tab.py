"""Prompts & Customer Messages tab.

Implements:
- ChatGPT_Quote_Prompts.txt: 3 prompt templates (Heartfelt, Christian, Graduation)
- Customer_Message_Templates.docx: 4 Etsy communication messages
"""
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from quoteforge.quotes.generator import (
    generate_heartfelt_message,
    generate_christian_encouragement,
    generate_graduation_message,
)
from quoteforge.etsy.customer_messages import (
    generate_personalized_customer_message,
    get_all_base_templates_formatted,
    get_base_template,
    MESSAGE_TYPES,
    MESSAGE_TONES,
    BASE_TEMPLATES,
)
from quoteforge.quotes.generator import OCCASIONS

TONES = [
    "Inspirational & Uplifting",
    "Warm & Heartfelt",
    "Faith-Based & Spiritual",
    "Bold & Celebratory",
    "Gentle & Healing",
]

BIBLE_THEMES = [
    "God's faithfulness",
    "Strength & courage",
    "Hope & future",
    "Peace & stillness",
    "Grace & forgiveness",
    "Love & compassion",
    "Purpose & calling",
    "Healing & restoration",
    "Trust & surrender",
    "Joy in all seasons",
]


class PromptsTab(tk.Frame):
    """Two-section tab: Quote Prompts + Customer Messages."""

    def __init__(self, parent: tk.Widget):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        """Assemble the two sub-tabs into an inner notebook."""
        # Use inner notebook for sub-tabs
        inner = ttk.Notebook(self)
        inner.pack(fill="both", expand=True, padx=6, pady=6)

        # Sub-tab A: Quote Prompt Templates
        frame_a = tk.Frame(inner)
        inner.add(frame_a, text="  Quote Prompts  ")
        self._build_prompts(frame_a)

        # Sub-tab B: Customer Messages
        frame_b = tk.Frame(inner)
        inner.add(frame_b, text="  Customer Messages  ")
        self._build_customer_messages(frame_b)

    # ── SECTION A: Quote Prompt Templates ───────────────────────

    def _build_prompts(self, frame: tk.Frame) -> None:
        """Build the Quote Prompts sub-tab widgets."""
        pad = {"padx": 14, "pady": 4}

        tk.Label(frame, text="Quote Prompt Templates",
                 font=("Helvetica", 14, "bold")).grid(
            row=0, column=0, columnspan=4, pady=(14, 2), padx=14, sticky="w")
        tk.Label(frame,
                 text="3 targeted prompt templates: Heartfelt Message · Christian Letter · Graduation",
                 font=("Helvetica", 9), fg="#555").grid(
            row=1, column=0, columnspan=4, padx=14, sticky="w")
        ttk.Separator(frame, orient="horizontal").grid(
            row=2, column=0, columnspan=4, sticky="ew", padx=14, pady=8)

        # Prompt type selector
        tk.Label(frame, text="Prompt Type:", anchor="w").grid(
            row=3, column=0, sticky="w", **pad)
        self._prompt_type = tk.StringVar(value="Heartfelt Personalized Message")
        prompt_types = [
            "Heartfelt Personalized Message",
            "Christian Encouragement Letter",
            "Graduation Message",
        ]
        self._prompt_menu = ttk.Combobox(frame, textvariable=self._prompt_type,
                                          values=prompt_types, state="readonly", width=36)
        self._prompt_menu.grid(row=3, column=1, columnspan=3, sticky="w", padx=4, pady=3)
        self._prompt_menu.bind("<<ComboboxSelected>>", self._on_prompt_type_change)

        # ── Heartfelt fields ─────────────────────────────────────
        self._heartfelt_frame = tk.LabelFrame(frame, text="Heartfelt Message Details",
                                               font=("Helvetica", 9, "bold"), padx=8, pady=6)
        _f = self._heartfelt_frame
        self._hf_recipient = self._labeled_entry(_f, 0, "Recipient Name:", "Emma")
        self._hf_occasion   = self._labeled_combo(_f, 1, "Occasion:", list(OCCASIONS), "Graduation")
        self._hf_relation   = self._labeled_entry(_f, 2, "Relationship:", "Daughter")
        self._hf_tone       = self._labeled_combo(_f, 3, "Tone:", TONES,
                                                   "Warm & Heartfelt")
        self._hf_length     = self._labeled_spinbox(_f, 4, "Word Count:", 80, 300, 120)

        # ── Christian encouragement fields ───────────────────────
        self._christian_frame = tk.LabelFrame(frame, text="Christian Encouragement Details",
                                               font=("Helvetica", 9, "bold"), padx=8, pady=6)
        _c = self._christian_frame
        self._ch_recipient  = self._labeled_entry(_c, 0, "Recipient Name:", "Sarah")
        self._ch_challenge  = self._labeled_entry(_c, 1, "Challenge They Face:",
                                                   "Dental school boards exam")
        self._ch_theme      = self._labeled_combo(_c, 2, "Favorite Bible Theme:",
                                                   BIBLE_THEMES, "Strength & courage")

        # ── Graduation fields ─────────────────────────────────────
        self._grad_frame = tk.LabelFrame(frame, text="Graduation Message Details",
                                          font=("Helvetica", 9, "bold"), padx=8, pady=6)
        _g = self._grad_frame
        self._gr_name   = self._labeled_entry(_g, 0, "Graduate's Name:", "Michael")
        self._gr_degree = self._labeled_entry(_g, 1, "Degree:", "Doctor of Dental Surgery (DDS)")
        self._gr_goal   = self._labeled_entry(_g, 2, "Career Goal:", "Open a dental practice")

        # Variations count (shared)
        self._prompt_count = tk.IntVar(value=3)

        row = 4
        for f in [self._heartfelt_frame, self._christian_frame, self._grad_frame]:
            f.grid(row=row, column=0, columnspan=4, padx=14, pady=4, sticky="ew")
        self._on_prompt_type_change()

        # Shared controls
        ctrl_row = row + 1
        tk.Label(frame, text="Variations:", anchor="w").grid(
            row=ctrl_row, column=0, sticky="w", **pad)
        ttk.Spinbox(frame, from_=1, to=5, textvariable=self._prompt_count, width=5).grid(
            row=ctrl_row, column=1, sticky="w", padx=4)

        self._prompt_btn = ttk.Button(frame, text="✦ Generate",
                                       command=self._on_prompt_generate)
        self._prompt_btn.grid(row=ctrl_row + 1, column=0, columnspan=4, pady=8)

        self._prompt_bar = ttk.Progressbar(frame, length=480, mode="indeterminate")
        self._prompt_bar.grid(row=ctrl_row + 2, column=0, columnspan=4, padx=14, pady=3)
        self._prompt_status = tk.Label(frame, text="Select a prompt type and fill in the details.",
                                        anchor="w", font=("Helvetica", 9))
        self._prompt_status.grid(row=ctrl_row + 3, column=0, columnspan=4, sticky="w", padx=14)

        tk.Label(frame, text="Output:", font=("Helvetica", 10, "bold"), anchor="w").grid(
            row=ctrl_row + 4, column=0, columnspan=4, sticky="w", padx=14, pady=(8, 2))
        self._prompt_output = tk.Text(frame, width=64, height=12, wrap="word",
                                       font=("Helvetica", 10), state="disabled",
                                       bg="#f9f9f9", relief="flat")
        self._prompt_output.grid(row=ctrl_row + 5, column=0, columnspan=4,
                                  padx=14, pady=4, sticky="ew")
        ttk.Button(frame, text="Copy to Clipboard",
                   command=lambda: self._copy(self._prompt_output)).grid(
            row=ctrl_row + 6, column=0, columnspan=4, pady=4)

    def _on_prompt_type_change(self, *_: object) -> None:
        """Show only the field frame matching the selected prompt type."""
        pt = self._prompt_type.get()
        self._heartfelt_frame.grid_remove()
        self._christian_frame.grid_remove()
        self._grad_frame.grid_remove()
        if pt == "Heartfelt Personalized Message":
            self._heartfelt_frame.grid()
        elif pt == "Christian Encouragement Letter":
            self._christian_frame.grid()
        elif pt == "Graduation Message":
            self._grad_frame.grid()

    def _on_prompt_generate(self) -> None:
        """Start prompt generation on a background thread."""
        self._prompt_btn.configure(state="disabled")
        self._prompt_bar.start(10)
        self._prompt_status.configure(text="Generating...")
        threading.Thread(target=self._run_prompt, daemon=True).start()

    def _run_prompt(self) -> None:
        """Generate variations for the selected prompt type (worker thread)."""
        try:
            pt = self._prompt_type.get()
            count = self._prompt_count.get()
            if pt == "Heartfelt Personalized Message":
                variations = generate_heartfelt_message(
                    recipient=self._hf_recipient.get().strip() or "Friend",
                    occasion=self._hf_occasion.get(),
                    relationship=self._hf_relation.get().strip() or "Friend",
                    tone=self._hf_tone.get(),
                    word_count=self._hf_length.get(),
                    count=count,
                )
            elif pt == "Christian Encouragement Letter":
                variations = generate_christian_encouragement(
                    recipient=self._ch_recipient.get().strip() or "Friend",
                    challenge=self._ch_challenge.get().strip() or "a difficult season",
                    bible_theme=self._ch_theme.get(),
                    count=count,
                )
            else:
                variations = generate_graduation_message(
                    name=self._gr_name.get().strip() or "Graduate",
                    degree=self._gr_degree.get().strip() or "their degree",
                    career_goal=self._gr_goal.get().strip() or "their goals",
                    count=count,
                )
            display = f"\n{'='*55}\n".join(variations)
            self.after(0, self._set_text, self._prompt_output, display)
            self.after(0, self._prompt_status.configure,
                       {"text": f"✓ {len(variations)} variations generated."})
        except Exception as exc:
            self.after(0, messagebox.showerror, "Error", str(exc))
        finally:
            self.after(0, self._prompt_bar.stop)
            self.after(0, self._prompt_btn.configure, {"state": "normal"})

    # ── SECTION B: Customer Messages ────────────────────────────

    def _build_customer_messages(self, frame: tk.Frame) -> None:
        """Build the Customer Messages sub-tab widgets."""
        pad = {"padx": 14, "pady": 4}

        tk.Label(frame, text="Etsy Customer Messages",
                 font=("Helvetica", 14, "bold")).grid(
            row=0, column=0, columnspan=4, pady=(14, 2), padx=14, sticky="w")
        tk.Label(frame,
                 text="4 templates: Order Received · Proof Ready · Shipped · Review Request",
                 font=("Helvetica", 9), fg="#555").grid(
            row=1, column=0, columnspan=4, padx=14, sticky="w")
        ttk.Separator(frame, orient="horizontal").grid(
            row=2, column=0, columnspan=4, sticky="ew", padx=14, pady=8)

        # Message type
        tk.Label(frame, text="Message Type:", anchor="w").grid(
            row=3, column=0, sticky="w", **pad)
        self._msg_type = tk.StringVar(value=MESSAGE_TYPES[0])
        ttk.Combobox(frame, textvariable=self._msg_type, values=MESSAGE_TYPES,
                     state="readonly", width=30).grid(
            row=3, column=1, columnspan=3, sticky="w", padx=4, pady=3)

        # Customer details
        fields = [
            ("Customer Name:", "_cm_customer", "Jennifer"),
            ("Gift Recipient:", "_cm_recipient", "Emma (her daughter)"),
            ("Occasion:", "_cm_occasion", "Graduation"),
            ("Shop Name:", "_cm_shop", "ScenicSoulPrints"),
        ]
        for i, (label, attr, default) in enumerate(fields, start=4):
            tk.Label(frame, text=label, anchor="w").grid(row=i, column=0, sticky="w", **pad)
            var = tk.StringVar(value=default)
            setattr(self, attr, var)
            tk.Entry(frame, textvariable=var, width=36).grid(
                row=i, column=1, columnspan=3, sticky="w", padx=4, pady=3)

        row = 4 + len(fields)
        tk.Label(frame, text="Tone:", anchor="w").grid(row=row, column=0, sticky="w", **pad)
        self._cm_tone = tk.StringVar(value="Warm & Professional")
        ttk.Combobox(frame, textvariable=self._cm_tone, values=MESSAGE_TONES,
                     state="readonly", width=28).grid(
            row=row, column=1, columnspan=3, sticky="w", padx=4, pady=3)
        row += 1

        ttk.Separator(frame, orient="horizontal").grid(
            row=row, column=0, columnspan=4, sticky="ew", padx=14, pady=8)
        row += 1

        btn_frame = tk.Frame(frame)
        btn_frame.grid(row=row, column=0, columnspan=4, pady=4)
        ttk.Button(btn_frame, text="✦ AI Personalize Message",
                   command=self._on_personalize).pack(side="left", padx=6)
        ttk.Button(btn_frame, text="📋 Quick Copy Base Template",
                   command=self._on_base_copy).pack(side="left", padx=6)
        ttk.Button(btn_frame, text="📋 Copy All 4 Templates",
                   command=self._on_copy_all).pack(side="left", padx=6)
        row += 1

        self._cm_bar = ttk.Progressbar(frame, length=480, mode="indeterminate")
        self._cm_bar.grid(row=row, column=0, columnspan=4, padx=14, pady=3)
        row += 1
        self._cm_status = tk.Label(frame, text="Fill in details and click a button.",
                                    anchor="w", font=("Helvetica", 9))
        self._cm_status.grid(row=row, column=0, columnspan=4, sticky="w", padx=14)
        row += 1

        tk.Label(frame, text="Output:", font=("Helvetica", 10, "bold"), anchor="w").grid(
            row=row, column=0, columnspan=4, sticky="w", padx=14, pady=(8, 2))
        row += 1
        self._cm_output = tk.Text(frame, width=64, height=10, wrap="word",
                                   font=("Helvetica", 10), state="disabled",
                                   bg="#f9f9f9", relief="flat")
        self._cm_output.grid(row=row, column=0, columnspan=4, padx=14, pady=4, sticky="ew")
        row += 1
        ttk.Button(frame, text="Copy to Clipboard",
                   command=lambda: self._copy(self._cm_output)).grid(
            row=row, column=0, columnspan=4, pady=4)

    def _on_personalize(self) -> None:
        """Start AI message personalization on a background thread."""
        self._cm_bar.start(10)
        self._cm_status.configure(text="Personalizing message with AI...")
        threading.Thread(target=self._run_personalize, daemon=True).start()

    def _run_personalize(self) -> None:
        """Generate the AI-personalized customer message (worker thread)."""
        try:
            text = generate_personalized_customer_message(
                message_type=self._msg_type.get(),
                customer_name=self._cm_customer.get().strip() or "there",
                occasion=self._cm_occasion.get().strip() or "your order",
                recipient_name=self._cm_recipient.get().strip() or "your recipient",
                shop_name=self._cm_shop.get().strip() or "our shop",
                tone=self._cm_tone.get(),
            )
            self.after(0, self._set_text, self._cm_output, text)
            self.after(0, self._cm_status.configure, {"text": "✓ Personalized message ready. Copy and paste into Etsy."})
        except Exception as exc:
            self.after(0, messagebox.showerror, "Error", str(exc))
        finally:
            self.after(0, self._cm_bar.stop)

    def _on_base_copy(self) -> None:
        """Copy the selected base template to the clipboard and show it."""
        text = get_base_template(self._msg_type.get())
        self._set_text(self._cm_output, text)
        self.clipboard_clear()
        self.clipboard_append(text)
        self._cm_status.configure(text=f"✓ Base '{self._msg_type.get()}' template copied to clipboard.")

    def _on_copy_all(self) -> None:
        """Copy all four base customer message templates to the clipboard."""
        text = get_all_base_templates_formatted()
        self._set_text(self._cm_output, text)
        self.clipboard_clear()
        self.clipboard_append(text)
        self._cm_status.configure(text="✓ All 4 templates copied to clipboard.")

    # ── Shared helpers ───────────────────────────────────────────

    def _labeled_entry(self, parent: tk.Widget, row: int, label: str,
                        default: str = "") -> tk.StringVar:
        """Create a labeled entry row; return its StringVar."""
        tk.Label(parent, text=label, anchor="w").grid(row=row, column=0, sticky="w",
                                                        padx=4, pady=3)
        var = tk.StringVar(value=default)
        tk.Entry(parent, textvariable=var, width=36).grid(row=row, column=1,
                                                           sticky="w", padx=4, pady=3)
        return var

    def _labeled_combo(self, parent: tk.Widget, row: int, label: str,
                        values: list[str], default: str) -> tk.StringVar:
        """Create a labeled read-only combobox row; return its StringVar."""
        tk.Label(parent, text=label, anchor="w").grid(row=row, column=0, sticky="w",
                                                        padx=4, pady=3)
        var = tk.StringVar(value=default)
        ttk.Combobox(parent, textvariable=var, values=values,
                     state="readonly", width=34).grid(row=row, column=1,
                                                       sticky="w", padx=4, pady=3)
        return var

    def _labeled_spinbox(self, parent: tk.Widget, row: int, label: str,
                          min_val: int, max_val: int, default: int) -> tk.IntVar:
        """Create a labeled spinbox row; return its IntVar."""
        tk.Label(parent, text=label, anchor="w").grid(row=row, column=0, sticky="w",
                                                        padx=4, pady=3)
        var = tk.IntVar(value=default)
        ttk.Spinbox(parent, from_=min_val, to=max_val, textvariable=var,
                    width=7).grid(row=row, column=1, sticky="w", padx=4, pady=3)
        return var

    def _set_text(self, widget: tk.Text, text: str) -> None:
        """Replace the contents of a read-only text widget."""
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def _copy(self, widget: tk.Text) -> None:
        """Copy a text widget's contents to the clipboard."""
        text = widget.get("1.0", "end").strip()
        self.clipboard_clear()
        self.clipboard_append(text)
        messagebox.showinfo("Copied", "Output copied to clipboard!")
