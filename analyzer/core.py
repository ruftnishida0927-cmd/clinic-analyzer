import requests
import time
import math
import re
from bs4 import BeautifulSoup
from typing import List, Dict, Optional, Tuple


SESSION = requests.Session()
COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0 Safari/537.36"
}


def safe_get(url: str, *, params: dict | None = None, timeout: int = 20, headers: dict | None = None) -> Optional[requests.Response]:
    try:
        res = SESSION.get(url, params=params, headers=headers or COMMON_HEADERS, timeout=timeout)
        if res.status_code != 200:
            print(f"HTTPエラー: {res.status_code} | {url}")
            return None
        if not res.text.strip():
            print(f"空レスポンス | {url}")
            return None
        return res
    except Exception as e:
        print(f"取得失敗: {url} | {e}")
        return None


def geocode_area(area: str) -> tuple[float, float]:
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": area,
        "format": "jsonv2",
        "limit": 1,
        "countrycodes": "jp",
    }
    headers = {"User-Agent": "clinic-tool/1.0"}

    res = safe_get(url, params=params, timeout=30, headers=headers)
    if res is None:
        raise RuntimeError("地点検索に失敗しました")

    try:
        data = res.json()
    except Exception:
        print("Nominatim JSON変換失敗")
        print(res.text[:500])
        raise RuntimeError("地点検索レスポンスが不正です")

    if not data:
        raise RuntimeError("地点が見つかりませんでした")

    return float(data[0]["lat"]), float(data[0]["lon"])


def fetch_osm(lat: float, lon: float, radius: int = 2000) -> List[Dict]:
    url = "https://overpass-api.de/api/interpreter"
    query = f"""
    [out:json][timeout:25];
    (
      node["amenity"="clinic"](around:{radius},{lat},{lon});
      node["amenity"="doctors"](around:{radius},{lat},{lon});
      node["healthcare"="clinic"](around:{radius},{lat},{lon});
      node["healthcare"="doctor"](around:{radius},{lat},{lon});
    );
    out body;
    """
    headers = {"User-Agent": "clinic-tool/1.0"}

    res = safe_get(url, params={"data": query}, timeout=60, headers=headers)
    if res is None:
        return []

    try:
        data = res.json()
    except Exception:
        print("Overpass JSON変換失敗")
        print(res.text[:500])
        return []

    result = []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        name = (tags.get("name") or "").strip()
        if not name:
            continue

        lat2 = el.get("lat")
        lon2 = el.get("lon")
        if lat2 is None or lon2 is None:
            continue

        result.append({
            "name": name,
            "lat": lat2,
            "lon": lon2,
            "tags": tags,
        })

    return result


def fetch_official_site(name: str) -> Optional[str]:
    url = "https://html.duckduckgo.com/html/"
    params = {"q": f"{name} 公式"}

    res = safe_get(url, params=params, timeout=15)
    if res is None:
        return None

    soup = BeautifulSoup(res.text, "html.parser")

    for a in soup.select("a.result__a"):
        href = a.get("href", "")
        if href.startswith("http"):
            return href

    for a in soup.select("a"):
        href = a.get("href", "")
        if href.startswith("http"):
            return href

    return None


def extract_specialties_from_hp(url: str) -> List[str]:
    res = safe_get(url, timeout=15)
    if res is None:
        return ["不明"]

    text = res.text
    found = []

    mapping = {
        "内視鏡特化": ["内視鏡", "胃カメラ", "大腸カメラ", "胃内視鏡", "大腸内視鏡"],
        "消化器内科": ["消化器内科", "消化器", "胃腸科", "胃腸内科"],
        "循環器内科": ["循環器内科", "循環器"],
        "呼吸器内科": ["呼吸器内科", "呼吸器"],
        "糖尿病内科": ["糖尿病内科", "糖尿病", "代謝内科"],
        "一般内科": ["内科", "総合内科", "一般内科"],
        "整形外科": ["整形外科", "整形", "リハビリ"],
        "小児科": ["小児科", "小児", "こども", "子ども", "キッズ"],
        "耳鼻咽喉科": ["耳鼻咽喉科", "耳鼻科", "耳鼻"],
        "皮膚科": ["皮膚科", "皮膚", "皮フ", "ひふ"],
        "眼科": ["眼科"],
        "泌尿器科": ["泌尿器科", "泌尿"],
        "婦人科": ["婦人科", "産婦人科", "婦人", "産婦"],
        "心療内科・精神科": ["心療内科", "精神科", "メンタルクリニック", "精神", "心療", "メンタル", "こころ"],
    }

    for specialty, words in mapping.items():
        if any(word in text for word in words):
            found.append(specialty)

    if not found:
        return ["不明"]

    return list(dict.fromkeys(found))


SPECIALTY_RULES = {
    "内視鏡特化": {
        "strong": ["内視鏡", "胃カメラ", "大腸カメラ", "胃内視鏡", "大腸内視鏡", "ポリープ", "EMR"],
        "medium": ["ピロリ", "鎮静内視鏡", "苦痛の少ない内視鏡"],
    },
    "消化器内科": {
        "strong": ["消化器内科", "消化器", "胃腸科", "胃腸内科"],
        "medium": ["腹痛", "便秘", "下痢", "逆流性食道炎", "胃炎", "過敏性腸症候群", "肝機能", "脂肪肝"],
    },
    "循環器内科": {
        "strong": ["循環器内科", "循環器"],
        "medium": ["高血圧", "動悸", "不整脈", "心電図", "心不全", "狭心症", "胸痛"],
    },
    "呼吸器内科": {
        "strong": ["呼吸器内科", "呼吸器"],
        "medium": ["咳", "喘息", "気管支喘息", "COPD", "睡眠時無呼吸", "いびき", "息切れ"],
    },
    "糖尿病内科": {
        "strong": ["糖尿病内科", "糖尿病", "代謝内科"],
        "medium": ["HbA1c", "血糖", "生活習慣病", "脂質異常症", "高尿酸血症"],
    },
    "一般内科": {
        "strong": ["内科", "総合内科", "一般内科"],
        "medium": ["発熱外来", "発熱", "風邪", "かぜ", "インフルエンザ", "ワクチン", "予防接種"],
    },
    "皮膚科": {
        "strong": ["皮膚科", "皮フ科", "ひふ科"],
        "medium": ["湿疹", "アトピー", "ニキビ", "蕁麻疹"],
    },
    "小児科": {
        "strong": ["小児科"],
        "medium": ["こども", "子ども", "キッズ", "乳幼児"],
    },
    "耳鼻咽喉科": {
        "strong": ["耳鼻咽喉科", "耳鼻科"],
        "medium": ["鼻炎", "副鼻腔炎", "中耳炎", "めまい"],
    },
    "眼科": {
        "strong": ["眼科"],
        "medium": ["白内障", "緑内障", "コンタクト"],
    },
    "整形外科": {
        "strong": ["整形外科"],
        "medium": ["腰痛", "膝痛", "骨粗鬆症", "リハビリ"],
    },
    "泌尿器科": {
        "strong": ["泌尿器科"],
        "medium": ["頻尿", "前立腺", "血尿"],
    },
    "婦人科": {
        "strong": ["婦人科", "産婦人科"],
        "medium": ["生理痛", "更年期", "子宮", "卵巣"],
    },
    "心療内科・精神科": {
        "strong": ["心療内科", "精神科", "メンタルクリニック"],
        "medium": ["不眠", "うつ", "適応障害", "不安", "パニック"],
    },
}

NON_CLINIC_WORDS = [
    "整骨院", "接骨院", "整体院", "鍼灸", "マッサージ", "オステオパシー"
]


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\u3000", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def add_score(score_map: Dict[str, int], key: str, value: int):
    score_map[key] = score_map.get(key, 0) + value


def score_text(text: str, source: str) -> Tuple[Dict[str, int], List[str]]:
    text = normalize_text(text)
    scores: Dict[str, int] = {}
    evidence: List[str] = []

    if not text:
        return scores, evidence

    if source == "name":
        strong_w = 5
        medium_w = 2
    elif source == "tags":
        strong_w = 4
        medium_w = 2
    else:
        strong_w = 3
        medium_w = 1

    for specialty, rule in SPECIALTY_RULES.items():
        for kw in rule["strong"]:
            if kw in text:
                add_score(scores, specialty, strong_w)
                evidence.append(f"{source}:strong:{specialty}:{kw}")

        for kw in rule["medium"]:
            if kw in text:
                add_score(scores, specialty, medium_w)
                evidence.append(f"{source}:medium:{specialty}:{kw}")

    return scores, evidence


def merge_scores(*score_dicts: Dict[str, int]) -> Dict[str, int]:
    merged: Dict[str, int] = {}
    for d in score_dicts:
        for k, v in d.items():
            merged[k] = merged.get(k, 0) + v
    return merged


def finalize_specialty(scores: Dict[str, int]) -> Tuple[str, float, str]:
    if not scores:
        return "不明", 0.0, "unknown"

    adjusted_scores = dict(scores)

    if adjusted_scores.get("内視鏡特化", 0) >= 5:
        adjusted_scores["内視鏡特化"] += 2

    specialized_internal = (
        adjusted_scores.get("消化器内科", 0)
        + adjusted_scores.get("循環器内科", 0)
        + adjusted_scores.get("呼吸器内科", 0)
        + adjusted_scores.get("糖尿病内科", 0)
        + adjusted_scores.get("内視鏡特化", 0)
    )
    if specialized_internal >= 5 and "一般内科" in adjusted_scores:
        adjusted_scores["一般内科"] = max(0, adjusted_scores["一般内科"] - 2)

    best = max(adjusted_scores, key=adjusted_scores.get)
    total = sum(v for v in adjusted_scores.values() if v > 0)
    confidence = round(adjusted_scores[best] / total, 2) if total > 0 else 0.0

    if confidence >= 0.75:
        label = "high"
    elif confidence >= 0.45:
        label = "mid"
    else:
        label = "low"

    return best, confidence, label


def infer_specialty_v2(name: str, tags: Dict, hp_text: str = "") -> Dict:
    name = normalize_text(name)
    tag_text = " ".join([str(v) for v in (tags or {}).values()])
    tag_text = normalize_text(tag_text)
    hp_text = normalize_text(hp_text)

    if any(x in name for x in NON_CLINIC_WORDS):
        return {
            "name": name,
            "excluded": True,
            "main_axis": "除外",
            "confidence": 1.0,
            "confidence_label": "high",
            "scores": {},
            "evidence": ["name:exclude:non_clinic"],
        }

    name_scores, name_ev = score_text(name, "name")
    tag_scores, tag_ev = score_text(tag_text, "tags")
    hp_scores, hp_ev = score_text(hp_text, "hp")

    merged_scores = merge_scores(name_scores, tag_scores, hp_scores)
    main_axis, confidence, confidence_label = finalize_specialty(merged_scores)

    return {
        "name": name,
        "excluded": False,
        "main_axis": main_axis,
        "confidence": confidence,
        "confidence_label": confidence_label,
        "scores": merged_scores,
        "evidence": name_ev + tag_ev + hp_ev,
    }


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)

    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def classify_distance_band(d):
    if d <= 500:
        return "近距離"
    if d <= 1000:
        return "中距離"
    return "遠距離"


def run(area: str):
    lat, lon = geocode_area(area)
    raw = fetch_osm(lat, lon)

    clinics = []

    for r in raw:
        name = r["name"]

        if any(k in name for k in NON_CLINIC_WORDS):
            continue

        site_url = fetch_official_site(name)
        hp_text = ""

        if site_url:
            res = safe_get(site_url, timeout=15)
            if res is not None:
                hp_text = res.text[:3000]
            time.sleep(1)

        result_sp = infer_specialty_v2(name, r["tags"], hp_text)

        if result_sp["excluded"]:
            continue

        d = haversine_m(lat, lon, r["lat"], r["lon"])

        clinics.append({
            "name": name,
            "main_axis": result_sp["main_axis"],
            "confidence": result_sp["confidence"],
            "confidence_label": result_sp["confidence_label"],
            "scores": result_sp["scores"],
            "evidence": result_sp["evidence"],
            "site_url": site_url,
            "distance_m": round(d, 1),
            "distance_band": classify_distance_band(d),
        })

    return clinics
