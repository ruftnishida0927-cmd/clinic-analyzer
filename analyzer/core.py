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

def safe_get(url: str, *, params=None, timeout=20, headers=None):
    try:
        res = SESSION.get(url, params=params, headers=headers or COMMON_HEADERS, timeout=timeout)
        if res.status_code != 200:
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

    query = f"""
    [out:json];
    node["amenity"="clinic"](around:{radius},{lat},{lon});
    out;
    """

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
# 診療科ロジック（新）
# =========================

SPECIALTY_RULES = {
    "消化器内科": ["消化器", "胃腸", "腹痛", "便秘"],
    "循環器内科": ["循環器", "高血圧", "心電図"],
    "呼吸器内科": ["呼吸器", "咳", "喘息"],
    "糖尿病内科": ["糖尿病", "血糖"],
    "内視鏡": ["内視鏡", "胃カメラ", "大腸カメラ"],
    "一般内科": ["内科", "風邪", "発熱"],
    "皮膚科": ["皮膚", "皮フ", "ひふ"],
    "精神科": ["精神", "心療", "メンタル"],
}

def score_text(text: str) -> Dict[str, int]:
    text = normalize_text(text)
    scores = {}

    for k, words in SPECIALTY_RULES.items():
        for w in words:
            if w in text:
                scores[k] = scores.get(k, 0) + 1

    return scores


def infer_specialty_v2(name: str, tags: Dict, hp_text: str = ""):

    text = normalize_text(name + " " + " ".join(tags.values()) + " " + hp_text)

    scores = score_text(text)

    if not scores:
        return {
            "main_axis": "不明",
            "confidence": 0,
            "scores": {}
        }

    best = max(scores, key=scores.get)
    total = sum(scores.values())
    confidence = round(scores[best] / total, 2)

    return {
        "main_axis": best,
        "confidence": confidence,
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

        if any(k in name for k in ["整骨院", "整体院", "鍼灸"]):
            continue

        result_sp = infer_specialty_v2(name, r["tags"], "")

        axis = result_sp["main_axis"]
        confidence = result_sp["confidence"]

        d = haversine_m(lat, lon, r["lat"], r["lon"])

        clinics.append({
            "name": name,
            "main_axis": axis,
            "confidence": confidence,
            "distance_m": round(d, 1),
            "distance_band": classify_distance_band(d),
        })

    return clinics
