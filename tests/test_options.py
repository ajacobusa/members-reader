import pandas as pd
from stock_dashboard.engine.options import (
    compute_max_pain, put_call_ratio, build_options_signal, OptionsSignal,
)


def _calls():
    return pd.DataFrame({"strike": [90, 100, 110],
                         "openInterest": [100, 500, 50],
                         "volume": [10, 800, 5],
                         "impliedVolatility": [0.4, 0.45, 0.5]})


def _puts():
    return pd.DataFrame({"strike": [90, 100, 110],
                         "openInterest": [60, 300, 40],
                         "volume": [400, 100, 20],
                         "impliedVolatility": [0.5, 0.45, 0.4]})


def test_put_call_ratio():
    assert put_call_ratio(_calls(), _puts()) == round(520 / 815, 3)


def test_compute_max_pain_returns_a_listed_strike():
    mp = compute_max_pain(_calls(), _puts())
    assert mp in [90, 100, 110]


def test_build_options_signal_unavailable_when_no_chain():
    sig = build_options_signal("AAPL", chain_fn=lambda t: None)
    assert isinstance(sig, OptionsSignal)
    assert sig.available is False


def test_build_options_signal_populated():
    sig = build_options_signal("AAPL", chain_fn=lambda t: (_calls(), _puts()))
    assert sig.available is True
    assert sig.put_call_ratio is not None
    assert sig.max_pain in [90, 100, 110]
    assert sig.unusual_call_volume in (True, False)
