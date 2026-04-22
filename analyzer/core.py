import requests
import time
import math
import re
from bs4 import BeautifulSoup
from typing import List, Dict, Optional, Tuple

SESSION = requests.Session()
COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

# =========================
# 共通
# =========================
def safe_get(url: str, *, params: dict | None = None, timeout: int = 20, headers: dict | None = None) -> Optional[requests.Response]:
    try:
        res = SESSION.get(url, params=params, headers=headers or COMMON_HEADERS, timeout=timeout)
        if res.status_code != 200:
            return None
        if not res.text.strip():
            return None
        return res
    except:
        return None


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\u3000", " ")
    return re.sub(r"\s+", " ", text).strip()


# =========================
# 位置取得
# =========================
def geocode_area(area: str):
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": area, "format": "jsonv2", "limit": 1, "countrycodes": "jp"}

    res = safe_get(url, params=params)
    data = res.json()
    return float(data[0]["lat"]), float(data[0]["lon"])


def fetch_osm(lat, lon, radius=2000):
    url = "https://overpass-api.de/api/interpreter"

    query = f'''
    [out:json];
    node["amenity"="clinic"](around:{radius},{lat},{lon});
    out;
    '''

    res = safe_get(url, params={"data": query})
    data = res.json()

    result = []
    for el in data.get("elements", []):
        name = el.get("tags", {}).get("name")
        if not name:
            continue

        result.append({
            "name": name,
            "lat": el["lat"],
            "lon": el["lon"],
            "tags": el.get("tags", {})
        })

    return result


# =========================
# URL取得改善
# =========================
def fetch_official_site(name: str) -> Optional[str]:
    url = "https://duckduckgo.com/html/"
    params = {"q": f"{name} クリニック"}

    res = safe_get(url, params=params, timeout=15)
    if res is None:
        return None

    soup = BeautifulSoup(res.text, "html.parser")

    for a in soup.select(".result__a"):
        href = a.get("href", "")

        if not href.startswith("http"):
            continue

        if any(x in href for x in [
            "maps.google", "tabelog", "hotpepper",
            "ekiten", "byoinnavi", "caloo", "qlife"
        ]):
            continue

        return href

    return None


# =========================
# 診療科ロジック
# =========================
SPECIALTY_RULES = {
    "内視鏡特化": ["内視鏡", "胃カメラ", "大腸カメラ"],
    "消化器内科": ["消化器", "胃腸"],
    "循環器内科": ["循環器", "高血圧"],
    "呼吸器内科": ["呼吸器", "咳"],
    "糖尿病内科": ["糖尿病"],
    "一般内科": ["内科", "風邪"],
    "皮膚科": ["皮膚", "皮フ"],
    "心療内科・精神科": ["精神", "心療"],
}

PRIORITY = [
    "内視鏡特化",
    "消化器内科",
    "循環器内科",
    "呼吸器内科",
    "糖尿病内科",
    "一般内科"
]


def score_text(text: str) -> Dict[str, int]:
    text = normalize_text(text)
    scores = {}

    for k, words in SPECIALTY_RULES.items():
        for w in words:
            if w in text:
                scores[k] = scores.get(k, 0) + 1

    return scores


def choose_main_axis(scores):
    if not scores:
        return "不明"

    for p in PRIORITY:
        if scores.get(p, 0) >= 2:
            return p

    return max(scores, key=scores.get)


def finalize_specialty(scores: Dict[str, int]):
    if not scores:
        return "不明", 0.0, "unknown"

    max_score = max(scores.values())
    sum_scores = sum(scores.values())

    main_axis = choose_main_axis(scores)

    confidence = round(max_score / (sum_scores + 1), 2)

    if max_score >= 5:
        label = "high"
    elif max_score >= 3:
        label = "mid"
    else:
        label = "low"

    return main_axis, confidence, label


def infer_specialty_v2(name: str, tags: Dict, hp_text: str = ""):
    text = normalize_text(name + " " + " ".join(tags.values()) + " " + hp_text)

    scores = score_text(text)

    main_axis, confidence, label = finalize_specialty(scores)

    return {
        "main_axis": main_axis,
        "confidence": confidence,
        "confidence_label": label,
        "scores": scores
    }


# =========================
# その他
# =========================
def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)

    a = math.sin(dp/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return 2*r*math.atan2(math.sqrt(a), math.sqrt(1-a))


def classify_distance_band(d):
    if d <= 500:
        return "近距離"
    if d <= 1000:
        return "中距離"
    return "遠距離"


# =========================
# メイン
# =========================
def run(area: str):
    lat, lon = geocode_area(area)
    raw = fetch_osm(lat, lon)

    clinics = []

    for r in raw:
        name = r["name"]

        print("処理中:", name)

        site_url = fetch_official_site(name)

        hp_text = ""
        if site_url:
            try:
                res = safe_get(site_url, timeout=10)
                if res:
                    hp_text = res.text[:3000]
            except:
                pass

        result = infer_specialty_v2(name, r["tags"], hp_text)

        d = haversine_m(lat, lon, r["lat"], r["lon"])

        clinics.append({
            "name": name,
            "main_axis": result["main_axis"],
            "confidence": result["confidence"],
            "confidence_label": result["confidence_label"],
            "scores": result["scores"],
            "site_url": site_url,
            "distance_m": round(d, 1),
            "distance_band": classify_distance_band(d)
        })

    print("最終件数:", len(clinics))

    return clinics
