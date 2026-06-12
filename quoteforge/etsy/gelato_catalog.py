"""Gelato product catalog with pricing and profit calculations."""
from dataclasses import dataclass, field


@dataclass
class GelatoProduct:
    """One sellable Gelato product: size, cost, tiered pricing, and fit notes."""
    product_id: str
    name: str
    category: str          # "poster", "canvas", "framed", "acrylic", "metal", "mug"
    size: str              # e.g. "18x24 in"
    width_px: int          # at 300 DPI
    height_px: int
    gelato_cost_usd: float # what Gelato charges you per unit
    suggested_price: dict[str, float]  # {"budget": 18.99, "mid": 29.99, "premium": 45.99}
    profit_margin: dict[str, float]    # calculated profit per tier
    etsy_fee_pct: float    # 6.5% transaction + listing
    print_quality: str     # "standard", "premium", "ultra"
    material: str
    ships_days: int        # estimated ship days (US)
    gelato_sku: str
    best_for: list[str]    # ["graduation", "memorial", "office", ...]


def _calc_profit(gelato_cost: float, prices: dict[str, float]) -> dict[str, float]:
    """Compute profit for each price tier: price - gelato_cost - (price * 0.065) - 0.20"""
    return {
        tier: round(price - gelato_cost - (price * 0.065) - 0.20, 2)
        for tier, price in prices.items()
    }


# ---------------------------------------------------------------------------
# POSTERS
# ---------------------------------------------------------------------------

_p8x10_prices = {"budget": 12.99, "mid": 18.99, "premium": 24.99}
_poster_8x10 = GelatoProduct(
    product_id="poster_8x10",
    name="Poster 8x10 in",
    category="poster",
    size="8x10 in",
    width_px=2400,
    height_px=3000,
    gelato_cost_usd=4.50,
    suggested_price=_p8x10_prices,
    profit_margin=_calc_profit(4.50, _p8x10_prices),
    etsy_fee_pct=0.065,
    print_quality="standard",
    material="170gsm matte paper",
    ships_days=5,
    gelato_sku="GEL-POSTER-8X10-STD",
    best_for=["dorm", "kids_room", "gift", "inspirational"],
)

_p11x14_prices = {"budget": 16.99, "mid": 22.99, "premium": 32.99}
_poster_11x14 = GelatoProduct(
    product_id="poster_11x14",
    name="Poster 11x14 in",
    category="poster",
    size="11x14 in",
    width_px=3300,
    height_px=4200,
    gelato_cost_usd=6.00,
    suggested_price=_p11x14_prices,
    profit_margin=_calc_profit(6.00, _p11x14_prices),
    etsy_fee_pct=0.065,
    print_quality="standard",
    material="170gsm matte paper",
    ships_days=5,
    gelato_sku="GEL-POSTER-11X14-STD",
    best_for=["office", "nursery", "motivational", "graduation"],
)

_p12x16_prices = {"budget": 18.99, "mid": 26.99, "premium": 36.99}
_poster_12x16 = GelatoProduct(
    product_id="poster_12x16",
    name="Poster 12x16 in",
    category="poster",
    size="12x16 in",
    width_px=3600,
    height_px=4800,
    gelato_cost_usd=7.50,
    suggested_price=_p12x16_prices,
    profit_margin=_calc_profit(7.50, _p12x16_prices),
    etsy_fee_pct=0.065,
    print_quality="standard",
    material="170gsm matte paper",
    ships_days=5,
    gelato_sku="GEL-POSTER-12X16-STD",
    best_for=["bedroom", "living_room", "motivational", "anniversary"],
)

_p18x24_prices = {"budget": 22.99, "mid": 29.99, "premium": 42.99}
_poster_18x24 = GelatoProduct(
    product_id="poster_18x24",
    name="Poster 18x24 in",
    category="poster",
    size="18x24 in",
    width_px=5400,
    height_px=7200,
    gelato_cost_usd=11.00,
    suggested_price=_p18x24_prices,
    profit_margin=_calc_profit(11.00, _p18x24_prices),
    etsy_fee_pct=0.065,
    print_quality="standard",
    material="170gsm matte paper",
    ships_days=5,
    gelato_sku="GEL-POSTER-18X24-STD",
    best_for=["office", "gym", "living_room", "memorial", "graduation"],
)

_p24x36_prices = {"budget": 28.99, "mid": 38.99, "premium": 54.99}
_poster_24x36 = GelatoProduct(
    product_id="poster_24x36",
    name="Poster 24x36 in",
    category="poster",
    size="24x36 in",
    width_px=7200,
    height_px=10800,
    gelato_cost_usd=16.00,
    suggested_price=_p24x36_prices,
    profit_margin=_calc_profit(16.00, _p24x36_prices),
    etsy_fee_pct=0.065,
    print_quality="standard",
    material="170gsm matte paper",
    ships_days=5,
    gelato_sku="GEL-POSTER-24X36-STD",
    best_for=["large_wall", "office", "gym", "event_decor"],
)

# ---------------------------------------------------------------------------
# CANVAS
# ---------------------------------------------------------------------------

_c8x10_prices = {"budget": 34.99, "mid": 44.99, "premium": 59.99}
_canvas_8x10 = GelatoProduct(
    product_id="canvas_8x10",
    name="Canvas 8x10 in",
    category="canvas",
    size="8x10 in",
    width_px=2400,
    height_px=3000,
    gelato_cost_usd=18.00,
    suggested_price=_c8x10_prices,
    profit_margin=_calc_profit(18.00, _c8x10_prices),
    etsy_fee_pct=0.065,
    print_quality="premium",
    material="300gsm canvas, 1.5in pine stretcher bars",
    ships_days=7,
    gelato_sku="GEL-CANVAS-8X10-PRM",
    best_for=["gift", "memorial", "anniversary", "nursery"],
)

_c11x14_prices = {"budget": 44.99, "mid": 59.99, "premium": 79.99}
_canvas_11x14 = GelatoProduct(
    product_id="canvas_11x14",
    name="Canvas 11x14 in",
    category="canvas",
    size="11x14 in",
    width_px=3300,
    height_px=4200,
    gelato_cost_usd=24.00,
    suggested_price=_c11x14_prices,
    profit_margin=_calc_profit(24.00, _c11x14_prices),
    etsy_fee_pct=0.065,
    print_quality="premium",
    material="300gsm canvas, 1.5in pine stretcher bars",
    ships_days=7,
    gelato_sku="GEL-CANVAS-11X14-PRM",
    best_for=["office", "living_room", "graduation", "inspirational"],
)

_c16x20_prices = {"budget": 59.99, "mid": 79.99, "premium": 104.99}
_canvas_16x20 = GelatoProduct(
    product_id="canvas_16x20",
    name="Canvas 16x20 in",
    category="canvas",
    size="16x20 in",
    width_px=4800,
    height_px=6000,
    gelato_cost_usd=32.00,
    suggested_price=_c16x20_prices,
    profit_margin=_calc_profit(32.00, _c16x20_prices),
    etsy_fee_pct=0.065,
    print_quality="premium",
    material="300gsm canvas, 1.5in pine stretcher bars",
    ships_days=7,
    gelato_sku="GEL-CANVAS-16X20-PRM",
    best_for=["living_room", "bedroom", "office", "memorial"],
)

_c18x24_prices = {"budget": 74.99, "mid": 99.99, "premium": 129.99}
_canvas_18x24 = GelatoProduct(
    product_id="canvas_18x24",
    name="Canvas 18x24 in",
    category="canvas",
    size="18x24 in",
    width_px=5400,
    height_px=7200,
    gelato_cost_usd=40.00,
    suggested_price=_c18x24_prices,
    profit_margin=_calc_profit(40.00, _c18x24_prices),
    etsy_fee_pct=0.065,
    print_quality="premium",
    material="300gsm canvas, 1.5in pine stretcher bars",
    ships_days=7,
    gelato_sku="GEL-CANVAS-18X24-PRM",
    best_for=["large_wall", "office", "gift", "corporate"],
)

_c24x36_prices = {"budget": 109.99, "mid": 139.99, "premium": 179.99}
_canvas_24x36 = GelatoProduct(
    product_id="canvas_24x36",
    name="Canvas 24x36 in",
    category="canvas",
    size="24x36 in",
    width_px=7200,
    height_px=10800,
    gelato_cost_usd=58.00,
    suggested_price=_c24x36_prices,
    profit_margin=_calc_profit(58.00, _c24x36_prices),
    etsy_fee_pct=0.065,
    print_quality="premium",
    material="300gsm canvas, 1.5in pine stretcher bars",
    ships_days=7,
    gelato_sku="GEL-CANVAS-24X36-PRM",
    best_for=["large_wall", "statement_piece", "corporate", "luxury_gift"],
)

# ---------------------------------------------------------------------------
# FRAMED PRINTS
# ---------------------------------------------------------------------------

_f8x10_prices = {"budget": 44.99, "mid": 59.99, "premium": 79.99}
_framed_8x10 = GelatoProduct(
    product_id="framed_8x10",
    name="Framed Print 8x10 in",
    category="framed",
    size="8x10 in",
    width_px=2400,
    height_px=3000,
    gelato_cost_usd=22.00,
    suggested_price=_f8x10_prices,
    profit_margin=_calc_profit(22.00, _f8x10_prices),
    etsy_fee_pct=0.065,
    print_quality="premium",
    material="170gsm matte paper, black/white wood frame, acrylic glass",
    ships_days=8,
    gelato_sku="GEL-FRAMED-8X10-PRM",
    best_for=["gift", "nursery", "office", "memorial", "graduation"],
)

_f11x14_prices = {"budget": 54.99, "mid": 74.99, "premium": 99.99}
_framed_11x14 = GelatoProduct(
    product_id="framed_11x14",
    name="Framed Print 11x14 in",
    category="framed",
    size="11x14 in",
    width_px=3300,
    height_px=4200,
    gelato_cost_usd=28.00,
    suggested_price=_f11x14_prices,
    profit_margin=_calc_profit(28.00, _f11x14_prices),
    etsy_fee_pct=0.065,
    print_quality="premium",
    material="170gsm matte paper, black/white wood frame, acrylic glass",
    ships_days=8,
    gelato_sku="GEL-FRAMED-11X14-PRM",
    best_for=["office", "living_room", "graduation", "anniversary"],
)

_f16x20_prices = {"budget": 74.99, "mid": 99.99, "premium": 134.99}
_framed_16x20 = GelatoProduct(
    product_id="framed_16x20",
    name="Framed Print 16x20 in",
    category="framed",
    size="16x20 in",
    width_px=4800,
    height_px=6000,
    gelato_cost_usd=38.00,
    suggested_price=_f16x20_prices,
    profit_margin=_calc_profit(38.00, _f16x20_prices),
    etsy_fee_pct=0.065,
    print_quality="premium",
    material="170gsm matte paper, black/white wood frame, acrylic glass",
    ships_days=8,
    gelato_sku="GEL-FRAMED-16X20-PRM",
    best_for=["statement_piece", "office", "living_room", "gift"],
)

_f18x24_prices = {"budget": 94.99, "mid": 124.99, "premium": 164.99}
_framed_18x24 = GelatoProduct(
    product_id="framed_18x24",
    name="Framed Print 18x24 in",
    category="framed",
    size="18x24 in",
    width_px=5400,
    height_px=7200,
    gelato_cost_usd=48.00,
    suggested_price=_f18x24_prices,
    profit_margin=_calc_profit(48.00, _f18x24_prices),
    etsy_fee_pct=0.065,
    print_quality="premium",
    material="170gsm matte paper, black/white wood frame, acrylic glass",
    ships_days=8,
    gelato_sku="GEL-FRAMED-18X24-PRM",
    best_for=["large_wall", "corporate", "luxury_gift", "memorial"],
)

# ---------------------------------------------------------------------------
# ACRYLIC
# ---------------------------------------------------------------------------

_a8x10_prices = {"budget": 69.99, "mid": 89.99, "premium": 119.99}
_acrylic_8x10 = GelatoProduct(
    product_id="acrylic_8x10",
    name="Acrylic Print 8x10 in",
    category="acrylic",
    size="8x10 in",
    width_px=2400,
    height_px=3000,
    gelato_cost_usd=35.00,
    suggested_price=_a8x10_prices,
    profit_margin=_calc_profit(35.00, _a8x10_prices),
    etsy_fee_pct=0.065,
    print_quality="ultra",
    material="4mm clear acrylic, face-mounted print",
    ships_days=10,
    gelato_sku="GEL-ACRYLIC-8X10-ULT",
    best_for=["luxury_gift", "office", "modern_decor", "anniversary"],
)

_a12x16_prices = {"budget": 94.99, "mid": 124.99, "premium": 164.99}
_acrylic_12x16 = GelatoProduct(
    product_id="acrylic_12x16",
    name="Acrylic Print 12x16 in",
    category="acrylic",
    size="12x16 in",
    width_px=3600,
    height_px=4800,
    gelato_cost_usd=48.00,
    suggested_price=_a12x16_prices,
    profit_margin=_calc_profit(48.00, _a12x16_prices),
    etsy_fee_pct=0.065,
    print_quality="ultra",
    material="4mm clear acrylic, face-mounted print",
    ships_days=10,
    gelato_sku="GEL-ACRYLIC-12X16-ULT",
    best_for=["luxury_gift", "corporate", "modern_decor"],
)

_a16x20_prices = {"budget": 124.99, "mid": 164.99, "premium": 214.99}
_acrylic_16x20 = GelatoProduct(
    product_id="acrylic_16x20",
    name="Acrylic Print 16x20 in",
    category="acrylic",
    size="16x20 in",
    width_px=4800,
    height_px=6000,
    gelato_cost_usd=65.00,
    suggested_price=_a16x20_prices,
    profit_margin=_calc_profit(65.00, _a16x20_prices),
    etsy_fee_pct=0.065,
    print_quality="ultra",
    material="4mm clear acrylic, face-mounted print",
    ships_days=10,
    gelato_sku="GEL-ACRYLIC-16X20-ULT",
    best_for=["statement_piece", "corporate", "luxury_gift"],
)

# ---------------------------------------------------------------------------
# METAL PRINTS
# ---------------------------------------------------------------------------

_m8x10_prices = {"budget": 64.99, "mid": 84.99, "premium": 114.99}
_metal_8x10 = GelatoProduct(
    product_id="metal_8x10",
    name="Metal Print 8x10 in",
    category="metal",
    size="8x10 in",
    width_px=2400,
    height_px=3000,
    gelato_cost_usd=32.00,
    suggested_price=_m8x10_prices,
    profit_margin=_calc_profit(32.00, _m8x10_prices),
    etsy_fee_pct=0.065,
    print_quality="ultra",
    material="0.045in aluminum, dye-sublimation print",
    ships_days=10,
    gelato_sku="GEL-METAL-8X10-ULT",
    best_for=["modern_decor", "office", "luxury_gift", "outdoor"],
)

_m12x16_prices = {"budget": 89.99, "mid": 119.99, "premium": 154.99}
_metal_12x16 = GelatoProduct(
    product_id="metal_12x16",
    name="Metal Print 12x16 in",
    category="metal",
    size="12x16 in",
    width_px=3600,
    height_px=4800,
    gelato_cost_usd=45.00,
    suggested_price=_m12x16_prices,
    profit_margin=_calc_profit(45.00, _m12x16_prices),
    etsy_fee_pct=0.065,
    print_quality="ultra",
    material="0.045in aluminum, dye-sublimation print",
    ships_days=10,
    gelato_sku="GEL-METAL-12X16-ULT",
    best_for=["corporate", "modern_decor", "luxury_gift"],
)

_m16x20_prices = {"budget": 119.99, "mid": 154.99, "premium": 199.99}
_metal_16x20 = GelatoProduct(
    product_id="metal_16x20",
    name="Metal Print 16x20 in",
    category="metal",
    size="16x20 in",
    width_px=4800,
    height_px=6000,
    gelato_cost_usd=62.00,
    suggested_price=_m16x20_prices,
    profit_margin=_calc_profit(62.00, _m16x20_prices),
    etsy_fee_pct=0.065,
    print_quality="ultra",
    material="0.045in aluminum, dye-sublimation print",
    ships_days=10,
    gelato_sku="GEL-METAL-16X20-ULT",
    best_for=["statement_piece", "corporate", "luxury_gift", "outdoor"],
)

# ---------------------------------------------------------------------------
# MUGS
# ---------------------------------------------------------------------------

_mug11_prices = {"budget": 16.99, "mid": 22.99, "premium": 29.99}
_mug_11oz = GelatoProduct(
    product_id="mug_11oz",
    name="Mug 11oz",
    category="mug",
    size="11oz",
    width_px=2220,
    height_px=1025,
    gelato_cost_usd=8.00,
    suggested_price=_mug11_prices,
    profit_margin=_calc_profit(8.00, _mug11_prices),
    etsy_fee_pct=0.065,
    print_quality="standard",
    material="white ceramic, dishwasher-safe coating",
    ships_days=6,
    gelato_sku="GEL-MUG-11OZ-STD",
    best_for=["gift", "office", "motivational", "birthday", "christmas"],
)

_mug15_prices = {"budget": 19.99, "mid": 26.99, "premium": 34.99}
_mug_15oz = GelatoProduct(
    product_id="mug_15oz",
    name="Mug 15oz",
    category="mug",
    size="15oz",
    width_px=2640,
    height_px=1100,
    gelato_cost_usd=10.00,
    suggested_price=_mug15_prices,
    profit_margin=_calc_profit(10.00, _mug15_prices),
    etsy_fee_pct=0.065,
    print_quality="standard",
    material="white ceramic, dishwasher-safe coating",
    ships_days=6,
    gelato_sku="GEL-MUG-15OZ-STD",
    best_for=["gift", "office", "motivational", "birthday", "christmas"],
)

# ---------------------------------------------------------------------------
# MASTER CATALOG
# ---------------------------------------------------------------------------

GELATO_CATALOG: list[GelatoProduct] = [
    # Posters
    _poster_8x10,
    _poster_11x14,
    _poster_12x16,
    _poster_18x24,
    _poster_24x36,
    # Canvas
    _canvas_8x10,
    _canvas_11x14,
    _canvas_16x20,
    _canvas_18x24,
    _canvas_24x36,
    # Framed
    _framed_8x10,
    _framed_11x14,
    _framed_16x20,
    _framed_18x24,
    # Acrylic
    _acrylic_8x10,
    _acrylic_12x16,
    _acrylic_16x20,
    # Metal
    _metal_8x10,
    _metal_12x16,
    _metal_16x20,
    # Mugs
    _mug_11oz,
    _mug_15oz,
]


# ---------------------------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------------------------

def get_by_category(category: str) -> list[GelatoProduct]:
    """Return all products matching the given category."""
    return [p for p in GELATO_CATALOG if p.category == category]


def get_best_profit_products(min_profit: float = 15.0) -> list[GelatoProduct]:
    """Return products where mid-tier profit exceeds min_profit."""
    return [p for p in GELATO_CATALOG if p.profit_margin.get("mid", 0) >= min_profit]


def verify_catalog_mappings() -> dict:
    """Check that each product has a REAL Gelato product UID (not a placeholder).

    The seed catalog ships placeholder SKUs like 'GEL-POSTER-8X10-STD'; before
    go-live each must be replaced with the actual Gelato product UID from your
    connected account, or fulfillment will fail. Returns a summary + the list of
    products still on placeholders.
    """
    placeholders = []
    for p in GELATO_CATALOG:
        sku = (p.gelato_sku or "").strip()
        # Placeholder if empty or matches the seed 'GEL-...-...' pattern.
        if not sku or sku.upper().startswith("GEL-"):
            placeholders.append({"product_id": p.product_id, "size": p.size,
                                 "current_sku": sku or "(empty)"})
    total = len(GELATO_CATALOG)
    return {
        "total": total,
        "configured": total - len(placeholders),
        "placeholder_count": len(placeholders),
        "placeholders": placeholders,
        "all_real": not placeholders,
    }


def get_product(identifier: str) -> "GelatoProduct | None":
    """Look up a product by product_id, gelato_sku, or size string (case-insensitive)."""
    if not identifier:
        return None
    key = identifier.strip().lower()
    for p in GELATO_CATALOG:
        if key in (p.product_id.lower(), p.gelato_sku.lower(), p.size.lower()):
            return p
    # size given without unit, e.g. "11x14"
    for p in GELATO_CATALOG:
        if p.size.lower().replace(" in", "").strip() == key:
            return p
    return None


def dimensions_for(identifier: str,
                   default: tuple[int, int] = (5400, 7200)) -> tuple[int, int]:
    """Return (width_px, height_px) at 300 DPI for a product, or a sane default
    (18x24 in) when the product can't be resolved."""
    p = get_product(identifier)
    return (p.width_px, p.height_px) if p else default


def calculate_profit(product_id: str, sale_price: float) -> dict:
    """Calculate exact profit for a given product and sale price."""
    product = next((p for p in GELATO_CATALOG if p.product_id == product_id), None)
    if not product:
        return {}
    etsy_fees = round(sale_price * 0.065 + 0.20, 2)
    profit = round(sale_price - product.gelato_cost_usd - etsy_fees, 2)
    margin_pct = round((profit / sale_price) * 100, 1) if sale_price > 0 else 0.0
    return {
        "product": product.name,
        "sale_price": sale_price,
        "gelato_cost": product.gelato_cost_usd,
        "etsy_fees": etsy_fees,
        "net_profit": profit,
        "margin_pct": margin_pct,
        "profitable": profit > 0,
    }
