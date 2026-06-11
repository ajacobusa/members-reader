"""Rate-limit / quota accommodation.

Free-tier data providers (yfinance, Stooq, FMP, Finnhub, NewsAPI, Alpha Vantage)
each cap requests per minute / day / month. When a cap is hit we want to:

  1. *Detect* it (HTTP 429, or a 200 body that is really a "limit reached" notice).
  2. *Remember* it — mark that provider "cooling" until its quota resets, persisted
     to disk so it survives process exit.
  3. *Skip* further calls to a cooling provider (preserve the rest of the quota,
     fail soft instead of hammering the limit).
  4. Expose `next_reset()` so the runner can schedule an automatic resume exactly
     when the resource becomes available again.

A single process-wide guard is configured once per run via `configure(...)`; if it
is never configured (e.g. in unit tests) all hooks are no-ops.
"""
import json
import logging
import datetime as dt
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)
UTC = dt.timezone.utc

# Default cooldown window per provider, matching how each one's free tier resets.
_DEFAULT_KINDS = {
    "yfinance": "hourly",      # unofficial, rolling — short cooldown
    "stooq": "daily",          # ~50 CSV downloads/day per IP
    "fmp": "daily",            # daily request cap
    "finnhub": "minute",       # 60 calls/minute
    "newsapi": "daily",        # 100 requests/day
    "alpha_vantage": "daily",  # 25 requests/day
}

# Map a request URL's host to the provider name, so detection can be centralized
# in base.http_get_json without each provider passing its own name.
_HOST_PROVIDER = {
    "financialmodelingprep.com": "fmp",
    "finnhub.io": "finnhub",
    "alphavantage.co": "alpha_vantage",
    "newsapi.org": "newsapi",
    "stooq.com": "stooq",
    "stooq.pl": "stooq",
}


def provider_for_url(url: str) -> Optional[str]:
    if not url:
        return None
    for host, name in _HOST_PROVIDER.items():
        if host in url:
            return name
    return None


def _next_utc_midnight(now: dt.datetime) -> dt.datetime:
    tomorrow = (now + dt.timedelta(days=1)).date()
    return dt.datetime(tomorrow.year, tomorrow.month, tomorrow.day, tzinfo=UTC)


def _next_monday(now: dt.datetime) -> dt.datetime:
    # weekday(): Mon=0 .. Sun=6. Days until the *next* Monday (strictly future).
    days_ahead = (0 - now.weekday()) % 7
    days_ahead = days_ahead or 7
    target = (now + dt.timedelta(days=days_ahead)).date()
    return dt.datetime(target.year, target.month, target.day, tzinfo=UTC)


def reset_at(now: dt.datetime, kind: str, retry_after: Optional[float] = None) -> dt.datetime:
    """Compute when a cooldown of `kind` (or an explicit Retry-After) expires."""
    if retry_after:
        return now + dt.timedelta(seconds=float(retry_after))
    if kind == "minute":
        return now + dt.timedelta(seconds=60)
    if kind == "hourly":
        return now + dt.timedelta(hours=1)
    if kind == "weekly":
        return _next_monday(now)
    # default: daily
    return _next_utc_midnight(now)


def detect(status_code: int, payload=None) -> bool:
    """True if a response signals quota exhaustion / rate limiting."""
    if status_code in (429,):
        return True
    if status_code in (402, 403) and payload is None:
        return False  # plain auth/paywall, not a transient quota — let caller decide
    text = ""
    if isinstance(payload, dict):
        # Alpha Vantage throttles by returning a bare "Note"/"Information" key
        # in place of data — treat the key's presence as the signal.
        if "Note" in payload or "Information" in payload:
            return True
        for k in ("Note", "Information", "Error Message", "error", "message", "detail"):
            v = payload.get(k)
            if isinstance(v, str):
                text += " " + v.lower()
    elif isinstance(payload, str):
        text = payload.lower()
    return any(s in text for s in (
        "limit reach", "rate limit", "too many request", "quota",
        "api call frequency", "exceeded", "throttl",
    ))


class QuotaGuard:
    def __init__(self, state_path, config: Optional[dict] = None, now_fn=None):
        self.state_path = Path(state_path)
        self.config = config or {}
        self._now_fn = now_fn
        self._kinds = {**_DEFAULT_KINDS, **(self.config.get("providers") or {})}
        self.state: dict = self._load()

    # -- time --------------------------------------------------------------
    def _now(self) -> dt.datetime:
        return self._now_fn() if self._now_fn else dt.datetime.now(UTC)

    # -- persistence -------------------------------------------------------
    def _load(self) -> dict:
        try:
            if self.state_path.exists():
                return json.loads(self.state_path.read_text())
        except Exception as exc:  # noqa: BLE001
            log.warning("quota state load failed: %s", exc)
        return {}

    def _save(self) -> None:
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            self.state_path.write_text(json.dumps(self.state, indent=2))
        except Exception as exc:  # noqa: BLE001
            log.warning("quota state save failed: %s", exc)

    # -- queries -----------------------------------------------------------
    def is_cooling(self, provider: Optional[str]) -> bool:
        if not provider:
            return False
        entry = self.state.get(provider)
        if not entry:
            return False
        try:
            until = dt.datetime.fromisoformat(entry["reset_at"])
        except Exception:  # noqa: BLE001
            return False
        return self._now() < until

    def cooling(self) -> dict:
        """{provider: reset_at_iso} for providers still cooling."""
        out = {}
        for prov, entry in self.state.items():
            if self.is_cooling(prov):
                out[prov] = entry["reset_at"]
        return out

    def next_reset(self) -> Optional[dt.datetime]:
        """Soonest reset time among providers still cooling (None if none)."""
        times = []
        for prov in self.state:
            if self.is_cooling(prov):
                try:
                    times.append(dt.datetime.fromisoformat(self.state[prov]["reset_at"]))
                except Exception:  # noqa: BLE001
                    pass
        return min(times) if times else None

    # -- mutations ---------------------------------------------------------
    def mark(self, provider: str, kind: Optional[str] = None,
             retry_after: Optional[float] = None, reason: str = "") -> dt.datetime:
        now = self._now()
        k = kind or self._kinds.get(provider, "daily")
        until = reset_at(now, k, retry_after)
        self.state[provider] = {
            "reset_at": until.isoformat(),
            "kind": k,
            "reason": reason,
            "hit_at": now.isoformat(),
        }
        self._save()
        log.warning("quota: %s cooling until %s (%s%s)", provider, until.isoformat(),
                    k, f", {reason}" if reason else "")
        return until

    def clear(self, provider: str) -> None:
        if provider in self.state:
            self.state.pop(provider, None)
            self._save()

    def clear_expired(self) -> None:
        changed = False
        for prov in list(self.state):
            if not self.is_cooling(prov):
                self.state.pop(prov, None)
                changed = True
        if changed:
            self._save()


# -- process-wide singleton -----------------------------------------------
_GUARD: Optional[QuotaGuard] = None


def configure(state_path, config: Optional[dict] = None, now_fn=None) -> QuotaGuard:
    global _GUARD
    _GUARD = QuotaGuard(state_path, config, now_fn)
    return _GUARD


def get_guard() -> Optional[QuotaGuard]:
    return _GUARD


def reset_guard() -> None:
    """Test hook: drop the configured guard so hooks become no-ops again."""
    global _GUARD
    _GUARD = None
