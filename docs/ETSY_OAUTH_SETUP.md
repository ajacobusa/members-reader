# Etsy API / OAuth Setup — enable auto-publishing, polling & tracking

Set these up once to unlock the automated paths: `publish-listings --live`
(create the 20 draft listings), `poll-etsy` (auto-import orders), and automatic
tracking push back to Etsy. All optional — the shop works without them; this just
removes manual steps.

## 1. Register an Etsy app (get the API key)
1. Go to **etsy.com/developers** → **Manage Apps** → **Create a New App**.
2. Name it "Joffiels Automation", agree to terms.
3. Copy the **Keystring** → this is your `ETSY_API_KEY`.

```env
ETSY_API_KEY=your_keystring
```

## 2. Get an OAuth token (scopes: listings_w, listings_r, transactions_r)
Etsy uses OAuth 2.0 (PKCE). Easiest path:
- In your app settings, set a **Redirect URI** (e.g. `http://localhost/callback`).
- Use Etsy's OAuth flow (their docs: "Authorization Code Grant") to get an
  **access token** and **refresh token** with these scopes:
  `listings_r listings_w transactions_r`.
- Tools that simplify this: Postman's OAuth2 helper, or a tiny local script
  (ask and I'll generate one).

```env
ETSY_OAUTH_TOKEN=your_access_token
ETSY_REFRESH_TOKEN=your_refresh_token
```

## 3. Your shop ID
- Call `GET /v3/application/users/me` (with the token) → it returns your
  `shop_id`, or find it in your shop URL / Shop Manager.

```env
ETSY_SHOP_ID=your_numeric_shop_id
```

## 4. Taxonomy + shipping profile (needed to CREATE listings)
- **Taxonomy id** (the category): call
  `GET /v3/application/seller-taxonomy/nodes` and find "Wall Decor → Posters &
  Prints" (or the closest). Use that node's `id`.
- **Shipping profile id**: create a shipping profile in Etsy (Settings →
  Shipping), then `GET /v3/application/shops/{shop_id}/shipping-profiles` to read
  its id.

```env
ETSY_TAXONOMY_ID=the_node_id
ETSY_SHIPPING_PROFILE_ID=your_profile_id
ETSY_DEFAULT_LISTING_PRICE=36.99
```

## 5. Verify + go
```bash
python -m quoteforge.admin publish-listings          # dry-run; should show no
                                                     # missing prerequisites
python -m quoteforge.admin publish-listings --live   # creates 20 DRAFT listings
                                                     # + uploads images
```
Drafts are **not** auto-published — review each in Etsy, then click **Publish**.

> Note for brand-new shops: Etsy sometimes limits API listing creation until the
> shop has some history. If `--live` is rejected, use the manual `launch_kit/`
> upload for the first batch, then switch to automation once established.
