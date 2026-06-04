"""Full Gelato product range — beyond posters. The key insight: the personalized
MESSAGE is the product, so one customer story can become 5-10 different items
(poster, mug, journal, card, ornament, tote...), lifting average order value
without creating new content.

Each product line has realistic 2026 Gelato cost, a mid-tier sell price, net
profit (after Etsy fees), a strategic rank, and which occasions it fits.
"""
from dataclasses import dataclass

from quoteforge.etsy.profit_calculator import calculate_order_profit


@dataclass
class ProductLine:
    name: str
    category: str           # print | drinkware | apparel | paper | accessory | seasonal | baby | pet
    gelato_cost: float      # what Gelato charges you per unit (USD)
    sell_price: float       # recommended mid-tier Etsy price (USD)
    rank: int               # 1 = highest strategic potential for this business
    personalization: str    # "name" | "message" | "photo"
    repeat_buy: bool        # do customers buy these repeatedly?

    @property
    def net_profit(self) -> float:
        return calculate_order_profit(self.sell_price, self.gelato_cost)["net_profit"]

    @property
    def margin_pct(self) -> float:
        return calculate_order_profit(self.sell_price, self.gelato_cost)["margin_pct"]


# Ranked roughly per strategic potential for a message-first business.
PRODUCT_LINES: list[ProductLine] = [
    ProductLine("Personalized Journal", "paper", 9.00, 27.99, 1, "name", True),
    ProductLine("Greeting Card", "paper", 2.20, 7.99, 2, "message", True),
    ProductLine("Mug 11oz", "drinkware", 8.00, 21.99, 3, "message", True),
    ProductLine("Tote Bag", "accessory", 12.00, 29.99, 4, "message", True),
    ProductLine("Christmas Ornament", "seasonal", 9.00, 24.99, 5, "name", True),
    ProductLine("T-Shirt", "apparel", 13.00, 29.99, 6, "message", True),
    ProductLine("Hoodie", "apparel", 28.00, 54.99, 6, "message", False),
    ProductLine("Sweatshirt", "apparel", 24.00, 49.99, 6, "message", False),
    ProductLine("Wall Calendar", "paper", 13.00, 32.99, 7, "photo", False),
    ProductLine("Photo Puzzle", "accessory", 15.00, 36.99, 8, "photo", False),
    ProductLine("Sticker Pack", "accessory", 2.50, 7.99, 9, "message", True),
    ProductLine("Mouse Pad", "accessory", 8.00, 19.99, 10, "message", False),
    ProductLine("Coaster Set", "accessory", 10.00, 26.99, 10, "name", False),
    ProductLine("Fridge Magnet", "accessory", 3.50, 11.99, 10, "message", True),
    ProductLine("Phone Case", "accessory", 12.00, 27.99, 10, "message", False),
    ProductLine("Baby Onesie", "baby", 13.00, 28.99, 10, "name", True),
    ProductLine("Baby Bib", "baby", 10.00, 22.99, 10, "name", True),
    ProductLine("Pet Bandana", "pet", 9.00, 20.99, 10, "name", True),
    ProductLine("Pet Bowl", "pet", 16.00, 34.99, 10, "name", False),
    # Existing print products (kept here for the unified catalog/cross-sell)
    ProductLine("Poster 18x24", "print", 11.00, 29.99, 3, "message", False),
    ProductLine("Canvas 16x20", "print", 32.00, 64.99, 7, "message", False),
    ProductLine("Framed Print 11x14", "print", 28.00, 54.99, 7, "message", False),
]

# The universal set — almost any customer story works on these four.
UNIVERSAL_PRODUCTS = ["Poster 18x24", "Mug 11oz", "Greeting Card", "Tote Bag"]

# occasion keyword → extra product lines that fit especially well
OCCASION_PRODUCTS: list[tuple[str, list[str]]] = [
    ("prayer",     ["Personalized Journal", "Mug 11oz", "Tote Bag", "Greeting Card"]),
    ("christian",  ["Personalized Journal", "Mug 11oz", "Tote Bag", "Sticker Pack"]),
    ("faith",      ["Personalized Journal", "Greeting Card", "Sticker Pack"]),
    ("graduation", ["Mug 11oz", "Tote Bag", "T-Shirt", "Personalized Journal", "Greeting Card"]),
    ("future",     ["Mug 11oz", "Tote Bag", "T-Shirt", "Personalized Journal"]),
    ("memorial",   ["Photo Puzzle", "Christmas Ornament", "Fridge Magnet", "Greeting Card"]),
    ("loss",       ["Greeting Card", "Christmas Ornament", "Photo Puzzle"]),
    ("pet",        ["Pet Bandana", "Pet Bowl", "Photo Puzzle", "Fridge Magnet"]),
    ("wedding",    ["Greeting Card", "Coaster Set", "Photo Puzzle", "Canvas 16x20", "Christmas Ornament"]),
    ("anniversary",["Greeting Card", "Coaster Set", "Mug 11oz", "Canvas 16x20"]),
    ("baby",       ["Baby Onesie", "Baby Bib", "Wall Calendar", "Christmas Ornament"]),
    ("pregnancy",  ["Baby Onesie", "Baby Bib", "Personalized Journal"]),
    ("teacher",    ["Mug 11oz", "Tote Bag", "T-Shirt", "Sticker Pack"]),
    ("nurse",      ["Mug 11oz", "Tote Bag", "T-Shirt", "Personalized Journal"]),
    ("dentist",    ["Mug 11oz", "Tote Bag", "T-Shirt", "Personalized Journal"]),
    ("christmas",  ["Christmas Ornament", "Mug 11oz", "Greeting Card"]),
    ("recovery",   ["Personalized Journal", "Mug 11oz", "Sticker Pack"]),
    ("sobriety",   ["Personalized Journal", "Fridge Magnet", "Sticker Pack"]),
    ("retirement", ["Mug 11oz", "Canvas 16x20", "Greeting Card"]),
    ("employee",   ["Mug 11oz", "Mouse Pad", "Personalized Journal", "Coaster Set"]),
    ("corporate",  ["Mug 11oz", "Mouse Pad", "Personalized Journal", "Tote Bag"]),
]


def _by_name(name: str) -> ProductLine | None:
    return next((p for p in PRODUCT_LINES if p.name == name), None)


def story_to_products(occasion: str, max_products: int = 8) -> list[dict]:
    """ONE story → MANY products. Returns the recommended product bundle for an
    occasion, each with price and net profit, most-relevant first.
    """
    low = (occasion or "").lower()
    names: list[str] = []
    for key, products in OCCASION_PRODUCTS:
        if key in low:
            names.extend(products)
    # Always include the universal four as fallbacks
    names.extend(UNIVERSAL_PRODUCTS)
    # De-dupe preserving order
    names = list(dict.fromkeys(names))[:max_products]

    out = []
    for n in names:
        p = _by_name(n)
        if p:
            out.append({
                "product": p.name, "category": p.category,
                "sell_price": p.sell_price, "net_profit": round(p.net_profit, 2),
                "personalization": p.personalization,
            })
    return out


def bundle_value(occasion: str, max_products: int = 8) -> dict:
    """Total potential profit if a customer buys the whole product bundle."""
    products = story_to_products(occasion, max_products)
    return {
        "occasion": occasion,
        "product_count": len(products),
        "total_revenue": round(sum(p["sell_price"] for p in products), 2),
        "total_profit": round(sum(p["net_profit"] for p in products), 2),
        "products": products,
    }


def catalog_by_category() -> dict[str, list[ProductLine]]:
    cats: dict[str, list[ProductLine]] = {}
    for p in PRODUCT_LINES:
        cats.setdefault(p.category, []).append(p)
    return cats


def top_ranked(n: int = 10) -> list[ProductLine]:
    return sorted(PRODUCT_LINES, key=lambda p: p.rank)[:n]
