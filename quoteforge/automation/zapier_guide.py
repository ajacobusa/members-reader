"""Setup guides for Zapier and Make.com automation."""

ZAPIER_SETUP = """
ZAPIER AUTOMATION SETUP — QuoteForge Webhook
=============================================

Step 1: Start QuoteForge Webhook Server
  - Open Command Prompt
  - Run: python -m quoteforge.automation.webhook_server
  - Note your IP address (run: ipconfig)
  - Server runs at: http://YOUR-IP:5050

Step 2: Expose Server to Internet (for Zapier)
  Option A: ngrok (free, easiest)
    - Download ngrok.com
    - Run: ngrok http 5050
    - Copy the https://xxx.ngrok.io URL

  Option B: Port forward your router
    - Forward port 5050 to your PC's local IP

Step 3: Create Zapier Workflow
  Trigger: "New Order" in Etsy (Etsy app in Zapier)
  Action: "Webhooks by Zapier" → POST
  URL: https://your-ngrok-url/order
  Payload (JSON):
    {
      "customer_name": {{customer_name}},
      "recipient_name": {{personalization_recipient_name}},
      "relationship": {{personalization_relationship}},
      "occasion": {{personalization_occasion}},
      "scenery": {{personalization_scenery}},
      "memory": {{personalization_special_memory}},
      "output_style": "Personal Letter",
      "order_id": {{order_id}}
    }

Step 4: Test
  - Place a test order on your Etsy shop
  - Check Desktop/QuoteForge-Output/Orders/ for generated text file
  - Check Desktop/QuoteForge-Output/webhook_log.json for log

Make.com Alternative:
  Same steps — use "HTTP" module instead of Webhooks
  Trigger: Etsy → Watch Orders
  Module: HTTP → Make a Request → POST to /order
"""

MAKE_SETUP = """
MAKE.COM (formerly Integromat) SETUP
=====================================

1. Create scenario: Etsy → HTTP
2. Etsy module: Watch Orders (new orders)
3. HTTP module: Make a Request
   - URL: http://YOUR-IP:5050/order (or ngrok URL)
   - Method: POST
   - Body type: Raw
   - Content type: application/json
   - Body: map Etsy personalization fields to JSON

Full automation flow:
Etsy Order → Make.com → QuoteForge Webhook → Quote Generated
         → Saved to Desktop → You open file → Paste into Canva
         → Upload PNG to Gelato → Gelato ships to customer
"""

VA_WORKFLOW_INSTRUCTIONS = """
VIRTUAL ASSISTANT WORKFLOW — QuoteForge Order Fulfillment
==========================================================

When an order comes in, the VA should:

1. RECEIVE ORDER
   - Check Etsy messages/orders dashboard
   - Copy all personalization field answers

2. GENERATE QUOTE (2 minutes)
   - Open QuoteForge app
   - Click "Order Processor" tab
   - Paste: Recipient Name, Sender Name, Occasion, Relationship, Scenery, Memory
   - Click "Generate Message"
   - Copy the best variation

3. CREATE DESIGN IN CANVA (5-8 minutes)
   - Open Canva
   - Select correct template (match scenery to customer request)
   - Paste the generated quote text
   - Adjust font size if needed (text must fit and be readable)
   - Export as PNG (300 DPI)

4. UPLOAD TO GELATO (2 minutes)
   - Log into gelato.com
   - Go to customer's pending order
   - Upload the PNG file
   - Verify mockup looks correct
   - Click Approve

5. UPDATE TRACKER (1 minute)
   - Open QuoteForge_Order_Tracker.xlsx
   - Find the order row
   - Update: Design Status → Done, Gelato Upload → Uploaded

6. SEND CUSTOMER MESSAGE (1 minute)
   - In QuoteForge → Prompts & Messages → Customer Messages
   - Select "Order Shipped"
   - Fill in customer name and occasion
   - Copy and paste into Etsy message thread

Total per order: ~12-15 minutes
"""
