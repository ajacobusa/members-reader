# Joffiels / QuoteForge — Complete Capability & Use-Case Reference

Every command, grouped by what you're trying to do. Run any with
`python -m quoteforge.admin <command>`. **52 commands total.**

---

## 🚀 Launch the shop (do these, in order)
| Use case | Command |
|---|---|
| Verify API keys + Gelato UID mappings | `verify-keys` |
| Go-live readiness checks | `preflight` |
| Preview real AI quotes (judge quality) | `sample-quote` · `sample-batch` |
| The 20 starter listings + scaling phases | `launch` · `launch scale N` |
| Build ALL 20 ready-to-upload packages (SEO+design+5 images) | `launch-kit` |
| Plan the storefront sections + assignments | `shop-plan` |
| Custom-quote / photo listing copy + FAQ | `custom-copy` |
| Auto-create the 20 Etsy DRAFT listings + images | `publish-listings [--live]` |
| Register all scheduled jobs (run as admin) | `install-schedule` |

## 🎨 Create artwork & listing media
| Use case | Command |
|---|---|
| Styled-room lifestyle mockup from a poster | `mockup POSTER.png` |
| 5-image Etsy gallery pack from a design | `listing-pack POSTER.png` |
| Short premium MP4 listing video (Etsy ranks it higher) | `listing-video IMAGE.png` |
| Artwork print-quality check (DPI/size/mode) | `preflight-art ART.png [size]` |
| Edge-case artwork QA (long names, all sizes) | `artwork-qa` |

## 🔎 SEO & getting found
| Use case | Command |
|---|---|
| Per-listing SEO (title+13 tags+desc), all fields/relationships | `seo [N|export|prof NAME|rel REL OCC|professions]` |
| Demand-driven seasonal SEO (refresh 4wks out, last-minute 1wk) | `seasonal-seo` |
| Seasonal campaign plan + publish-by dates | `campaign [Month]` |
| Which occasions to create listings for now | `plan` |
| Annual marketing calendar (list/market dates) | `calendar` |

## 📈 Grow the business
| Use case | Command |
|---|---|
| Repeat-gift outreach, cross-sell, win-backs (LTV) | `retention` |
| Reviews + referrals post-delivery (delight loop) | `delight` |
| What to scale / retire / demand gaps (from sales) | `growth` |
| Today's upsell / review / win-back actions | `sales` |
| High-ticket gallery-set bundles ($180-500) | `bundles [occasion]` |
| Bulk-build the next N listings to scale | `build-batch N [--art]` |
| Full product range + 1-story-to-many cross-sell | `products [occasion]` |
| Margin-floor audit (>=60%) | `margins [floor%]` |
| Total cost of ownership | `tco [listings] [orders/mo]` |

## 🛒 Orders & customer service (mostly automated)
| Use case | Command |
|---|---|
| Pull new paid Etsy orders (no Make/Zapier) | `poll-etsy` |
| Show the proof message to send a buyer | `show-proof ID` |
| Buyer approved -> release to print | `customer-approved ID` |
| Autopilot a customer issue (auto-act or escalate) | `autopilot "<issue>" [ID]` |
| Your approval queue (refunds always here) | `approvals [approve|reject ID]` |
| Decide a return/refund issue + draft reply | `resolve <issue> [ID]` |
| Etsy + Gelato policy facts per issue | `policy [issue]` |
| Check a buyer photo's print quality | `check-photo PHOTO [size]` |
| Resume a held order with a corrected photo | `fix-photo ID PHOTO` |

## 💰 Money & reporting
| Use case | Command |
|---|---|
| One consolidated daily ops read | `briefing [email]` |
| Daily / weekly / monthly / yearly sales report | `report PERIOD [email]` |
| Email the daily report now | `email-report` |
| Detailed API (Claude) spend | `costs [today|week|month]` |
| Monthly bookkeeping Excel | `reconcile [YYYY-MM]` |

## 🛡️ Ops, health & backup (mostly scheduled)
| Use case | Command |
|---|---|
| Self-healing maintenance agent | `maintenance [email|--check]` |
| Health check (DB/storage/jobs) | `healthcheck [email]` |
| Database snapshot (3-day retention) | `backup` |
| FULL backup: DB + commit + push to GitHub + bundle | `backup-all` |
| List / restore DB backups | `list-backups` · `restore [PATH]` |
| Setup reminders (shown in the daily briefing) | `remind [add "x"|done N]` |
| Generate a webhook signing secret | `gen-secret` |

---

## The two paths to publish the 20 listings
1. **Manual / VA:** open `QuoteForge-Output/launch_kit/`, follow
   `UPLOAD_CHECKLIST.txt` - paste each `seo.txt`, upload the `gallery/` images.
2. **Automated:** set up Etsy OAuth (see `ETSY_OAUTH_SETUP.md`), then
   `publish-listings --live` creates all 20 drafts + uploads images. Review +
   publish each in Etsy.

## What still requires YOU (cannot be automated)
- Approving the **physical sample** print quality (the launch gate).
- Flipping `TEST_MODE=false` after the sample is approved.
- A friendly **seller photo** for the About page (builds trust).
- Final **Publish** click on each Etsy draft.
- Refund decisions (autopilot always escalates money-back to you).
