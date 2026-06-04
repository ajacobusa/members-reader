"""Gallery-set bundles — the high-ticket AOV lever.

High-ticket POD wins by raising average order value: instead of one $30 poster,
sell a coordinated multi-piece SET (a triptych or a 3-5 print gallery wall) as a
single premium listing at $180-500. Same personalized story, one transaction,
several pieces — margins stay healthy and AOV jumps.

Each set bundles N coordinated personalized prints. Economics use the real
per-piece Gelato cost so the set price reflects true margin (after Etsy fees).
"""
from dataclasses import dataclass

from quoteforge.etsy.profit_calculator import calculate_order_profit


@dataclass
class GallerySet:
    name: str
    occasion: str            # maps to the message generator / launch taxonomy
    relationship: str        # who it's for
    pieces: int              # number of coordinated prints in the set
    piece_format: str        # e.g. "Framed 11x14", "Canvas 12x16"
    per_piece_gelato: float  # Gelato cost per piece (USD)
    set_price: float         # listed set price (USD)

    @property
    def gelato_cost(self) -> float:
        return round(self.per_piece_gelato * self.pieces, 2)

    @property
    def net_profit(self) -> float:
        return calculate_order_profit(self.set_price, self.gelato_cost)["net_profit"]

    @property
    def margin_pct(self) -> float:
        return calculate_order_profit(self.set_price, self.gelato_cost)["margin_pct"]


# Coordinated multi-piece sets built on the proven launch categories.
# Prices target the article's $180-500 high-ticket band with 50%+ margins.
GALLERY_SETS: list[GallerySet] = [
    GallerySet("Daughter Gallery Trio", "Graduation", "Daughter",
               3, "Framed 11x14", 28.0, 219.0),
    GallerySet("Wedding Vows Gallery Wall", "Wedding", "Wife",
               3, "Framed 11x14", 28.0, 249.0),
    GallerySet("Family Blessing Triptych", "Just Because", "Family",
               3, "Canvas 12x16", 32.0, 239.0),
    GallerySet("Christian Faith Set", "Just Because", "Family",
               3, "Framed 11x14", 28.0, 209.0),
    GallerySet("Memorial Remembrance Set", "Memorial / In Memory Of", "Family",
               3, "Framed 11x14", 28.0, 209.0),
    GallerySet("Nursery Story Set", "New Baby", "Baby",
               4, "Framed 8x10", 22.0, 229.0),
    GallerySet("Anniversary Canvas Triptych", "Anniversary", "Wife",
               3, "Canvas 16x20", 38.0, 299.0),
    GallerySet("Deluxe Room Makeover (5)", "Graduation", "Daughter",
               5, "Framed 11x14", 28.0, 399.0),
]


def set_economics(gset: GallerySet) -> dict:
    p = calculate_order_profit(gset.set_price, gset.gelato_cost)
    return {
        "name": gset.name,
        "occasion": gset.occasion,
        "relationship": gset.relationship,
        "pieces": gset.pieces,
        "piece_format": gset.piece_format,
        "set_price": gset.set_price,
        "gelato_cost": gset.gelato_cost,
        "net_profit": p["net_profit"],
        "margin_pct": p["margin_pct"],
        # vs. selling a single piece — the AOV/profit uplift the set buys you
        "single_piece_price": round(gset.set_price / gset.pieces, 2),
    }


def sets_for_occasion(occasion: str) -> list[GallerySet]:
    low = (occasion or "").lower()
    return [s for s in GALLERY_SETS
            if low and (low in s.occasion.lower() or low in s.relationship.lower())]


def aov_uplift(single_price: float = 29.99) -> dict:
    """How much the average set lifts AOV vs. a single poster sale."""
    avg_set = round(sum(s.set_price for s in GALLERY_SETS) / len(GALLERY_SETS), 2)
    avg_profit = round(sum(s.net_profit for s in GALLERY_SETS) / len(GALLERY_SETS), 2)
    return {
        "single_price": single_price,
        "avg_set_price": avg_set,
        "avg_set_profit": avg_profit,
        "aov_multiple": round(avg_set / single_price, 1) if single_price else 0.0,
    }


def format_sets_text() -> str:
    lines = ["=" * 60, "QUOTEFORGE GALLERY SETS - high-ticket bundles", "=" * 60,
             f"{'Set':32}{'Pieces':>7}{'Price':>8}{'Profit':>8}{'Margin':>8}"]
    for s in GALLERY_SETS:
        lines.append(f"{s.name:32}{s.pieces:>7}{s.set_price:>8.0f}"
                     f"{s.net_profit:>8.0f}{s.margin_pct:>7.0f}%")
    up = aov_uplift()
    lines.append("-" * 60)
    lines.append(f"Average set: ${up['avg_set_price']:.0f}  "
                 f"(~{up['aov_multiple']}x a single ${up['single_price']:.0f} poster)")
    lines.append(f"Average profit per set: ${up['avg_set_profit']:.0f}")
    lines.append("Tip: price the largest set attractively so it pulls buyers up.")
    lines.append("=" * 60)
    return "\n".join(lines)
