"""The post-delivery delight/review touch waits longer for ASSUMED deliveries
(Printify/Printful timer) than for carrier-CONFIRMED ones - so we never ask a
customer for a review before their parcel realistically arrived."""
from datetime import datetime, timedelta

from quoteforge.etsy.delight_loop import (delight_due, DELIGHT_LEAD_DAYS,
                                          ASSUMED_DELIGHT_BUFFER_DAYS)


def _order(oid, confirmed, days_ago):
    ref = (datetime.now() - timedelta(days=days_ago)).isoformat()
    return {"order_id": oid, "status": "delivered",
            "delivery_confirmed": 1 if confirmed else 0,
            "customer_email": f"{oid}@x.com", "customer_name": "C",
            "recipient_name": "R", "updated_at": ref, "created_at": ref}


def test_confirmed_delivery_delights_at_normal_lead():
    o = _order("CONF", confirmed=True, days_ago=DELIGHT_LEAD_DAYS + 1)
    assert any(d["order_id"] == "CONF" for d in delight_due([o]))


def test_assumed_delivery_waits_the_extra_buffer():
    # Past the normal lead but inside the assumed buffer -> NOT due yet.
    o = _order("ASSUM", confirmed=False, days_ago=DELIGHT_LEAD_DAYS + 1)
    assert not any(d["order_id"] == "ASSUM" for d in delight_due([o]))
    # Past lead + buffer -> now due.
    o2 = _order("ASSUM2", confirmed=False,
                days_ago=DELIGHT_LEAD_DAYS + ASSUMED_DELIGHT_BUFFER_DAYS + 1)
    assert any(d["order_id"] == "ASSUM2" for d in delight_due([o2]))
