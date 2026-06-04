"""Canva API client for automated poster generation.

Canva Connect API: developers.canva.com
Requires: Canva Pro + API access (waitlist as of 2026)

Fallback: if Canva API is not configured, falls back to Bannerbear.
"""
import os
import time
import requests

CANVA_API_KEY: str = os.getenv("CANVA_API_KEY", "")
CANVA_BASE_URL = "https://api.canva.com/rest/v1"


def _canva_headers() -> dict:
    return {
        "Authorization": f"Bearer {CANVA_API_KEY}",
        "Content-Type": "application/json",
    }


def is_configured() -> bool:
    return bool(CANVA_API_KEY)


def create_design_from_template(
    template_id: str,
    quote_text: str,
    recipient_name: str,
    title: str = "",
) -> dict:
    """Create a Canva design from a brand template, inject quote text.

    Returns dict with design_id and export_url (once exported).
    Falls back gracefully if Canva API is not configured.
    """
    if not is_configured():
        return {"status": "skipped", "reason": "Canva API not configured — using Bannerbear"}

    # Step 1: Create autofill job
    payload = {
        "brand_template_id": template_id,
        "data": {
            "quote_text": {"type": "text", "text": quote_text},
            "recipient_name": {"type": "text", "text": recipient_name},
            "title_text": {"type": "text", "text": title},
        },
    }
    resp = requests.post(
        f"{CANVA_BASE_URL}/brand-templates/{template_id}/autofills",
        headers=_canva_headers(),
        json=payload,
        timeout=30,
    )
    if resp.status_code not in (200, 201):
        return {"status": "error", "message": resp.text}

    job_id = resp.json().get("job", {}).get("id", "")
    if not job_id:
        return {"status": "error", "message": "No job ID returned from Canva"}

    # Step 2: Poll for completion
    for _ in range(30):
        time.sleep(3)
        poll = requests.get(
            f"{CANVA_BASE_URL}/autofills/{job_id}",
            headers=_canva_headers(),
            timeout=15,
        )
        if poll.status_code == 200:
            data = poll.json().get("job", {})
            if data.get("status") == "success":
                design_id = data.get("result", {}).get("design", {}).get("id", "")
                return {"status": "success", "design_id": design_id, "job_id": job_id}
            elif data.get("status") == "failed":
                return {"status": "error", "message": "Canva autofill job failed"}

    return {"status": "timeout", "message": "Canva job timed out"}


def export_design_as_png(design_id: str) -> str | None:
    """Export a Canva design as PNG and return the download URL."""
    if not is_configured() or not design_id:
        return None

    payload = {"design_id": design_id, "format": "png", "export_quality": "pro"}
    resp = requests.post(
        f"{CANVA_BASE_URL}/exports",
        headers=_canva_headers(),
        json=payload,
        timeout=30,
    )
    if resp.status_code not in (200, 201):
        return None

    job_id = resp.json().get("job", {}).get("id", "")
    for _ in range(20):
        time.sleep(3)
        poll = requests.get(
            f"{CANVA_BASE_URL}/exports/{job_id}",
            headers=_canva_headers(),
            timeout=15,
        )
        if poll.status_code == 200:
            data = poll.json().get("job", {})
            if data.get("status") == "success":
                urls = data.get("urls", [])
                return urls[0] if urls else None
    return None


def get_canva_setup_guide() -> str:
    return """
CANVA API SETUP
===============
1. Go to developers.canva.com → Apply for API access (Pro required)
2. Once approved: Create an app → Get API key
3. Set in config.py: CANVA_API_KEY = "your_key"

4. Create Brand Templates in Canva:
   - Design your poster template
   - Add text layers named exactly: "quote_text", "recipient_name", "title_text"
   - Publish as Brand Template
   - Copy the template ID from the URL

5. Use template IDs in your pipeline config.

FALLBACK: If Canva API is unavailable, QuoteForge uses Bannerbear automatically.
"""
