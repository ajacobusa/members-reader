import datetime as dt
import json
import pytest
from stock_dashboard.engine import ratelimit
from stock_dashboard.engine.ratelimit import QuotaGuard, reset_at, detect, provider_for_url

UTC = dt.timezone.utc
NOON = dt.datetime(2026, 6, 10, 12, 0, tzinfo=UTC)  # a Wednesday


@pytest.fixture(autouse=True)
def _reset_singleton():
    ratelimit.reset_guard()
    yield
    ratelimit.reset_guard()


def _guard(tmp_path, now=NOON, config=None):
    return QuotaGuard(tmp_path / "quota.json", config or {}, now_fn=lambda: now)


# -- url -> provider --------------------------------------------------------
def test_provider_for_url():
    assert provider_for_url("https://financialmodelingprep.com/stable/x") == "fmp"
    assert provider_for_url("https://finnhub.io/api/v1/x") == "finnhub"
    assert provider_for_url("https://www.alphavantage.co/query") == "alpha_vantage"
    assert provider_for_url("https://newsapi.org/v2/x") == "newsapi"
    assert provider_for_url("https://stooq.com/q/d/l/") == "stooq"
    assert provider_for_url("http://example.com") is None


# -- reset math -------------------------------------------------------------
def test_reset_daily_is_next_utc_midnight():
    assert reset_at(NOON, "daily") == dt.datetime(2026, 6, 11, 0, 0, tzinfo=UTC)


def test_reset_hourly_and_minute():
    assert reset_at(NOON, "hourly") == NOON + dt.timedelta(hours=1)
    assert reset_at(NOON, "minute") == NOON + dt.timedelta(seconds=60)


def test_reset_weekly_is_next_monday():
    r = reset_at(NOON, "weekly")          # Wed -> next Mon
    assert r.weekday() == 0 and r == dt.datetime(2026, 6, 15, 0, 0, tzinfo=UTC)


def test_reset_retry_after_wins():
    assert reset_at(NOON, "daily", retry_after=120) == NOON + dt.timedelta(seconds=120)


# -- detection --------------------------------------------------------------
@pytest.mark.parametrize("status,payload,expected", [
    (429, None, True),
    (200, {"Note": "API call frequency is 25 requests per day"}, True),
    (200, {"Information": "rate limit reached"}, True),
    (200, {"Error Message": "Limit Reach . Please upgrade"}, True),
    (200, "Too many requests", True),
    (200, {"data": [1, 2, 3]}, False),
    (200, [1, 2, 3], False),
    (403, None, False),
])
def test_detect(status, payload, expected):
    assert detect(status, payload) is expected


# -- ledger behaviour -------------------------------------------------------
def test_mark_and_is_cooling(tmp_path):
    g = _guard(tmp_path)
    assert not g.is_cooling("fmp")
    until = g.mark("fmp")
    assert until == dt.datetime(2026, 6, 11, 0, 0, tzinfo=UTC)
    assert g.is_cooling("fmp")
    assert g.is_cooling(None) is False


def test_cooling_expires_with_time(tmp_path):
    later = {"t": NOON}
    g = QuotaGuard(tmp_path / "q.json", {}, now_fn=lambda: later["t"])
    g.mark("finnhub", kind="minute")
    assert g.is_cooling("finnhub")
    later["t"] = NOON + dt.timedelta(minutes=2)   # past the 60s window
    assert not g.is_cooling("finnhub")


def test_next_reset_is_soonest(tmp_path):
    g = _guard(tmp_path)
    g.mark("finnhub", kind="minute")   # +60s
    g.mark("fmp", kind="daily")        # next midnight
    assert g.next_reset() == NOON + dt.timedelta(seconds=60)


def test_state_persists_across_instances(tmp_path):
    p = tmp_path / "q.json"
    QuotaGuard(p, {}, now_fn=lambda: NOON).mark("stooq")
    g2 = QuotaGuard(p, {}, now_fn=lambda: NOON)
    assert g2.is_cooling("stooq")
    assert "stooq" in json.loads(p.read_text())


def test_clear_expired_prunes(tmp_path):
    clock = {"t": NOON}
    g = QuotaGuard(tmp_path / "q.json", {}, now_fn=lambda: clock["t"])
    g.mark("finnhub", kind="minute")
    clock["t"] = NOON + dt.timedelta(minutes=5)
    g.clear_expired()
    assert g.state == {}


def test_provider_specific_kind_from_config(tmp_path):
    g = _guard(tmp_path, config={"providers": {"fmp": "weekly"}})
    g.mark("fmp")                       # config overrides default 'daily'
    assert g.state["fmp"]["kind"] == "weekly"


def test_configure_singleton(tmp_path):
    assert ratelimit.get_guard() is None
    g = ratelimit.configure(tmp_path / "q.json", {"providers": {}})
    assert ratelimit.get_guard() is g


def test_corrupt_state_file_is_ignored(tmp_path):
    p = tmp_path / "q.json"
    p.write_text("{not valid json")
    g = QuotaGuard(p, {}, now_fn=lambda: NOON)
    assert g.state == {}
