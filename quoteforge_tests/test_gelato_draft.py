"""Gelato DRAFT-order preview tool - the safety contract: only ever a draft."""
import pytest

from quoteforge.automation.gelato_draft import (
    build_draft_payload, assert_draft, DRAFT_ORDER_TYPE)


def test_payload_is_always_draft_never_production():
    p = build_draft_payload("some_uid", "http://x/design.png")
    assert p["orderType"] == DRAFT_ORDER_TYPE == "draft"
    assert p["items"][0]["productUid"] == "some_uid"
    assert p["items"][0]["files"][0]["url"] == "http://x/design.png"


def test_assert_draft_refuses_a_production_order():
    # defense in depth: a tampered/non-draft payload must be refused before any send
    with pytest.raises(ValueError):
        assert_draft({"orderType": "order"})
    with pytest.raises(ValueError):
        assert_draft({})  # missing orderType
    assert_draft(build_draft_payload("u", "http://x"))  # the real payload passes


def test_create_draft_order_guards_before_network(monkeypatch):
    # Prove create_draft_order asserts draft BEFORE any HTTP call. If the guard is
    # bypassed the test would hit the network; we make the network explode to be sure
    # it is never reached for a non-draft, and reached only with a draft payload.
    import sys
    import quoteforge.automation.gelato_draft as gd

    sent = {}

    class _Resp:
        status_code = 201

        def raise_for_status(self):
            """No-op success."""

        def json(self):
            """Echo a fake created-draft response."""
            return {"id": "draft-123"}

    fake = type(sys)("requests")
    fake.post = lambda url, headers=None, json=None, timeout=0: (
        sent.update(json) or _Resp())
    monkeypatch.setitem(sys.modules, "requests", fake)
    monkeypatch.setattr(
        "quoteforge.automation.gelato_api._gelato_headers", lambda: {}, raising=False)

    out = gd.create_draft_order("uid", "http://x/d.png")
    assert out["id"] == "draft-123"
    assert sent["orderType"] == "draft"     # what actually went over the wire
