import yaml
from pathlib import Path
import dash
from dash import html, dcc, callback, Input, Output, State

dash.register_page(__name__, path="/settings")

ROOT = Path(__file__).parent.parent

def layout():
    cfg_path = ROOT / "config.yaml"
    cfg_data = yaml.safe_load(cfg_path.read_text())
    s = cfg_data["scoring"]

    return html.Div([
        html.Div([html.H2("Settings")], style={"padding": "16px 24px 8px"}),
        html.Div([
            html.H4("Scoring Weights", style={"marginBottom": "16px"}),
            html.Div([
                html.Label(f"Technical ({int(s['technical_weight']*100)}%)"),
                dcc.Slider(id="w-technical", min=0, max=100,
                           value=int(s["technical_weight"] * 100), step=5,
                           marks={i: f"{i}%" for i in range(0, 101, 25)}),
                html.Label(f"Fundamental ({int(s['fundamental_weight']*100)}%)",
                           style={"marginTop": "16px"}),
                dcc.Slider(id="w-fundamental", min=0, max=100,
                           value=int(s["fundamental_weight"] * 100), step=5,
                           marks={i: f"{i}%" for i in range(0, 101, 25)}),
                html.Label(f"Catalyst ({int(s['catalyst_weight']*100)}%)",
                           style={"marginTop": "16px"}),
                dcc.Slider(id="w-catalyst", min=0, max=100,
                           value=int(s["catalyst_weight"] * 100), step=5,
                           marks={i: f"{i}%" for i in range(0, 101, 25)}),
                html.Label(f"Pattern Match ({int(s['pattern_weight']*100)}%)",
                           style={"marginTop": "16px"}),
                dcc.Slider(id="w-pattern", min=0, max=100,
                           value=int(s["pattern_weight"] * 100), step=5,
                           marks={i: f"{i}%" for i in range(0, 101, 25)}),
            ]),
            html.Button("Save Weights", id="btn-save-weights",
                        style={"marginTop": "16px", "padding": "8px 18px",
                               "background": "#1565c0", "color": "white",
                               "border": "none", "borderRadius": "6px",
                               "cursor": "pointer"}),
            html.Div(id="settings-save-status", style={"marginTop": "8px", "color": "#2e7d32"}),

            html.Hr(),
            html.H4("API Keys (Tier B — optional)"),
            html.Label("Alpha Vantage Key:"),
            dcc.Input(id="key-av", type="password", placeholder="Leave blank to skip",
                      style={"width": "100%", "padding": "6px 10px", "marginBottom": "8px",
                             "border": "1px solid #ddd", "borderRadius": "4px"}),
            html.Label("Benzinga Key:"),
            dcc.Input(id="key-bz", type="password", placeholder="Leave blank to skip",
                      style={"width": "100%", "padding": "6px 10px", "marginBottom": "8px",
                             "border": "1px solid #ddd", "borderRadius": "4px"}),
            html.Label("NewsAPI Key:"),
            dcc.Input(id="key-na", type="password", placeholder="Leave blank to skip",
                      style={"width": "100%", "padding": "6px 10px", "marginBottom": "8px",
                             "border": "1px solid #ddd", "borderRadius": "4px"}),
            html.Button("Save Keys", id="btn-save-keys",
                        style={"padding": "8px 18px", "background": "#1565c0",
                               "color": "white", "border": "none",
                               "borderRadius": "6px", "cursor": "pointer"}),
            html.Div(id="keys-save-status", style={"marginTop": "8px", "color": "#2e7d32"}),
        ], style={"padding": "0 24px 24px", "maxWidth": "600px"}),
    ])

@callback(
    Output("settings-save-status", "children"),
    Input("btn-save-weights", "n_clicks"),
    State("w-technical", "value"),
    State("w-fundamental", "value"),
    State("w-catalyst", "value"),
    State("w-pattern", "value"),
    prevent_initial_call=True,
)
def save_weights(n_clicks, tech, fund, cat, pat):
    cfg_path = ROOT / "config.yaml"
    data = yaml.safe_load(cfg_path.read_text())
    total = (tech or 0) + (fund or 0) + (cat or 0) + (pat or 0)
    if total == 0:
        return "⚠ Weights must sum to > 0"
    data["scoring"]["technical_weight"] = round((tech or 0) / 100, 2)
    data["scoring"]["fundamental_weight"] = round((fund or 0) / 100, 2)
    data["scoring"]["catalyst_weight"] = round((cat or 0) / 100, 2)
    data["scoring"]["pattern_weight"] = round((pat or 0) / 100, 2)
    cfg_path.write_text(yaml.dump(data, default_flow_style=False))
    return "✓ Weights saved"

@callback(
    Output("keys-save-status", "children"),
    Input("btn-save-keys", "n_clicks"),
    State("key-av", "value"),
    State("key-bz", "value"),
    State("key-na", "value"),
    prevent_initial_call=True,
)
def save_keys(n_clicks, av, bz, na):
    cfg_path = ROOT / "config.yaml"
    data = yaml.safe_load(cfg_path.read_text())
    if av:
        data["api_keys"]["alpha_vantage"] = av
    if bz:
        data["api_keys"]["benzinga"] = bz
    if na:
        data["api_keys"]["newsapi"] = na
    cfg_path.write_text(yaml.dump(data, default_flow_style=False))
    return "✓ API keys saved"
