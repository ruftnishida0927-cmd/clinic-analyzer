import requests
from bs4 import BeautifulSoup
import re

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

def search_official_site(name):
    query = f"{name} クリニック"

    url = "https://duckduckgo.com/html/"
    params = {"q": query}

    try:
        res = requests.get(url, params=params, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, "html.parser")

        links = soup.select(".result__a")

        for a in links:
            href = a.get("href")

            if not href:
                continue

            # 不要サイト除外
            if any(x in href for x in [
                "maps.google",
                "tabelog",
                "hotpepper",
                "ekiten",
                "byoinnavi",
                "caloo",
                "qlife"
            ]):
                continue

            return href

    except Exception:
        return None

    return None
