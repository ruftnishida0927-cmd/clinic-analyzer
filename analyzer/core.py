import requests
import time
import math
from bs4 import BeautifulSoup
from typing import List, Dict, Optional


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
    # Google直読みは不安定なので使わない
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

    # フォールバック
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
        "内視鏡": ["内視鏡", "胃カメラ", "大腸カメラ"],
        "消化器": ["消化器", "胃腸"],
        "循環器": ["循環器"],
        "呼吸器": ["呼吸器"],
        "内分泌": ["糖尿病", "内分泌"],
        "整形外科": ["整形", "リハビリ"],
        "小児科": ["小児", "こども", "子ども", "キッズ"],
        "耳鼻咽喉科": ["耳鼻"],
        "皮膚科": ["皮膚", "皮フ", "ひふ"],
        "眼科": ["眼科"],
        "泌尿器科": ["泌尿"],
        "婦人科": ["婦人", "産婦"],
        "精神科": ["精神", "心療", "メンタル", "こころ"],
        "内科": ["内科"],
    }

    for specialty, words in mapping.items():
        if any(word in text for word in words):
            found.append(specialty)

    if not found:
        return ["不明"]

    # 重複除去
    return list(dict.fromkeys(found))


def refine_internal_medicine(name: str, current_specialties: List[str]) -> List[str]:
    text = name or ""

    if any(k in text for k in ["内視鏡", "胃カメラ", "大腸カメラ"]):
        return ["内視鏡"]
    if any(k in text for k in ["消化器", "胃腸"]):
        return ["消化器"]
    if "循環器" in text:
        return ["循環器"]
    if "呼吸器" in text:
        return ["呼吸器"]
    if any(k in text for k in ["糖尿病", "内分泌"]):
        return ["内分泌"]

    return ["内科（軽）"]


def infer_specialties(name: str, tags: Dict) -> List[str]:
    name = name or ""
    text = name + " " + " ".join([str(v) for v in tags.values()])

    # 最優先
    if any(k in text for k in ["皮膚", "皮フ", "ひふ"]):
        return ["皮膚科"]
    if any(k in text for k in ["精神", "心療", "メンタル", "こころ"]):
        return ["精神科"]
    if any(k in text for k in ["小児", "こども", "子ども", "キッズ"]):
        return ["小児科"]
    if "耳鼻" in text:
        return ["耳鼻咽喉科"]
    if "眼科" in text:
        return ["眼科"]
    if "泌尿" in text:
        return ["泌尿器科"]
    if any(k in text for k in ["婦人", "産婦"]):
        return ["婦人科"]
    if "整形" in text:
        return ["整形外科"]

    specialties = []

    if any(k in text for k in ["内視鏡", "胃カメラ", "大腸カメラ"]):
        specialties.append("内視鏡")
    if any(k in text for k in ["消化器", "胃腸"]):
        specialties.append("消化器")
    if "循環器" in text:
        specialties.append("循環器")
    if "呼吸器" in text:
        specialties.append("呼吸器")
    if any(k in text for k in ["糖尿病", "内分泌"]):
        specialties.append("内分泌")
    if "内科" in text:
        specialties.append("内科")

    if specialties:
        return list(dict.fromkeys(specialties))

    if any(k in name for k in ["医院", "クリニック", "診療所"]):
        return ["内科"]

    return ["不明"]


def choose_main_axis(specialties: List[str], name: str) -> str:
    text = name or ""

    priority_by_name = [
        ("内視鏡", "内視鏡"),
        ("消化器", "消化器"),
        ("循環器", "循環器"),
        ("呼吸器", "呼吸器"),
        ("整形", "整形外科"),
        ("小児", "小児科"),
        ("耳鼻", "耳鼻咽喉科"),
        ("皮膚", "皮膚科"),
        ("皮フ", "皮膚科"),
        ("眼科", "眼科"),
        ("泌尿", "泌尿器科"),
        ("婦人", "婦人科"),
        ("精神", "精神科"),
        ("心療", "精神科"),
        ("メンタル", "精神科"),
        ("こころ", "精神科"),
    ]

    for keyword, axis in priority_by_name:
        if keyword in text:
            return axis

    priority = [
        "内視鏡",
        "消化器",
        "循環器",
        "呼吸器",
        "内分泌",
        "整形外科",
        "小児科",
        "耳鼻咽喉科",
        "皮膚科",
        "眼科",
        "泌尿器科",
        "婦人科",
        "精神科",
        "内科（軽）",
        "内科",
        "不明",
    ]

    for p in priority:
        if p in specialties:
            return p

    return "不明"


def infer_strength(name: str, tags: Dict, main_axis: str) -> int:
    text = (name or "") + " " + " ".join([str(v) for v in tags.values()])

    if any(k in text for k in ["専門", "センター", "内視鏡"]):
        return 3
    if any(k in text for k in ["クリニック", "医院"]):
        return 2
    return 1


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

        if any(k in name for k in ["整骨院", "接骨院", "整体院", "鍼灸", "マッサージ", "オステオパシー"]):
            continue

        sp = infer_specialties(name, r["tags"])

        if sp == ["内科"]:
            sp = refine_internal_medicine(name, sp)

        if sp == ["不明"]:
            site_url = fetch_official_site(name)
            if site_url:
                sp = extract_specialties_from_hp(site_url)
            time.sleep(1)

        axis = choose_main_axis(sp, name)
        strength = infer_strength(name, r["tags"], axis)
        d = haversine_m(lat, lon, r["lat"], r["lon"])

        clinics.append({
            "name": name,
            "main_axis": axis,
            "specialties": sp,
            "strength": strength,
            "distance_m": round(d, 1),
            "distance_band": classify_distance_band(d),
        })


    if not clinics:
        print("クリニック取得なし")
        return

    return clinics
