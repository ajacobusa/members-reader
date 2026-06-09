"""Curated Wedding & Corporate gift packages.

Packages are multi-piece sets sold as one offer. Every package price is computed
from REAL variation prices via the same floor-safe bundle math used everywhere
else (`variations.bundle_quote`), so the 60% net-margin floor is never broken -
even after the package discount. No hardcoded prices.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Package:
    key: str
    name: str
    audience: str          # "wedding" | "corporate"
    blurb: str
    pieces: int            # number of prints in the set
    tier: str              # margin tier used for floor math
    includes: tuple        # bullet points


WEDDING_PACKAGES = (
    Package("vows", "The Vows Set", "wedding",
            "Your wedding vows or first dance lyrics as a framed centerpiece, "
            "plus two matching prints for the couple's first home.", 3, "top",
            ("1 large framed centerpiece (premium wood)",
             "2 coordinated prints", "Custom names, date & wording",
             "Free digital proof before printing")),
    Package("guest", "Guest & Gift Bundle", "wedding",
            "A signature framed piece for the couple plus a set of small prints "
            "as keepsake favors or bridal-party gifts.", 5, "mid",
            ("1 framed signature piece", "4 keepsake prints",
             "Matching design & palette", "Bulk-friendly pricing")),
)

CORPORATE_PACKAGES = (
    Package("recognition", "Team Recognition Set", "corporate",
            "Personalized award/values prints for employee recognition, onboarding "
            "or milestones - your branding, names and message.", 5, "mid",
            ("5 personalized prints (poster or framed)",
             "Your logo, colors & wording", "Volume pricing - scales with quantity",
             "Single invoice, one approval")),
    Package("client", "Client Gifting Program", "corporate",
            "Branded, made-to-order art gifts for clients and partners - ship "
            "individually or in bulk, fully personalized.", 10, "mid",
            ("10+ branded gift prints", "Individual personalization",
             "Recurring/seasonal scheduling available",
             "Dedicated account contact")),
)


def _representative(tier: str, variations=None) -> tuple[float, float]:
    """A representative (list_price, cost) for a tier, from real variations.

    Pass `variations` (a prebuilt list) to avoid rebuilding the catalog per call.
    Falls back to config defaults if the catalog can't be read, chosen so the
    floor math still produces a sane, floor-clearing price.
    """
    from quoteforge.config import DEFAULT_LIST_PRICE, DEFAULT_GELATO_COST
    try:
        if variations is None:
            from quoteforge.etsy.variations import build_variations
            variations = build_variations()
        vs = [v for v in variations if v.tier == tier] or list(variations)
        if not vs:
            return (DEFAULT_LIST_PRICE, DEFAULT_GELATO_COST)
        # median-ish: pick the variation nearest the average price
        avg = sum(v.price for v in vs) / len(vs)
        pick = min(vs, key=lambda v: abs(v.price - avg))
        return float(pick.price), float(pick.gelato_cost)
    except Exception:  # noqa: BLE001
        return (DEFAULT_LIST_PRICE, DEFAULT_GELATO_COST)


def package_quote(pkg: Package, variations=None) -> dict:
    """Floor-safe 'from' price for a package: the bundle total for its piece count.

    Uses variations.bundle_quote, which caps the discount at the 60% net floor, so
    the returned per-piece price always clears the floor.
    """
    from quoteforge.etsy.variations import bundle_quote
    list_price, cost = _representative(pkg.tier, variations)
    q = bundle_quote(list_price, cost, pkg.pieces, pkg.tier)
    return {
        "key": pkg.key, "name": pkg.name, "audience": pkg.audience,
        "blurb": pkg.blurb, "pieces": pkg.pieces, "includes": list(pkg.includes),
        "from_total": q["total"], "per_piece": q["unit"],
        "discount_pct": q["discount_pct"], "margin_pct": q["margin_pct"],
        "holds_floor": q["holds_floor"],
    }


def all_packages() -> list[dict]:
    # Build the variations catalog ONCE and reuse it for every package quote.
    variations = None
    try:
        from quoteforge.etsy.variations import build_variations
        variations = build_variations()
    except Exception:  # noqa: BLE001
        variations = None
    return [package_quote(p, variations)
            for p in (*WEDDING_PACKAGES, *CORPORATE_PACKAGES)]


def packages_section(b2b_email: str) -> str:
    """Render the Wedding & Corporate packages section for the storefront."""
    quotes = all_packages()
    if not quotes:
        return ""

    def card(q: dict) -> str:
        inc = "".join(f"<li>{i}</li>" for i in q["includes"])
        save = (f'<span class="pksave">Set price - {q["discount_pct"]}% vs singles</span>'
                if q["discount_pct"] else "")
        return (
            f'<div class="pkcard"><div class="pkname">{q["name"]}</div>'
            f'<div class="pkfrom">from ${q["from_total"]:.2f} '
            f'<span class="pkpp">(~${q["per_piece"]:.2f}/piece)</span></div>'
            f'{save}<p class="pkblurb">{q["blurb"]}</p>'
            f'<ul class="pkinc">{inc}</ul>'
            f'<a class="pkcta" href="mailto:{b2b_email}?subject=Package%20inquiry:%20'
            f'{q["name"].replace(" ", "%20")}">Request this package &rarr;</a></div>')

    weddings = "".join(card(q) for q in quotes if q["audience"] == "wedding")
    corporate = "".join(card(q) for q in quotes if q["audience"] == "corporate")
    # Collapsed by default - keeps the page tight for the common case (one personal
    # gift); buyers shopping at scale tap to expand.
    return (
        '<details class="packages"><summary class="pksummary">'
        '<span class="pktitle">Wedding &amp; corporate packages</span>'
        '<span class="pkhint">Multi-piece sets, priced for gifting at scale — tap to view</span>'
        '</summary>'
        '<p class="pksub">Curated multi-piece sets - personalized, made to order, '
        'and priced for gifting at scale. Every set price still clears our quality '
        'and margin standards.</p>'
        '<h3 class="pkgrouph">💍 Weddings</h3>'
        f'<div class="pkgrid">{weddings}</div>'
        '<h3 class="pkgrouph">🏢 Corporate &amp; bulk</h3>'
        f'<div class="pkgrid">{corporate}</div></details>')
