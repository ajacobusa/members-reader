"""Streamlit web-based pipeline monitor.

A deployable web dashboard (alternative to the Tkinter Pipeline Monitor tab).
Run locally:  streamlit run quoteforge/web_monitor.py
Deploy:       see docs/DEPLOYMENT_GUIDE.md (Render / Streamlit Cloud)

Unlike the Tkinter GUI, this runs in a browser and can be hosted publicly
so your VAs can monitor orders from anywhere.
"""
from pathlib import Path

try:
    import streamlit as st
    import pandas as pd
except ImportError:  # pragma: no cover - only needed when running the dashboard
    st = None
    pd = None

from quoteforge.config import OUTPUT_DIR, TEST_MODE
from quoteforge.db.database import (
    DB_PATH, init_db, get_all_orders, get_order_stats, get_pipeline_log,
)

STAGE_ORDER = [
    "received", "quote_generated", "artwork_done", "artwork_stored",
    "proof_sent", "in_production", "shipped",
]


def render() -> None:
    """Render the Streamlit dashboard. Requires streamlit + pandas installed."""
    if st is None:
        print("Streamlit not installed. Run: pip install streamlit pandas")
        return

    st.set_page_config(page_title="QuoteForge Pipeline Monitor", layout="wide")
    st.title("QuoteForge — 7-Stage Pipeline Monitor")

    mode_label = "🧪 TEST MODE" if TEST_MODE else "🟢 LIVE MODE"
    st.caption(f"{mode_label}  ·  Customer → Etsy → Quote → Artwork → Drive → Gelato → Follow-up")

    init_db()
    orders = get_all_orders(limit=200)
    stats = get_order_stats()

    # ── Top-line metrics ─────────────────────────────────────────
    by_status = stats.get("by_status", {})
    in_progress = sum(v for k, v in by_status.items()
                      if k not in ("shipped", "delivered", "error"))
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Orders", stats.get("total", 0))
    c2.metric("In Progress", in_progress)
    c3.metric("Shipped", by_status.get("shipped", 0))
    c4.metric("Errors", by_status.get("error", 0))

    if not orders:
        st.info("No orders yet. Orders appear here once they flow through the pipeline.")
        return

    df = pd.DataFrame(orders)

    # ── Status funnel chart ──────────────────────────────────────
    st.subheader("Pipeline Funnel")
    funnel = {stage: by_status.get(stage, 0) for stage in STAGE_ORDER}
    st.bar_chart(pd.Series(funnel))

    # ── Orders table ─────────────────────────────────────────────
    st.subheader("Recent Orders")
    display_cols = [c for c in
                    ["order_id", "recipient_name", "occasion", "relationship",
                     "status", "tracking_number", "created_at"]
                    if c in df.columns]
    st.dataframe(df[display_cols], use_container_width=True, height=400)

    # ── Per-order pipeline log ───────────────────────────────────
    st.subheader("Inspect an Order")
    order_ids = df["order_id"].tolist()
    selected = st.selectbox("Select order", order_ids)
    if selected:
        logs = get_pipeline_log(selected)
        if logs:
            st.dataframe(pd.DataFrame(logs)[["stage", "status", "message", "created_at"]],
                         use_container_width=True)
        else:
            st.write("No pipeline log entries for this order yet.")


if __name__ == "__main__" and st is not None:
    render()
