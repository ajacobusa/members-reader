import random
import requests
from quoteforge.config import UNSPLASH_ACCESS_KEY


def fetch_background_url(keyword: str) -> str | None:
    """Fetch a random high-res Unsplash photo URL matching the keyword."""
    params = {
        "query": keyword,
        "orientation": "portrait",
        "per_page": 10,
        "client_id": UNSPLASH_ACCESS_KEY,
    }
    response = requests.get("https://api.unsplash.com/search/photos", params=params)
    response.raise_for_status()
    results = response.json().get("results", [])
    if not results:
        return None
    photo = random.choice(results)
    return photo["urls"]["full"]
