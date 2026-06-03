# QuoteForge Setup Guide

## Step 1: Install Python
Download from https://python.org — choose Python 3.10 or higher.
During install, check "Add Python to PATH".

## Step 2: Get Your API Keys

### Anthropic (Claude API)
1. Go to https://console.anthropic.com
2. Click API Keys → Create Key
3. Copy the key (starts with sk-ant-)

### Unsplash
1. Go to https://unsplash.com/developers
2. Click New Application → fill in details
3. Copy your Access Key

### Bannerbear
1. Go to https://bannerbear.com
2. Settings → API Key → copy it

## Step 3: Enter Your API Keys
Open `quoteforge/config.py` in Notepad and paste your keys:
```
ANTHROPIC_API_KEY = "sk-ant-your-key-here"
UNSPLASH_ACCESS_KEY = "your-unsplash-key"
BANNERBEAR_API_KEY = "your-bannerbear-key"
```

## Step 4: Create Your Bannerbear Template
1. Log into Bannerbear → Templates → New Template
2. Set canvas size: 5400 × 7200 px (18×24 poster at 300 DPI)
3. Add a full-canvas image layer — name it exactly: `background_image`
4. Add a centered text box — name it exactly: `quote_text`
   - Font: choose a clean readable font (Playfair Display, Montserrat, etc.)
   - Color: white with text shadow for contrast
5. Save the template → copy the Template UID
6. Open `quoteforge/gui/app.py` and paste the UID:
   `DEFAULT_TEMPLATE_UID = "YOUR_TEMPLATE_UID_HERE"`

## Step 5: Install Dependencies
Double-click `install.bat`

## Step 6: Run QuoteForge
Double-click `QuoteForge.bat`

A window will open. Select a category, pick a sub-category, choose how many designs, then click Generate.

Your designs will be saved to: `Desktop\QuoteForge-Output\`
Your Etsy listings will be saved to: `Desktop\QuoteForge-Output\etsy_listings.csv`
