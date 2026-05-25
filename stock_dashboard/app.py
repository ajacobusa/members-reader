import dash
from dash import Dash, html, dcc
import dash_bootstrap_components as dbc

app = Dash(
    __name__,
    use_pages=True,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    suppress_callback_exceptions=True,
)

app.layout = html.Div([
    html.Nav([
        html.A("📈 StockBoard", href="/", className="navbar-brand"),
        dcc.Link("Today's Picks", href="/", className="nav-link"),
        dcc.Link("History", href="/history", className="nav-link"),
        dcc.Link("Settings", href="/settings", className="nav-link"),
    ], className="navbar"),
    dash.page_container,
])

if __name__ == "__main__":
    app.run(debug=True, port=8050)
