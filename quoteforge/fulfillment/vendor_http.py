"""Shared HTTP plumbing for the stdlib (urllib) vendor adapters.

Printify and Printful speak near-identical Bearer-token JSON APIs; this module
holds the one copy of the GET/parse, auth-probe, and shipment-scan logic so a
fix lands in both adapters at once (the per-vendor files keep only their URLs,
field names, and status maps).
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request


def get_json(url: str, api_key: str, timeout: int = 15) -> dict:
    """GET ``url`` with a Bearer token and parse the JSON body.
    urlopen raises on any non-2xx, so a return always means success."""
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {api_key}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def verify_auth(url: str, api_key: str, ok_detail: str) -> dict:
    """Probe ``url`` with the key and classify the result as {ok, detail}.
    401/403 produce the actionable 'auth rejected ... check key' wording the
    admin verify-keys report relies on (Gelato parity)."""
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {api_key}"})
    try:
        # urlopen raises HTTPError on any non-2xx, so reaching here means OK.
        with urllib.request.urlopen(req, timeout=15):
            return {"ok": True, "detail": ok_detail}
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return {"ok": False,
                    "detail": f"auth rejected (HTTP {exc.code}) - check key"}
        return {"ok": False, "detail": f"unexpected HTTP {exc.code}"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}


def first_tracked_shipment(shipments: list, number_key: str) -> dict:
    """The first shipment carrying a tracking number (falling back to shipment
    zero) - partially-fulfilled orders may track on a later shipment."""
    shipments = shipments or []
    return next((s for s in shipments if s.get(number_key)),
                shipments[0] if shipments else {})
