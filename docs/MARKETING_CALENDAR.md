# QuoteForge Annual Marketing Calendar (Formalized)

> **Think like a retailer, not a gift-buyer.** Buyers search *weeks* before an
> event, and a new Etsy listing takes 3–6 weeks to rank. So listings go live
> early and marketing starts as searches begin. This is the single source of
> truth — it's encoded in `quoteforge/etsy/marketing_calendar.py` and surfaced
> by `python -m quoteforge.admin calendar`.

## The Retailer Timeline

| Occasion | Listings Live | Marketing Starts | Revenue Rank |
|---|---|---|---|
| Christmas | Sep 15 | Nov 1 | 🥇 #1 (30–50% of annual revenue) |
| Mother's Day | Mar 1 | Apr 1 | #2 |
| Graduation | Mar 15 | Apr 15 | #3 |
| Wedding Season | Feb 1 | Apr 1 | #4 |
| Father's Day | Apr 15 | May 15 | #5 |
| Valentine's Day | Dec 15 | Jan 1 | #6 |
| Easter | Jan 15 | Feb 15 | #7 |
| Back to School | Jun 1 | Jul 1 | #8 |
| Thanksgiving | Sep 1 | Oct 1 | #9 |
| Halloween | Aug 1 | Sep 1 | #10 |

**How to use it:** run `python -m quoteforge.admin calendar` any time. It shows
every list-live and marketing-start date due in the next 60 days, flags
`OVERDUE` / `THIS WEEK`, and sorts by soonest + revenue rank — so you always act
4–8 weeks before each occasion.

## Month-by-Month Push

| Month | Primary push | Also prep / start listing |
|---|---|---|
| **Jan** | New Year goals, future-self, vision boards, Christian new beginnings | Valentine's marketing begins |
| **Feb** | Valentine's (wife/husband/partner/fiancé) | Wedding Season listings live; Easter listings live |
| **Mar** | Easter (Christian, prayers, blessings) | Mother's Day + Graduation listings go live |
| **Apr** | **Graduation campaign** (HS/college/dental/med) — huge | Mother's Day + Wedding + Graduation marketing |
| **May** | Mother's Day (mom/grandma/stepmom) | Wedding season (vows, anniversaries); Father's Day listings live |
| **Jun** | Father's Day (dad/grandpa/military dad) | Summer weddings; Back-to-School listings live |
| **Jul** | Military, deployment, retirement, veterans | Back-to-School marketing |
| **Aug** | Back to School (teacher, dorm, future profession) | Halloween listings live |
| **Sep** | Fall collection (family, faith, gratitude) | **Christmas + Thanksgiving listings go live** |
| **Oct** | Pregnancy, new baby, adoption, family | Thanksgiving marketing; Christmas ramp-up |
| **Nov** | Thanksgiving (gratitude, legacy) | **Christmas marketing starts aggressively** |
| **Dec** | **Christmas** (Christian, family, blessings) | Valentine's listings go live (Dec 15) |

## The Automation Engine (what runs vs. what you do)

| Engine | What the software does | Your part |
|---|---|---|
| **Listing factory** | Generates titles, tags, quotes, designs (free Pillow renderer) | Publish to Etsy by the list-live date |
| **Campaign planner** | `campaign <Month>` → every listing + publish-by date | Follow the schedule |
| **Sales engine** | `sales` → upsells, reviews, win-backs to send | Paste into Etsy messages |
| **Email sequence** | Decides Day 0 / 14 / 30 touch per order | Send via Etsy |
| **Reports** | Daily/weekly/monthly/yearly profit, auto-emailed | Read them |
| **Health monitor** | Confirms all jobs run, every 5 hours | Nothing (alerts you) |

### Post-purchase email sequence (Day 0 / 14 / 30)

| Day | Message | Purpose |
|---|---|---|
| 0 | Thank You | Confirm + set expectations |
| 14 | Review Request | Lift ranking via reviews |
| 30 | Upsell | "Looking for a matching poster for your son?" |

`due_email_touch(order_created_at)` tells you which touch each order is due for.

## Honest boundary — what's NOT auto-posted

These need external tools or are against Etsy's API rules for new shops, so the
software prepares the *content/plan* and you (or a VA, or a paid tool) execute:

- **Pinterest pins** — software gives you the design + title; use Tailwind/Canva
  to schedule pins. (Pinterest is the #1 underused Etsy traffic source.)
- **Blog posts** — the AI can draft "gift ideas" articles; you publish them.
- **Etsy Ads / Offsite Ads** — set the budget manually in Etsy.
- **Auto-listing to Etsy** — Etsy's API doesn't allow it for new shops; you
  publish from the campaign plan.

## Scaling Targets

| Year | Listings | Strategy |
|---|---|---|
| 1 | 500 | Validate niches, nail the seasonal calendar |
| 2 | 2,000 | Weekly batch generation, add channels (Pinterest) |
| 3 | 5,000+ | Multiple shops, VAs, B2B/wholesale |

**The real advantage** isn't one poster — it's the system:
`Customer Story → AI Quote → Artwork → Gelato Print → Etsy Delivery`
runs continuously while you focus on adding niches and launching each seasonal
campaign 4–8 weeks early.
