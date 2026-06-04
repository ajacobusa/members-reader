# Product Expansion — Beyond Wall Art

Most Gelato sellers get trapped in "posters only." The bigger opportunity:
products where **the personalized message IS the product.** One customer story
→ 5–10 products → much higher order value with **zero extra content**.

## The core model

```
Customer Story  →  AI Message  →  Apply to:
                                   Poster · Mug · Journal · Card ·
                                   Tote · Ornament · T-Shirt · Puzzle ...
```

Run `python -m quoteforge.admin products <Occasion>` to get the matching bundle.
Example (Graduation): one story becomes a 6-product set worth **~$148 revenue /
~$77 profit** vs. ~$16 for a single poster.

## The product range (ranked by potential)

| # | Product | Why it works |
|---|---|---|
| 1 | **Personalized Journal** | Higher perceived value than posters (prayer, gratitude, recovery, future-professional) |
| 2 | **Greeting Cards** | Huge overlooked market; AI writes the message; repeat buys |
| 3 | **Mugs** | Bought repeatedly; "To My Daughter", "Future Dentist", "Christian Mom" |
| 4 | **Tote Bags** | Easy personalization; Bible study, teacher, nurse, book lover |
| 5 | **Christmas Ornaments** | One of Etsy's biggest categories; baby's first, newlyweds, pet memorial |
| 6 | **Apparel** (tee/hoodie/sweatshirt) | "Future DDS", "Class of 2027", "God Is Within Her" |
| 7 | **Calendars** | Family, Christian, grandparent, new-baby first year |
| 8 | **Photo Puzzles** | Customer submits a family/wedding/memorial photo |
| 9 | **Stickers** | Very scalable; sell in bundles (nursing, faith, mental health) |
| 10 | **Mouse Pads / Coasters / Magnets / Phone Cases** | Low-cost impulse + corporate niche |
| — | **Baby** (onesie, bib) · **Pet** (bandana, bowl) | Parents & pet owners spend heavily / emotionally |
| — | **Corporate** (employee recognition, core values) | Bigger budgets than consumers |

## How it's wired into the system

- `product_lines.py` — every product with real Gelato cost, sell price, net
  profit (after Etsy fees), strategic rank, and personalization type.
- `story_to_products(occasion)` — the cross-sell matrix: which products fit each
  occasion (e.g. memorial → photo puzzle + ornament; baby → onesie + bib).
- The **sales engine upsell** now suggests the matching product set, not just a
  canvas upgrade — so every fulfilled order is an automatic cross-sell prompt.
- `bundle_value(occasion)` — total revenue/profit if they buy the whole set.

## How to use it for real money

1. **List the same design across products.** When you build a poster listing,
   also create the mug + journal + card versions — Gelato prints them all from
   the same artwork/message.
2. **Offer a "matching set"** in the proof message and the Day-30 upsell:
   *"Want this design as a mug and journal too? I can do a matching set."*
3. **Lead with journals, cards, and mugs** for new niches — they convert and
   repeat better than posters.

## Honest note

Each product still needs a Gelato product set up and an Etsy listing (or a
matching-set listing with variants). The software gives you the message, the
design, the price, and the cross-sell plan — you create the listings. The win
is average order value: turning one $16 poster sale into a $40–$80 multi-product
order from the **same** customer story.
