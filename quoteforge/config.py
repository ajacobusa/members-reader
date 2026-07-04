"""Central configuration — all tunables in one place, sourced from environment
variables (and an optional .env file) with safe defaults.

Covers API keys, pricing/margin policy, pipeline behavior, autopilot limits,
backup retention, and the product/size catalog.
"""
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Load .env file if present (python-dotenv optional — degrade gracefully)
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parent.parent / ".env"
    if _env_path.exists():
        # override=True makes the .env file authoritative. Without it, an empty
        # OS environment variable (e.g. ANTHROPIC_API_KEY="") silently wins over
        # the value in .env and keys appear "not set".
        load_dotenv(_env_path, override=True)
except ImportError:
    logger.debug("python-dotenv not installed; using OS environment variables only")


def _env_bool(name: str, default: bool = False) -> bool:
    """Read a boolean env var; true/1/yes/on (any case) count as True."""
    return os.getenv(name, str(default)).strip().lower() in ("true", "1", "yes", "on")


# TEST_MODE — when true, pipeline generates mock outputs without calling paid APIs.
# Keep this ON until a full real test order has succeeded end-to-end.
TEST_MODE: bool = _env_bool("TEST_MODE", True)

# API Keys — set these as environment variables or paste directly
ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
UNSPLASH_ACCESS_KEY: str = os.getenv("UNSPLASH_ACCESS_KEY", "")
BANNERBEAR_API_KEY: str = os.getenv("BANNERBEAR_API_KEY", "")

# Output / data directory. Defaults to <project>/data so it lives NEXT TO the code
# and is therefore drive-letter-independent - critical when the project runs from a
# USB drive whose letter can change when another device is plugged in. Computed from
# this file's location, so it resolves to whatever drive the code is actually on.
# Override with OUTPUT_DIR env on a server (e.g. a persistent disk like /data).
_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
OUTPUT_DIR: Path = (Path(os.environ["OUTPUT_DIR"]) if os.getenv("OUTPUT_DIR")
                    else _PROJECT_ROOT / "data")

# Claude models.
# Quote/message/SEO generation is short and simple — Haiku 4.5 does it well at
# ~1/3 the cost of Sonnet ($1/$5 per 1M vs $3/$15). Override per env if you want
# higher quality (e.g. set CLAUDE_MODEL=claude-sonnet-4-6).
CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5")

# Bannerbear template UID — set this after creating your template
BANNERBEAR_TEMPLATE_UID: str = os.getenv("BANNERBEAR_TEMPLATE_UID", "YOUR_BANNERBEAR_TEMPLATE_UID")

# Renderer selection: "local" (free, Pillow — default) | "bannerbear" | "canva".
# Local rendering composites the quote over an Unsplash background with Pillow,
# eliminating the Bannerbear subscription ($49/mo) for standard quote posters.
RENDERER: str = os.getenv("RENDERER", "local")

# Generate a styled-room lifestyle mockup alongside the print file. Context sells
# high-ticket wall art: a framed print on a styled wall converts far better than
# a print on white. Free (Pillow); the mockup is a listing image, not the print.
GENERATE_ROOM_MOCKUP: bool = _env_bool("GENERATE_ROOM_MOCKUP", True)

# Target net margin floor (% of sale price kept after Gelato + Etsy fees).
# Set to 60%: every product and gallery set is priced to clear this, and the
# margin guard flags anything that slips below it (e.g. after a fee increase).
TARGET_MARGIN_PCT: float = float(os.getenv("TARGET_MARGIN_PCT", "60"))
# When a real order's economics fall below the margin floor, the pre-vendor gate
# HOLDS it for owner review instead of auto-routing money to the vendor. Set this
# truthy only to allow deliberate loss-leaders through without a hold.
ALLOW_BELOW_FLOOR_ORDERS: bool = os.getenv(
    "ALLOW_BELOW_FLOOR_ORDERS", "").strip().lower() in ("1", "true", "yes", "on")
# Real per-order costs beyond the print blank, folded into the AUTHORITATIVE
# profit calc so reported/audited margins are honest (NOT into the list-price
# floor - the 65% list anchor already absorbs them, so customer prices don't
# change; only bare-floor items like gallery sets are re-priced to stay >=60%).
#   PACKAGING_COST_USD   : mailer/tube + materials per physical order
#   REPRINT_RESERVE_PCT  : % of print cost reserved for defect/damage reprints
#                          (POD reprint rates run ~2-4%; raise for fragile lines)
#   CAC_CONTINGENCY_PCT  : optional per-order marketing/ad reserve (% of sale).
#                          Default 0: the 60% floor is a CONTRIBUTION margin and
#                          marketing comes out of it (standard POD practice);
#                          set >0 to model ad-attributed orders explicitly.
# Alert when an order's ACTUAL shipping exceeds the modeled shipping for its
# destination by more than this % - the silent margin-leak tripwire.
SHIPPING_VARIANCE_ALERT_PCT: float = float(os.getenv("SHIPPING_VARIANCE_ALERT_PCT", "10"))
# A past customer with no order in this many days is "lapsed" - a win-back
# target (re-engaging a prior buyer is the cheapest profit there is).
LAPSED_CUSTOMER_DAYS: int = int(os.getenv("LAPSED_CUSTOMER_DAYS", "90"))
# Window (days) around a repeat customer's PREDICTED next-purchase date in which
# to reach out pre-emptively - before they drift off and lapse.
CLV_DUE_SOON_DAYS: int = int(os.getenv("CLV_DUE_SOON_DAYS", "10"))
# Claim reporting deadlines (calendar days from the delivery anchor). 0..REPORT
# = auto-accept; REPORT+1..FLAG = manual review; > FLAG = management approval.
# Gelato Create's quality guarantee accepts claims within 30 days of receipt
# (SUPPLIER_CLAIM_DAYS). We set the customer auto-accept window to 7 days,
# leaving a 23-DAY BUFFER inside that 30 for customer back-and-forth, photo
# collection, and filing with Gelato before its cutoff (and the freshest
# evidence). Days 8-30 are still file-able but flagged (buffer zone); past 30
# the partner won't reimburse, so any approval is goodwill/at-cost. Override via
# env if a contract differs.
CLAIM_REPORT_DAYS: int = int(os.getenv("CLAIM_REPORT_DAYS", "7"))
CLAIM_FLAG_DAYS: int = int(os.getenv("CLAIM_FLAG_DAYS", "30"))
SUPPLIER_CLAIM_DAYS: int = int(os.getenv("SUPPLIER_CLAIM_DAYS", "30"))
PACKAGING_COST_USD: float = float(os.getenv("PACKAGING_COST_USD", "0.75"))
REPRINT_RESERVE_PCT: float = float(os.getenv("REPRINT_RESERVE_PCT", "3"))
CAC_CONTINGENCY_PCT: float = float(os.getenv("CAC_CONTINGENCY_PCT", "0"))
# Per-tier net-margin floors for the upsell ladder (entry=Poster, mid=Framed,
# top=Canvas/Acrylic/Metal). Default each to the global target so we never sell
# below 60%; raise a tier as sales data justifies more margin on it.
MARGIN_FLOOR_ENTRY: float = float(os.getenv("MARGIN_FLOOR_ENTRY", str(TARGET_MARGIN_PCT)))
MARGIN_FLOOR_MID: float = float(os.getenv("MARGIN_FLOOR_MID", str(TARGET_MARGIN_PCT)))
MARGIN_FLOOR_TOP: float = float(os.getenv("MARGIN_FLOOR_TOP", str(TARGET_MARGIN_PCT)))
# Single items LIST at this margin (the anchor); bundle/quantity discounts reduce
# toward - but never below - TARGET_MARGIN_PCT (the hard floor).
# LIST (anchor) margin. 65% on the full 9.5%+$0.20 fee stack reproduces the
# SAME list prices the old 68%-on-6.5% target produced (denominator 0.255) -
# so correcting the fee stack does not shock live prices; it only makes the
# reported margin honest (~65% real) and raises the bare 60% floor to genuine.
LIST_MARGIN_PCT: float = float(os.getenv("LIST_MARGIN_PCT", "65"))
# Dynamic (seasonal-demand) pricing. UPLIFT-ONLY: during active high-demand
# seasons we raise prices above list by up to DYNAMIC_MAX_UPLIFT_PCT. It can never
# push a price DOWN, so the 60% net floor is structurally safe. Toggle off to
# always sell at list price.
DYNAMIC_PRICING_ENABLED: bool = os.getenv("DYNAMIC_PRICING_ENABLED", "true").lower() in ("1", "true", "yes")
DYNAMIC_MAX_UPLIFT_PCT: float = float(os.getenv("DYNAMIC_MAX_UPLIFT_PCT", "15"))
# Welcome / first-order promo (exit-intent capture). Set the code in your Etsy
# shop coupons; these just drive the on-site copy. Empty code hides the offer.
ETSY_SHOP_URL: str = os.getenv("ETSY_SHOP_URL", "").strip().rstrip("/")
# The CURRENT live storefront URL that marketing (Pinterest pins, etc.) links to.
# Today the store runs on the marketplace, so this is unset and falls back to the
# Etsy shop. When the DIRECT store goes live, set STORE_URL=https://joffiels.com
# to flip every marketing link to the new site in one switch.
STORE_URL: str = os.getenv("STORE_URL", "").strip().rstrip("/")
# Same-flow payment: a hosted checkout link (Stripe Payment Link / PayPal /
# Square). When set, completing an order opens it IMMEDIATELY - the customer
# pays in the same visit instead of waiting for an emailed link. Takes
# priority over the Etsy redirect. (Etsy has no payments API; off-site card
# entry for Etsy orders is not possible - this is the industry-standard
# hosted-checkout handoff instead.)
PAYMENT_LINK_URL: str = os.getenv("PAYMENT_LINK_URL", "").strip()
# ── Carrier tracking API (optional - confirms REAL delivery) ──────
# A tracking aggregator (AfterShip / 17track) key. When set, Printify/Printful
# orders are confirmed delivered by an actual carrier scan instead of the
# timer assumption. Empty = timer-assumption fallback (current behavior).
TRACKING_API_KEY: str = os.getenv("TRACKING_API_KEY", "").strip()
TRACKING_API_PROVIDER: str = os.getenv("TRACKING_API_PROVIDER", "aftership").strip()
# Buyer tax is calculated & collected by Etsy (marketplace facilitator) at checkout
# based on the buyer's location - we do NOT compute it. Optionally show an ESTIMATE
# on-site for transparency; 0 hides it and we just say "tax calculated by Etsy".
ESTIMATED_TAX_RATE_PCT: float = float(os.getenv("ESTIMATED_TAX_RATE_PCT", "0"))
PROMO_WELCOME_CODE: str = os.getenv("PROMO_WELCOME_CODE", "WELCOME10").strip()
PROMO_WELCOME_PCT: int = int(os.getenv("PROMO_WELCOME_PCT", "10"))
# Conservative fallbacks used only when the live variations catalog can't be read
# (e.g. package pricing during a Gelato outage). Chosen to clear the 60% floor.
DEFAULT_LIST_PRICE: float = float(os.getenv("DEFAULT_LIST_PRICE", "49.99"))
DEFAULT_GELATO_COST: float = float(os.getenv("DEFAULT_GELATO_COST", "12.0"))
# Public hosting for customer print files so the print partner (Gelato) can fetch
# them by URL. Preferred: Google Drive (service account). Fallback: a directory
# served at PUBLIC_FILE_BASE_URL (e.g. the web server's /files static route).
PUBLIC_FILE_BASE_URL: str = os.getenv("PUBLIC_FILE_BASE_URL", "").strip().rstrip("/")
PUBLIC_FILE_DIR: str = os.getenv("PUBLIC_FILE_DIR", "").strip()
# Competitor shops to track (comma-separated handles/names). Snapshots are stored
# and diffed for price drops, new listings, and review growth.
COMPETITORS: list[str] = [c.strip() for c in
                          os.getenv("COMPETITORS", "").split(",") if c.strip()]
# Alert when a competitor's lowest price drops by at least this %.
COMPETITOR_PRICE_DROP_ALERT_PCT: float = float(
    os.getenv("COMPETITOR_PRICE_DROP_ALERT_PCT", "10"))
# Per-vendor net-margin floors (JSON). Services/digital can carry higher floors.
# e.g. VENDOR_MARGIN_FLOORS_JSON={"service":80,"digital":90,"printful":55}
VENDOR_MARGIN_FLOORS_JSON: str = os.getenv("VENDOR_MARGIN_FLOORS_JSON", "").strip()

# Other POD vendors (auto-route fulfillment when their key is set).
PRINTFUL_API_KEY: str = os.getenv("PRINTFUL_API_KEY", "").strip()
PRINTIFY_API_KEY: str = os.getenv("PRINTIFY_API_KEY", "").strip()
PRINTIFY_SHOP_ID: str = os.getenv("PRINTIFY_SHOP_ID", "").strip()

# ── Autopilot (autonomous decision bots) ─────────────────────────
# When enabled, bots auto-execute low-risk, high-confidence decisions and only
# escalate to the human-approval queue when money moves, confidence is low, or
# the decision needs judgement. Tune the bar with these knobs.
AUTOPILOT_ENABLED: bool = _env_bool("AUTOPILOT_ENABLED", True)
# Minimum classifier confidence to auto-act (otherwise escalate to a human).
AUTOPILOT_CONFIDENCE_THRESHOLD: float = float(
    os.getenv("AUTOPILOT_CONFIDENCE_THRESHOLD", "0.80"))
# Max money (USD) a bot may commit on its own. 0 = NEVER auto-refund/auto-spend.
AUTOPILOT_MAX_AUTO_REFUND: float = float(os.getenv("AUTOPILOT_MAX_AUTO_REFUND", "0"))
# Orders above this value always go to a human, even for routine decisions.
AUTOPILOT_HIGH_VALUE_ORDER: float = float(
    os.getenv("AUTOPILOT_HIGH_VALUE_ORDER", "150"))
# Use Claude to classify free-text customer issues (falls back to keywords).
AUTOPILOT_USE_LLM: bool = _env_bool("AUTOPILOT_USE_LLM", False)
# Defect/damage reporting window the shop honours (days from delivery). Buyers
# must report with a photo inside this window for a free replacement. Matches the
# published Etsy return policy; keep <= Gelato's own claim window.
POLICY_DEFECT_WINDOW_DAYS: int = int(os.getenv("POLICY_DEFECT_WINDOW_DAYS", "7"))
# Window to report a lost-in-transit package (days from ship/last tracking).
POLICY_LOST_WINDOW_DAYS: int = int(os.getenv("POLICY_LOST_WINDOW_DAYS", "30"))

# Database backup retention (days). Backups older than this are pruned; the most
# recent backup is always kept regardless of age.
BACKUP_RETENTION_DAYS: int = int(os.getenv("BACKUP_RETENTION_DAYS", "3"))

# ── Artwork preflight (print-quality gate before Gelato) ─────────
PREFLIGHT_ENABLED: bool = _env_bool("PREFLIGHT_ENABLED", True)
PREFLIGHT_TARGET_DPI: int = int(os.getenv("PREFLIGHT_TARGET_DPI", "300"))
PREFLIGHT_MIN_DPI: int = int(os.getenv("PREFLIGHT_MIN_DPI", "150"))
# Allowed shortfall vs the product's required pixel dimensions (0.05 = 5%).
PREFLIGHT_DIMENSION_TOLERANCE: float = float(
    os.getenv("PREFLIGHT_DIMENSION_TOLERANCE", "0.05"))
# Allowed aspect-ratio drift vs the product's spec.
PREFLIGHT_ASPECT_TOLERANCE: float = float(
    os.getenv("PREFLIGHT_ASPECT_TOLERANCE", "0.06"))

# ── Customer-supplied photo quality gate ─────────────────────────
# Minimum effective DPI a buyer's own photo must meet for the ordered print
# size. Below this the order is held and an auto-reply asks for a better photo.
# 150 = the Gelato-safe floor (matches PREFLIGHT_MIN_DPI). Was 120, which let
# visibly-soft photos pass and print blurry with no block.
CUSTOMER_PHOTO_MIN_DPI: int = int(os.getenv("CUSTOMER_PHOTO_MIN_DPI", "150"))
# Print-quality SCORE gate (photo_quality.score_photo): a 0-100 score that blends
# resolution, sharpness, noise, compression, exposure + an optional AI pass - so a
# blurry-but-large photo is caught, not just an under-resolution one.
#   score >= PASS   -> proceed
#   REJECT..PASS    -> warn (offer enhancement / "may look soft")
#   score <  REJECT -> reject (ask for a better photo)
PHOTO_QUALITY_PASS: float = float(os.getenv("PHOTO_QUALITY_PASS", "80"))
PHOTO_QUALITY_REJECT: float = float(os.getenv("PHOTO_QUALITY_REJECT", "60"))
# Auto-email the buyer (when their email is known) on a bad photo.
AUTO_EMAIL_CUSTOMER: bool = _env_bool("AUTO_EMAIL_CUSTOMER", True)
# AI-assisted photo enhancement: before bouncing a too-low-res buyer photo, try
# to upscale it to print resolution and re-review it (photo_enhance). The Lanczos
# baseline is free + offline (capped 2x); set an AI super-resolution provider
# (key + URL) for the premium tier (capped 4x). Kill-switch defaults ON.
AI_PHOTO_ENHANCE: bool = _env_bool("AI_PHOTO_ENHANCE", True)
AI_UPSCALE_API_KEY: str = os.getenv("AI_UPSCALE_API_KEY", "")
AI_UPSCALE_API_URL: str = os.getenv("AI_UPSCALE_API_URL", "")
# Which provider the URL+key speak to:
#   "generic"   - a sync endpoint (your own Real-ESRGAN/GFPGAN server) that takes the
#                 image as multipart and returns the upscaled image bytes (or JSON
#                 with an output URL). This is the default.
#   "replicate" - Replicate's async API (Real-ESRGAN). Set AI_UPSCALE_MODEL to the
#                 model version id; URL defaults to https://api.replicate.com/v1/predictions.
AI_UPSCALE_PROVIDER: str = os.getenv("AI_UPSCALE_PROVIDER", "generic").strip().lower()
AI_UPSCALE_MODEL: str = os.getenv("AI_UPSCALE_MODEL", "")

# ── UAT / feedback collection ────────────────────────────────────
# Optional Google Form (or any survey) URL. When set, the UAT shop-home page
# routes its feedback buttons to this form (with the listing + star rating in
# the URL fragment) instead of a mailto link, so responses auto-aggregate to a
# sheet. Leave blank to use the built-in mailto-to-owner feedback.
FEEDBACK_FORM_URL: str = os.getenv("FEEDBACK_FORM_URL", "").strip()

# ── Affiliate "complete the gift" + B2B (off-Etsy, on your own site) ──
# Paste your affiliate links (flowers / gift cards / gifts). Each is shown only
# if set. FTC disclosure is added automatically. These are referral links - you
# earn a commission; do NOT use these on Etsy (Etsy bans off-site links).
AFFILIATE_FLOWERS_URL: str = os.getenv("AFFILIATE_FLOWERS_URL", "").strip()
AFFILIATE_GIFTCARD_URL: str = os.getenv("AFFILIATE_GIFTCARD_URL", "").strip()
AFFILIATE_GIFTS_URL: str = os.getenv("AFFILIATE_GIFTS_URL", "").strip()
# Add ANY number of programs as a JSON dict, e.g.
# AFFILIATE_LINKS_JSON={"1-800-Flowers":"https://...","Amazon":"https://..."}
AFFILIATE_LINKS_JSON: str = os.getenv("AFFILIATE_LINKS_JSON", "").strip()
# Where B2B / wholesale / corporate-gifting inquiries should be sent.
B2B_CONTACT_EMAIL: str = os.getenv("B2B_CONTACT_EMAIL", "").strip()

# ── Off-site backup (Google Drive) ───────────────────────────────
# When true, `backup-all` also uploads the DB snapshot + bundle to Google Drive
# (requires a configured Drive client). Off by default; a no-op without creds.
BACKUP_TO_DRIVE: bool = _env_bool("BACKUP_TO_DRIVE", False)
BACKUP_DRIVE_FOLDER: str = os.getenv("BACKUP_DRIVE_FOLDER", "Joffiels-Backups").strip()

# ── Audience / email capture ─────────────────────────────────────
# Where the email-capture QR code + Linktree + announcement CTA point. Set this
# to your mailing-list signup form (Mailchimp/MailerLite/Google Form/website).
SIGNUP_URL: str = os.getenv("SIGNUP_URL", "").strip()
# Optional public Linktree/landing URL to print on inserts.
LINKTREE_URL: str = os.getenv("LINKTREE_URL", "").strip()

# ── Pinterest auto-publish (optional) ────────────────────────────
# With a Pinterest API token + board id, scheduled pin packs are posted
# automatically. Without them, `pinterest-publish` stays a dry-run (it still
# generates the images + pins.csv for manual upload). No-op safe default.
PINTEREST_ACCESS_TOKEN: str = os.getenv("PINTEREST_ACCESS_TOKEN", "").strip()
PINTEREST_BOARD_ID: str = os.getenv("PINTEREST_BOARD_ID", "").strip()
PINTEREST_AUTOPILOT: bool = _env_bool("PINTEREST_AUTOPILOT", False)

# ── Web analytics (injected into the GitHub Pages shop-home page) ─
# Both are no-ops when blank. Etsy Shop Stats needs no code (enable in Etsy).
GA_MEASUREMENT_ID: str = os.getenv("GA_MEASUREMENT_ID", "").strip()   # e.g. G-XXXXXXX
CLARITY_PROJECT_ID: str = os.getenv("CLARITY_PROJECT_ID", "").strip()  # Microsoft Clarity

# ── Error monitoring (optional) ──────────────────────────────────
# Set a Sentry DSN to capture unhandled errors in the webhook server + admin.
# No-op (zero overhead) when blank. Install `sentry-sdk` to enable.
SENTRY_DSN: str = os.getenv("SENTRY_DSN", "").strip()

# Optional public URL of the webhook server's /ask endpoint. When set, the
# on-page "Ask Ange" widget calls it for full Claude answers; otherwise it uses
# the built-in knowledge base (no API key is ever exposed on the static site).
ASK_ANGE_API_URL: str = os.getenv("ASK_ANGE_API_URL", "").strip()

# Cost-of-ownership inputs (used by the `tco` command)
USE_MAKE_COM: bool = _env_bool("USE_MAKE_COM", True)   # $9/mo automation
MAKE_COM_COST: float = float(os.getenv("MAKE_COM_COST", "9.0"))
ANTHROPIC_COST_PER_ORDER: float = float(os.getenv("ANTHROPIC_COST_PER_ORDER", "0.02"))
# Fixed monthly overhead for the general ledger (tooling/subscriptions you pay).
# The ledger prorates this across days. Make.com (if used) is added automatically.
MONTHLY_FIXED_COSTS: float = float(os.getenv("MONTHLY_FIXED_COSTS", "0"))
# Turnaround for the "order by" gift-deadline banner.
PRODUCTION_DAYS: int = int(os.getenv("PRODUCTION_DAYS", "3"))
SHIPPING_DAYS: int = int(os.getenv("SHIPPING_DAYS", "6"))
# Optional homepage hero image (a lifestyle/sample photo). Falls back to banner.
HERO_IMAGE: str = os.getenv("HERO_IMAGE", "").strip()
ETSY_LISTING_RENEWAL_PER_MONTH: float = 0.20 / 4   # $0.20 every 4 months

# Phase 12: All Gelato product sizes at 300 DPI (width_px, height_px)
PRODUCTS: dict[str, dict] = {
    # Posters
    "Poster 18x24 in": {"size": (5400, 7200), "gelato_sku": "poster_18x24", "profit": "medium"},
    "Poster 24x36 in": {"size": (7200, 10800), "gelato_sku": "poster_24x36", "profit": "medium"},
    # Canvas — higher profit
    "Canvas 16x20 in": {"size": (4800, 6000), "gelato_sku": "canvas_16x20", "profit": "high"},
    "Canvas 18x24 in": {"size": (5400, 7200), "gelato_sku": "canvas_18x24", "profit": "high"},
    # Framed prints — higher profit
    "Framed 11x14 in": {"size": (3300, 4200), "gelato_sku": "framed_11x14", "profit": "high"},
    "Framed 16x20 in": {"size": (4800, 6000), "gelato_sku": "framed_16x20", "profit": "high"},
    # Acrylic — premium
    "Acrylic 12x16 in": {"size": (3600, 4800), "gelato_sku": "acrylic_12x16", "profit": "premium"},
    "Acrylic 16x20 in": {"size": (4800, 6000), "gelato_sku": "acrylic_16x20", "profit": "premium"},
    # Metal — premium
    "Metal 12x16 in": {"size": (3600, 4800), "gelato_sku": "metal_12x16", "profit": "premium"},
    "Metal 16x20 in": {"size": (4800, 6000), "gelato_sku": "metal_16x20", "profit": "premium"},
    # Square / social
    "Square 12x12 in": {"size": (3600, 3600), "gelato_sku": "poster_12x12", "profit": "medium"},
}

# Airtable
AIRTABLE_API_KEY: str = os.getenv("AIRTABLE_API_KEY", "")
AIRTABLE_BASE_ID: str = os.getenv("AIRTABLE_BASE_ID", "")

# Gelato API (for programmatic order creation)
GELATO_API_KEY: str = os.getenv("GELATO_API_KEY", "")
GELATO_BASE_URL: str = os.getenv("GELATO_BASE_URL", "https://order.gelatoapis.com")
# Gelato ECOMMERCE API (connected store) — used to auto-pull official product mockup
# images (previewUrl) once the owner creates a product. GELATO_STORE_ID is the
# connected store's UUID (empty = the ecommerce image sync stays a safe no-op).
GELATO_ECOMMERCE_URL: str = os.getenv(
    "GELATO_ECOMMERCE_URL", "https://ecommerce.gelatoapis.com").rstrip("/")
GELATO_STORE_ID: str = os.getenv("GELATO_STORE_ID", "").strip()
# Gelato Order API version (current = v4; v3 is the older API). v4 additionally
# requires orderType + shipmentMethodUid on create.
GELATO_API_VERSION: str = os.getenv("GELATO_API_VERSION", "v4").strip().lower()
# Shipping method submitted to Gelato. "normal" = standard; a comma list (e.g.
# "normal,express") tells Gelato to pick the CHEAPEST of those. The buyer already
# paid Etsy shipping; this is what Gelato uses to fulfil + what it charges you.
GELATO_SHIPMENT_METHOD: str = os.getenv("GELATO_SHIPMENT_METHOD", "normal").strip()

# Express delivery — a PAID, per-order upgrade the customer can choose at design time.
# OFF by default: until EXPRESS_SHIPPING_ENABLED is true the storefront never offers it
# and nothing changes. When enabled, the buyer can pick Express for EXPRESS_SHIPPING_UPCHARGE
# (USD, on top of standard shipping) and the order is sent to Gelato with
# EXPRESS_SHIPMENT_METHOD instead of the normal method. Set the upcharge from your Gelato
# account's express rate so it covers the express cost difference + margin. Confirm Gelato
# offers express for your products/destinations before enabling.
EXPRESS_SHIPPING_ENABLED: bool = _env_bool("EXPRESS_SHIPPING_ENABLED", False)
EXPRESS_SHIPPING_UPCHARGE: float = float(os.getenv("EXPRESS_SHIPPING_UPCHARGE", "9.95"))
EXPRESS_SHIPMENT_METHOD: str = os.getenv("EXPRESS_SHIPMENT_METHOD", "express").strip()
EXPRESS_SHIPPING_DAYS: int = int(os.getenv("EXPRESS_SHIPPING_DAYS", "3"))

# Shipping COST model — high-end US estimates per product TYPE + a SAFETY MARGIN, so a
# shipping figure baked into the price (or charged) never loses money. Gelato's exact
# rate varies by product/size/destination/hub and changes regularly, so we take the
# HIGH end + margin; the shipping-rate monitor re-checks and flags drift/staleness.
SHIPPING_MARGIN_PCT: float = float(os.getenv("SHIPPING_MARGIN_PCT", "5"))        # +5% margin
ADDITIONAL_ITEM_SHIP_FACTOR: float = float(os.getenv("ADDITIONAL_ITEM_SHIP_FACTOR", "0.75"))
EXPRESS_SHIP_MULT: float = float(os.getenv("EXPRESS_SHIP_MULT", "1.6"))          # express ≈ +60%
SHIPPING_COST_TABLE_JSON: str = os.getenv("SHIPPING_COST_TABLE_JSON", "").strip()  # owner override
SHIPPING_RATES_REVIEW_DAYS: int = int(os.getenv("SHIPPING_RATES_REVIEW_DAYS", "30"))
# Free-shipping strategy: bake the shipping cost INTO the displayed item price and present
# "Free shipping" (Etsy boosts free-shipping listings; US free-shipping guarantee at $35+).
# OFF by default and it MUST stay off until the Etsy listings themselves are set to free
# shipping - otherwise the buyer pays shipping TWICE (baked into the price here AND Etsy's
# checkout shipping). When ON, the storefront shows landed prices (item + high-end shipping
# + margin, via shipping_costs.landed_price) and the copy reads "Free shipping".
FREE_SHIPPING_BAKED: bool = _env_bool("FREE_SHIPPING_BAKED", False)

# Apparel MULTI-AREA printing (back + sleeves, beyond the front). The print partner does
# DTG on front/back/sleeves; each EXTRA area adds an upcharge that clears the shop margin
# PLUS EXTRA_PRINT_MARGIN_PCT, AFTER marketplace fees - so an extra area is always
# profitable, never a loss (apparel_print_costs.extra_print_upcharge). ON by default so
# the storefront editor offers back/sleeves and the daily rebuild keeps it live. This is
# SAFE even before the automatic per-area artwork submission is wired: the router
# UNCONDITIONALLY holds any back/sleeve order for manual two-sided production, so nothing
# ever prints front-only. Per-area COSTS are high-end estimates (the partner's per-area
# surcharge isn't public - read the real number off the partner's editor and override
# here); the high-end + the margin give double loss-protection. Set =false to hide it.
APPAREL_MULTI_AREA_ENABLED: bool = _env_bool("APPAREL_MULTI_AREA_ENABLED", True)
EXTRA_PRINT_MARGIN_PCT: float = float(os.getenv("EXTRA_PRINT_MARGIN_PCT", "10"))   # +10% over base
BACK_PRINT_COST: float = float(os.getenv("BACK_PRINT_COST", "6.00"))              # high-end est.
SLEEVE_PRINT_COST: float = float(os.getenv("SLEEVE_PRINT_COST", "4.00"))          # high-end est.
# WHO submits orders to Gelato - exactly one source may, or orders double-print +
# double-charge. "quoteforge" (DEFAULT): QuoteForge is the personalization engine - it
# GENERATES the artwork (AI quote -> template -> layout -> 300 DPI render) and submits
# it to Gelato with that artwork URL. This is the product's purpose; Gelato's native
# Etsy integration can't render personalized art, so it must NOT be connected (it would
# print the static listing image AND duplicate). "native": for a seller who is NOT
# using QuoteForge's artwork - Gelato fulfils via its Etsy integration and QuoteForge
# only records/analyses/tracks. With "quoteforge", DO NOT also connect Gelato's native
# Etsy app, or every order is submitted twice.
GELATO_FULFILLMENT_MODE: str = os.getenv("GELATO_FULFILLMENT_MODE", "quoteforge").strip().lower()

# Auto-send TRANSACTIONAL lifecycle updates ("Order Received", "In Production") to the
# buyer by email. OFF by default: the marketplace already sends an order confirmation,
# and these are a personal touch the marketplace doesn't (the shipped+tracking notice
# and the post-delivery review ask are already automatic regardless of this flag).
CUSTOMER_AUTO_NOTIFY: bool = os.getenv("CUSTOMER_AUTO_NOTIFY", "false").strip().lower() in ("1", "true", "yes")

# Google Drive (for artwork storage)
GOOGLE_DRIVE_FOLDER_ID: str = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
GOOGLE_SERVICE_ACCOUNT_FILE: str = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "")

# Canva API
CANVA_API_KEY: str = os.getenv("CANVA_API_KEY", "")
CANVA_BRAND_TEMPLATE_ID: str = os.getenv("CANVA_BRAND_TEMPLATE_ID", "")

# Etsy API (for webhook verification + order pulling)
# Your Etsy shop / brand name — used in customer messages and report headers.
SHOP_NAME: str = os.getenv("SHOP_NAME", "Joffiels")
ETSY_SHOP_ID: str = os.getenv("ETSY_SHOP_ID", "")
ETSY_API_KEY: str = os.getenv("ETSY_API_KEY", "")
# OAuth token for authorized shop access (orders + fulfillment). From the Etsy
# OAuth flow; refresh token lets the poller renew it without re-auth.
ETSY_OAUTH_TOKEN: str = os.getenv("ETSY_OAUTH_TOKEN", "")
ETSY_REFRESH_TOKEN: str = os.getenv("ETSY_REFRESH_TOKEN", "")
ETSY_API_BASE: str = os.getenv("ETSY_API_BASE", "https://openapi.etsy.com/v3")
# Required to auto-create listings via the Etsy API (from your shop):
#   taxonomy id for wall-art prints, your shipping profile id, default price.
ETSY_TAXONOMY_ID: str = os.getenv("ETSY_TAXONOMY_ID", "")
ETSY_SHIPPING_PROFILE_ID: str = os.getenv("ETSY_SHIPPING_PROFILE_ID", "")
ETSY_DEFAULT_LISTING_PRICE: float = float(
    os.getenv("ETSY_DEFAULT_LISTING_PRICE", "36.99"))
ETSY_WEBHOOK_SECRET: str = os.getenv("ETSY_WEBHOOK_SECRET", "")
# Shared secret Gelato signs its status/tracking callbacks with (set the same
# value in the Gelato dashboard webhook config). Empty = verification disabled.
GELATO_WEBHOOK_SECRET: str = os.getenv("GELATO_WEBHOOK_SECRET", "")

# Pipeline settings
PIPELINE_AUTO_APPROVE_PROOF: bool = _env_bool("PIPELINE_AUTO_APPROVE_PROOF", False)
# When true, the proof step is treated as CUSTOMER approval: the pipeline
# prepares a proof message + image for you to send the buyer via Etsy, and
# printing is blocked until you record the customer's approval.
CUSTOMER_PROOF_APPROVAL: bool = _env_bool("CUSTOMER_PROOF_APPROVAL", True)
PIPELINE_REVIEW_DELAY_DAYS: int = int(os.getenv("PIPELINE_REVIEW_DELAY_DAYS", "14"))
PIPELINE_UPSELL_DELAY_HOURS: int = int(os.getenv("PIPELINE_UPSELL_DELAY_HOURS", "2"))

# Financial defaults — used to estimate per-order economics when the actual
# sale price / print cost aren't recorded on the order yet (e.g. before the
# Etsy + Gelato APIs feed real numbers). Override per env.
DEFAULT_SALE_PRICE: float = float(os.getenv("DEFAULT_SALE_PRICE", "36.99"))
DEFAULT_GELATO_COST: float = float(os.getenv("DEFAULT_GELATO_COST", "11.00"))
# Average sales-tax rate Etsy COLLECTS and REMITS on your behalf (pass-through —
# not your money, not a cost). Shown for reference/reconciliation only.
ESTIMATED_SALES_TAX_RATE: float = float(os.getenv("ESTIMATED_SALES_TAX_RATE", "0.07"))

# Daily report email (Gmail SMTP). Create an App Password at
# myaccount.google.com -> Security -> App passwords (requires 2FA).
GMAIL_ADDRESS: str = os.getenv("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD: str = os.getenv("GMAIL_APP_PASSWORD", "")
REPORT_RECIPIENT: str = os.getenv("REPORT_RECIPIENT", "joffielsc@gmail.com")
# Where the owner's per-order notices go: an INVOICE copy when an order is placed and a
# SHIPPED + tracking copy when it ships. Defaults to the owner report inbox.
ORDER_NOTIFY_EMAIL: str = os.getenv("ORDER_NOTIFY_EMAIL", REPORT_RECIPIENT)

# Wave accounting API (https://gql.waveapps.com/graphql/public). Create a Full-Access
# token in Wave -> Settings -> (Developer/API). Personal tokens need no Wave Pro plan.
# Run `admin wave-test` to verify the token and list your business + account IDs, then
# fill the account IDs below and `admin wave-sync` to push per-order Etsy payouts.
WAVE_API_TOKEN: str = os.getenv("WAVE_API_TOKEN", "")
WAVE_BUSINESS_ID: str = os.getenv("WAVE_BUSINESS_ID", "")
# Account IDs (from `wave-test`): the anchor bank/clearing account money lands in, and
# the income/expense categories. Leave blank until you've created/identified them.
WAVE_ACCT_BANK: str = os.getenv("WAVE_ACCT_BANK", "")        # anchor (Cash/Bank/Clearing)
WAVE_ACCT_SALES: str = os.getenv("WAVE_ACCT_SALES", "")      # Sales income
WAVE_ACCT_SHIPPING: str = os.getenv("WAVE_ACCT_SHIPPING", "")  # Shipping income (optional)
WAVE_ACCT_FEES: str = os.getenv("WAVE_ACCT_FEES", "")        # Etsy/selling fees expense
WAVE_ACCT_COGS: str = os.getenv("WAVE_ACCT_COGS", "")        # Gelato print + shipping (COGS)
WAVE_ACCT_INFRA: str = os.getenv("WAVE_ACCT_INFRA", "")      # Software/AI/hosting expense
WAVE_ACCT_TAX: str = os.getenv("WAVE_ACCT_TAX", "")          # Sales Tax Payable (liability)
# Flip ON only after a clean `wave-sync month` dry-run: the daily job then pushes
# transactions to Wave automatically (otherwise it just emails the dry-run review).
WAVE_AUTO_SYNC: bool = _env_bool("WAVE_AUTO_SYNC", False)

# Phase 1 priority niches to validate first (20-30 manual listings)
PHASE1_NICHES: list[str] = [
    "Personalized Daughter Gifts",
    "Personalized Son Gifts",
    "Christian Encouragement",
    "Graduation Gifts",
    "Memorial Gifts",
    "Future Dentist Gifts",
    "Custom Love Letters",
    "Personalized Mom Gifts",
]

# Phase 14 bulk catalog: 8 core relationships × quote batches = 800+ listings
BULK_CATALOG_RELATIONSHIPS: list[str] = [
    "Daughter", "Son", "Wife", "Husband", "Mom", "Dad", "Friend", "Graduation",
]
