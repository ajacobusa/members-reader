# Production Migration Tracker

_Auto-generated 2026-06-08T00:23:24.125380. Running locally for UAT; this lists what to change when moving to the permanent server._

**Ready for production:** NO - 4 required item(s) remaining.

## Required before go-live

- [ ] **TEST_MODE** (now: `True`) - Set TEST_MODE=false on the server so real Etsy/Gelato/Claude calls run.
- [ ] **Print-file hosting** (now: `local file:// only (not fetchable by Gelato - set Drive or PUBLIC_FILE_DIR before go-live)`) - Set Google Drive (GOOGLE_DRIVE_FOLDER_ID + GOOGLE_SERVICE_ACCOUNT_FILE) or PUBLIC_FILE_DIR + PUBLIC_FILE_BASE_URL so uploaded JPGs are fetchable.
- [ ] **Server API URL (ASK_ANGE_API_URL)** (now: `(not set - widgets degrade gracefully)`) - Host the webhook server (Render/own box) and set ASK_ANGE_API_URL to its /ask URL so Ask Ange, signup, photo upload, and A/B all work live.
- [ ] **Etsy (ETSY_API_KEY)** (now: `missing`) - Set ETSY_API_KEY + token for order polling, tracking push, competitor pulls.

## Full environment state

| Setting | Status | Current | Production action |
|---|---|---|---|
| TEST_MODE | todo | True | Set TEST_MODE=false on the server so real Etsy/Gelato/Claude calls run. |
| Print-file hosting | todo | local file:// only (not fetchable by Gelato - set Drive or PUBLIC_FILE_DIR before go-live) | Set Google Drive (GOOGLE_DRIVE_FOLDER_ID + GOOGLE_SERVICE_ACCOUNT_FILE) or PUBLIC_FILE_DIR + PUBLIC_FILE_BASE_URL so uploaded JPGs are fetchable. |
| Server API URL (ASK_ANGE_API_URL) | todo | (not set - widgets degrade gracefully) | Host the webhook server (Render/own box) and set ASK_ANGE_API_URL to its /ask URL so Ask Ange, signup, photo upload, and A/B all work live. |
| Claude API (ANTHROPIC_API_KEY) | ready | set | Set ANTHROPIC_API_KEY for AI quote/vision/quality features. |
| Gelato (GELATO_API_KEY) | ready | set | Set GELATO_API_KEY to place real print orders. |
| Etsy (ETSY_API_KEY) | todo | missing | Set ETSY_API_KEY + token for order polling, tracking push, competitor pulls. |
| Report recipient | ready | ajacobusa@gmail.com | Confirm REPORT_RECIPIENT is your email for daily/Friday reports. |
| Google Analytics (GA_MEASUREMENT_ID) | optional | (unset) | Optional: set for GA traffic stats. |
| Clarity (CLARITY_PROJECT_ID/API) | optional | (unset) | Optional: set CLARITY_PROJECT_ID + CLARITY_API_TOKEN for heatmaps/rage clicks. |
| Pinterest (PINTEREST_ACCESS_TOKEN) | optional | (unset) | Optional: set to auto-publish pins + enrich trend predictions. |
| Competitors tracked | optional | (none) | Optional: set COMPETITORS to track rival prices/listings. |
| Output dir | ready | C:\Users\anoop\Desktop\QuoteForge-Output | On the server, point OUTPUT_DIR at persistent storage (not ephemeral). |

## Move-to-server steps (summary)

1. Provision the permanent server (Render/own box); deploy the webhook server (see docs/DEPLOY.md).
2. Set the env vars flagged TODO above.
3. Point OUTPUT_DIR at persistent storage; restore the latest DB backup.
4. Set ASK_ANGE_API_URL to the live server `/ask` URL and rebuild the site so the storefront talks to production.
5. Install the scheduled jobs on the server (`admin install-schedule`).
6. Run `admin deploy-status` and `admin healthcheck` to confirm green.
