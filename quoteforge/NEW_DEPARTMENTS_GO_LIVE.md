# Go-Live Runbook — Mugs, Calendars, Branded Products

These three departments are built, tested, and safe in `TEST_MODE`. To take them
**live** you (the owner) must do a few steps that require your authenticated Gelato
account — Claude cannot fetch or invent Gelato product UIDs.

The safety gates below mean nothing ships wrong until these steps are done: the
preflight gate hard-fails live mode while any department is unmapped, and the
router sends any placeholder (`GEL-*`) UID to manual review.

## 1. Map real Gelato product UIDs

```bash
python -m quoteforge.admin map-gelato          # prints a JSON template (44 families)
```

For each family (`mug:classic_mug`, `calendar:wall_cal`, `branded:tote`, …) open the
product in your Gelato dashboard, copy its **product UID**, and paste it in place of
`REPLACE_WITH_GELATO_PRODUCT_UID`. Save the JSON to the path in
`GELATO_PRODUCT_FAMILY_FILE` (see `.env`). Then:

```bash
python -m quoteforge.admin go-live-readiness    # must show RESULT: READY
```

## 2. Sync real costs and re-check margins

The cost sync now covers all departments (mugs/calendars/branded included), so real
Gelato costs flow into pricing and the order-time margin floor.

```bash
python -m quoteforge.admin gelato-sync          # pulls real costs/availability
python -m quoteforge.admin margins              # confirm every variant >= 60% floor
```

If any variant drops below the floor on real costs, raise its list price (the
catalog auto-prices to the floor, but verify after the first real sync).

## 3. Calendars: manual fulfilment for now (deliberate)

A 12-month calendar carries up to 12 month photos. The current Gelato submission
sends a **single** print file, so the router **holds every calendar order for
manual production** (`status: "manual"`) — it will never silently ship a cover-only
calendar. The 12 photo URLs and the cover are saved with the order; retrieve them
for manual fulfilment with:

```python
from quoteforge.db.database import get_design_for_order
design = get_design_for_order(order_id)      # design_json.cal.urls = the 12 months
```

To make calendars fully automated later, build a Gelato multi-page payload in
`create_gelato_order` that maps each month URL to its calendar page, then remove the
calendar hold in `fulfillment/router.py`. Until then, calendars are sellable and
safe — just fulfilled by hand.

## 4. Verify dynamic variant search (optional)

Mapped families resolve directly by UID, so this is only relevant if you rely on
dynamic Gelato variant search. `_gelato_search_variant` uses apparel attribute names
(`GarmentColor`/`GarmentSize`); for mugs/calendars those filters may not match, so an
unmapped variant falls to manual review (safe, never wrong-product). Mapping the
family UIDs in step 1 avoids this path entirely.

## 5. Final gate

```bash
python -m quoteforge.admin preflight            # must PASS before flipping live
# then set TEST_MODE=false in the production env
```

`preflight` hard-fails if any department is still on placeholder UIDs, so you cannot
flip live half-mapped.
