# QuoteForge VA Order Fulfillment SOP
**Version:** 1.0 | **Updated:** 2026-06-03

## Overview
This SOP covers the complete process for fulfilling a personalized wall art order on Etsy using QuoteForge and Gelato.

**Time per order:** 12-15 minutes
**Tools needed:** QuoteForge app, Canva (free or Pro), Gelato account, Etsy seller account

---

## Step 1: Receive & Record the Order (2 min)

1. Log into Etsy Seller Hub
2. Go to Orders & Shipping
3. Click the new order
4. Find the personalization box answers from the customer
5. Open `QuoteForge_Order_Tracker.xlsx` on Desktop
6. Add a new row with:
   - Order ID (from Etsy)
   - Customer Name
   - Recipient Name
   - Occasion
   - Scenery preference
   - Set Quote Status → Pending

---

## Step 2: Generate the Custom Quote (2 min)

1. Open QuoteForge app (double-click `QuoteForge.bat`)
2. Click **Order Processor** tab
3. Fill in ALL fields from the customer's personalization:
   - Recipient Name
   - Your Name (sender)
   - Relationship
   - Occasion
   - Scenery
   - Message Tone
   - Special Memory (paste exactly what customer wrote)
4. Click **✦ Generate Message**
5. Read all 3 variations
6. Choose the best one
7. Update tracker: Quote Status → Generated

---

## Step 3: Create Design in Canva (5-8 min)

1. Open Canva
2. Go to your template library (search by scenery type)
3. Select the template matching the customer's scenery choice
4. Click the text box labeled "QUOTE"
5. Paste the generated quote text
6. Adjust font size so text fills the box cleanly (aim for 70-80% of box)
7. Verify:
   - [ ] Text is fully readable (no overflow)
   - [ ] Recipient name is correct
   - [ ] No spelling errors
8. Click Share → Download
   - File type: PNG
   - Size: 300 DPI (enable "High Quality" if available)
9. Save to `Desktop/QuoteForge-Output/Designs/[OrderID].png`
10. Update tracker: Design Status → Done

---

## Step 4: Upload to Gelato (2 min)

1. Log into gelato.com
2. Go to Orders (left sidebar)
3. Find the pending order matching this Etsy order
4. Click the order → Upload Design
5. Upload the PNG from Step 3
6. Wait for mockup preview to generate
7. Verify:
   - [ ] Design is properly centered
   - [ ] Text is readable in mockup
   - [ ] No white borders or cropping issues
8. Click **Approve**
9. Update tracker: Gelato Upload → Uploaded

---

## Step 5: Customer Communication (1 min)

1. In QuoteForge → **Prompts & Messages** tab → **Customer Messages**
2. Select: **Order Shipped** (after Gelato confirms production start)
3. Fill in: Customer Name, Occasion, Recipient Name
4. Click **AI Personalize Message**
5. Copy the output
6. In Etsy: Go to the order → Message Buyer → Paste and send

---

## Step 6: Review Request (send 7 days after ship date)

1. In QuoteForge → **Prompts & Messages** → **Customer Messages**
2. Select: **Review Request**
3. AI Personalize → Copy → Send via Etsy

---

## Quality Checklist (before every Gelato upload)
- [ ] Recipient name spelled correctly
- [ ] Quote text is emotionally appropriate for the occasion
- [ ] Scenery matches what customer requested
- [ ] No typos visible in the design
- [ ] File resolution is 300 DPI
- [ ] Image dimensions match product (18x24 for poster, etc.)

---

## Escalate to Owner When:
- Customer is unhappy with proof
- Order needs rush processing (< 24 hours)
- Gelato shows an error on upload
- Customer requests a full refund
