import json
import datetime
from pathlib import Path
import dash
from dash import html, dcc, callback, Input, Output, dash_table
from stock_dashboard.engine.config_loader import load_config
from stock_dashboard.db.database import Database

dash.register_page(__name__, path="/history")

ROOT = Path(__file__).parent.parent
cfg = load_config(ROOT / "config.yaml")
db = Database(str(ROOT / cfg.output["db_path"]))
db.init_schema()

def layout():
    return html.Div([
        html.Div([
            html.H2("Past Picks History"),
            html.Div([
                dcc.Input(id="hist-ticker", placeholder="Filter by ticker",
                          style={"marginRight": "8px", "padding": "6px 10px",
                                 "border": "1px solid #ddd", "borderRadius": "4px"}),
                dcc.Checklist(id="hist-marked-only",
                              options=[{"label": " Marked picks only", "value": "marked"}],
                              value=[], inline=True, style={"marginRight": "8px"}),
                html.Button("Filter", id="hist-filter-btn",
                            style={"padding": "6px 14px", "background": "#1565c0",
                                   "color": "white", "border": "none",
                                   "borderRadius": "4px", "cursor": "pointer"}),
            ], style={"display": "flex", "alignItems": "center", "marginTop": "8px"}),
        ], style={"padding": "16px 24px 8px"}),
        html.Div(id="history-table-container", style={"padding": "0 24px 24px"}),
    ])

@callback(
    Output("history-table-container", "children"),
    Input("hist-filter-btn", "n_clicks"),
    Input("hist-ticker", "value"),
    Input("hist-marked-only", "value"),
)
def render_history(n_clicks, ticker_filter, marked_only):
    picks = db.get_picks(
        ticker=ticker_filter or None,
        marked_only="marked" in (marked_only or []),
    )
    if not picks:
        return html.P("No picks found.", style={"color": "#888"})

    rows = []
    for p in picks:
        cats = json.loads(p["catalysts"]) if isinstance(p.get("catalysts"), str) else (p.get("catalysts") or [])
        primary_cat = cats[0].get("label", "") if cats else ""
        rows.append({
            "Date": p["date"], "Ticker": p["ticker"], "Company": p["company"],
            "Price": f"${p['price']:.2f}", "Score": int(p["composite_score"]),
            "Primary Catalyst": primary_cat,
            "Marked": "✓" if p["marked_as_picked"] else "",
            "Used in Learning": "Yes" if p["marked_as_picked"] else "No",
        })

    return dash_table.DataTable(
        data=rows,
        columns=[{"name": c, "id": c} for c in rows[0].keys()],
        sort_action="native",
        filter_action="native",
        page_size=25,
        style_table={"overflowX": "auto"},
        style_cell={"padding": "8px 12px", "fontSize": "13px"},
        style_header={"background": "#f8f9fa", "fontWeight": "600"},
        style_data_conditional=[
            {"if": {"filter_query": '{Marked} = "✓"'},
             "background": "#e8f5e9"},
        ],
    )
