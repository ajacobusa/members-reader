import json
import datetime
from pathlib import Path
import dash
from dash import html, dcc, callback, Input, Output, State
from stock_dashboard.engine.config_loader import load_config
from stock_dashboard.db.database import Database

dash.register_page(__name__, path="/")

ROOT = Path(__file__).parent.parent
cfg = load_config(ROOT / "config.yaml")
db = Database(str(ROOT / cfg.output["db_path"]))
db.init_schema()

def layout():
    return html.Div([
        html.Div(id="market-banner"),
        html.Div([
            html.Div([
                html.H2("Today's Top 10 Picks", style={"margin": 0}),
                html.Div(id="last-run-label",
                         style={"color": "#888", "fontSize": "12px"}),
            ]),
            html.Div([
                html.Button("⚙ Adjust Weights", id="btn-weights",
                            style={"marginRight": "10px", "padding": "8px 16px",
                                   "border": "1px solid #1565c0", "color": "#1565c0",
                                   "background": "white", "borderRadius": "6px",
                                   "cursor": "pointer"}),
                html.Button("▶ Run Today's Picks", id="btn-run",
                            style={"padding": "8px 18px", "background": "#1565c0",
                                   "color": "white", "border": "none",
                                   "borderRadius": "6px", "cursor": "pointer"}),
            ]),
        ], style={"display": "flex", "justifyContent": "space-between",
                  "alignItems": "flex-start", "padding": "16px 24px 8px"}),

        dcc.Loading(html.Div(id="picks-container", style={"padding": "0 24px"})),
        html.Div(id="expanded-card", style={"padding": "0 24px 24px"}),
        dcc.Store(id="picks-store"),
        dcc.Store(id="selected-ticker"),
    ], style={"minHeight": "100vh"})

@callback(
    Output("picks-store", "data"),
    Output("market-banner", "children"),
    Output("last-run-label", "children"),
    Input("btn-run", "n_clicks"),
    prevent_initial_call=True,
)
def run_picks(n_clicks):
    from stock_dashboard.engine.universe import get_universe
    from stock_dashboard.engine.pipeline import run_pipeline
    from stock_dashboard.run_daily import _fetch_market_data, _fetch_earnings_data

    tickers = get_universe(cfg)
    market_data = _fetch_market_data()
    earnings_data = _fetch_earnings_data(tickers)
    marked_count = len(db.get_picks(marked_only=True))

    records, market_ok = run_pipeline(
        tickers=tickers, cfg=cfg, market_data=market_data,
        earnings_data=earnings_data, sector_pe_map={},
        marked_picks_count=marked_count,
    )
    if records:
        db.save_picks(records)

    banner_class = "market-banner market-ok" if market_ok else "market-banner market-bad"
    banner_text = "✓ Market conditions favorable" if market_ok else "✗ Market conditions unfavorable — picks paused"
    banner = html.Div(banner_text, className=banner_class,
                      style={"margin": "8px 24px"})

    now = datetime.datetime.now().strftime("Last run: %H:%M")
    return [r.__dict__ for r in records], banner, now

@callback(
    Output("picks-container", "children"),
    Input("picks-store", "data"),
)
def render_picks_table(data):
    if not data:
        picks = db.get_picks(date=datetime.date.today().isoformat())
        data = picks

    if not data:
        return html.P("No picks yet. Click 'Run Today's Picks' to generate.",
                      style={"color": "#888", "padding": "24px"})

    rows = []
    for i, p in enumerate(data):
        cats = json.loads(p["catalysts"]) if isinstance(p.get("catalysts"), str) else (p.get("catalysts") or [])
        cat_tags = html.Div([
            html.Span(c.get("label", c.get("type", "")),
                      className="catalyst-tag",
                      style={"background": "#1565c0", "color": "white"})
            for c in cats[:2]
        ])
        price_val = p.get("price")
        price_str = f"${float(price_val):.2f}" if price_val not in (None, "") else "—"
        er = p.get("expected_return_pct")
        pg = p.get("prob_gain")
        sz = p.get("suggested_size_pct")
        er_str = "—" if er is None else f"{float(er):+.1f}%"
        pg_str = "—" if pg is None else f"{float(pg)*100:.0f}%"
        sz_str = "—" if sz is None else f"{float(sz):.1f}%"
        rows.append(html.Tr([
            html.Td(i + 1, style={"color": "#888", "padding": "10px 8px"}),
            html.Td(html.Strong(p.get("ticker", ""), style={"color": "#1565c0", "fontSize": "15px"}),
                    style={"padding": "10px 8px"}),
            html.Td(p.get("company", ""), style={"padding": "10px 8px"}),
            html.Td(price_str, style={"padding": "10px 8px"}),
            html.Td(html.Span(int(p.get("composite_score", 0)), className="score-badge"),
                    style={"padding": "10px 8px", "textAlign": "center"}),
            html.Td(html.Span(int(p.get("technical_score", 0))), style={"padding": "10px 8px", "color": "#1565c0"}),
            html.Td(html.Span(int(p.get("fundamental_score", 0))), style={"padding": "10px 8px", "color": "#2e7d32"}),
            html.Td(er_str, style={"padding": "10px 8px", "textAlign": "right", "fontWeight": "700"}),
            html.Td(pg_str, style={"padding": "10px 8px", "textAlign": "right"}),
            html.Td(sz_str, style={"padding": "10px 8px", "textAlign": "right", "color": "#1565c0"}),
            html.Td(cat_tags, style={"padding": "10px 8px"}),
            html.Td(
                html.Button("Expand ▾", id={"type": "expand-btn", "index": p.get("ticker")},
                            n_clicks=0,
                            style={"border": "none", "background": "none",
                                   "color": "#1565c0", "cursor": "pointer"}),
                style={"padding": "10px 8px"},
            ),
        ], style={"borderBottom": "1px solid #f0f0f0",
                  "background": "white" if i % 2 == 0 else "#fafafa"}))

    return html.Table([
        html.Thead(html.Tr([
            html.Th(h, style={"padding": "8px", "background": "#f8f9fa",
                              "color": "#555", "fontWeight": "600",
                              "borderBottom": "2px solid #e5e7eb"})
            for h in ["#", "Ticker", "Company", "Price", "Score", "Tech", "Fund", "Exp.Ret", "P(Gain)", "Size", "Catalysts", ""]
        ])),
        html.Tbody(rows),
    ], style={"width": "100%", "borderCollapse": "collapse",
              "fontSize": "13px", "background": "white",
              "borderRadius": "8px", "overflow": "hidden",
              "boxShadow": "0 1px 3px rgba(0,0,0,0.1)"})
