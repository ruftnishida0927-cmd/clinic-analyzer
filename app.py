import requests
import time
import math
import pandas as pd
from bs4 import BeautifulSoup

SESSION = requests.Session()

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

# =========================
# 共通
# =========================
def safe_get(url, params=None, timeout=20):
    try:
        r = SESSION.get(url, params=params, headers=HEADERS, timeout=timeout)
        if r.status_code != 200:
            print(f"HTTPエラー: {url}")
            return None
        return r
    except Exception as e:
        print(f"取得失敗: {url}")
        return None

# =========================
# 位置取得
# =========================
def geocode(area):
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": area,
        "format": "json",
        "limit": 1
    }
    r = safe_get(url, params)
    if not r:
        return None

    data = r.json()
    if not data:
        return None

    return float(data[0]["lat"]), float(data[0]["lon"])

# =========================
# OSM取得
# =========================
def fetch_osm(lat, lon, radius=2000):
    url = "https://overpass-api.de/api/interpreter"

    query = f"""
    [out:json];
    (
      node["amenity"="clinic"](around:{radius},{lat},{lon});
      node["amenity"="doctors"](around:{radius},{lat},{lon});
    );
    out;
    """

    r = safe_get(url, {"data": query})
    if not r:
        return []

    data = r.json()

    results = []
    for e in data.get("elements", []):
        tags = e.get("tags", {})
        name = tags.get("name", "")

        if not name:
            continue

        # 除外
        if any(x in name for x in ["整骨院", "整体", "鍼灸", "マッサージ"]):
            continue

        results.append({
            "name": name,
            "lat": e["lat"],
            "lon": e["lon"],
            "tags": tags
        })

    return results

# =========================
# 距離
# =========================
def calc_distance(lat1, lon1, lat2, lon2):
    R = 6371000
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return int(2 * R * math.atan2(math.sqrt(a), math.sqrt(1-a)))

# =========================
# 公式サイト取得（簡易）
# =========================
def fetch_site(name):
    url = "https://html.duckduckgo.com/html/"
    r = safe_get(url, {"q": name + " クリニック"})
    if not r:
        return None

    soup = BeautifulSoup(r.text, "html.parser")

    for a in soup.select("a.result__a"):
        href = a.get("href")
        if href and href.startswith("http"):
            return href

    return None

# =========================
# HP解析（強化版）
# =========================
def analyze_hp(url):
    r = safe_get(url)
    if not r:
        return {}, "fail"

    soup = BeautifulSoup(r.text, "html.parser")

    scores = {}

    def add(key, w):
        scores[key] = scores.get(key, 0) + w

    # title重視
    if soup.title:
        title = soup.title.text

        if "消化器" in title:
            add("消化器内科", 3)
        if "内視鏡" in title:
            add("内視鏡", 3)
        if "循環器" in title:
            add("循環器内科", 3)

    text = soup.get_text()

    # 本文
    if "胃カメラ" in text or "大腸カメラ" in text:
        add("内視鏡", 2)

    if "糖尿病" in text:
        add("糖尿病内科", 2)

    if "呼吸器" in text:
        add("呼吸器内科", 2)

    if "発熱外来" in text or "風邪" in text:
        add("一般内科", 1)

    return scores, "success"

# =========================
# 名前解析
# =========================
def analyze_name(name):
    scores = {}

    def add(k, w):
        scores[k] = scores.get(k, 0) + w

    if "内視鏡" in name:
        add("内視鏡", 4)
    if "消化器" in name:
        add("消化器内科", 4)
    if "循環器" in name:
        add("循環器内科", 4)
    if "呼吸器" in name:
        add("呼吸器内科", 4)
    if "糖尿病" in name:
        add("糖尿病内科", 4)

    return scores

# =========================
# 判定（信頼度付き）
# =========================
def decide_specialty(scores):
    if not scores:
        return "不明", 0.0, "unknown"

    best = max(scores, key=scores.get)
    total = sum(scores.values())

    confidence = scores[best] / total if total > 0 else 0

    if confidence >= 0.75:
        label = "high"
    elif confidence >= 0.5:
        label = "mid"
    else:
        label = "low"

    return best, round(confidence, 2), label

# =========================
# メイン処理
# =========================
def run(area):
    print(f"エリア: {area}")

    geo = geocode(area)
    if not geo:
        print("位置取得失敗")
        return

    lat, lon = geo

    raw = fetch_osm(lat, lon)
    print(f"取得件数: {len(raw)}")

    results = []

    for r in raw:
        name = r["name"]

        name_score = analyze_name(name)

        site = fetch_site(name)

        hp_score = {}
        hp_status = "no_site"

        if site:
            hp_score, hp_status = analyze_hp(site)
            time.sleep(1)

        # スコア統合
        total = {}

        for d in [name_score, hp_score]:
            for k, v in d.items():
                total[k] = total.get(k, 0) + v

        main, conf, conf_label = decide_specialty(total)

        distance = calc_distance(lat, lon, r["lat"], r["lon"])

        results.append({
            "name": name,
            "main_axis": main,
            "confidence": conf,
            "confidence_label": conf_label,
            "distance_m": distance,
            "site": site,
            "hp_status": hp_status,
            "raw_scores": str(total)
        })

    df = pd.DataFrame(results)

    print("\n=== 結果 ===")
    print(df.head(10))

    df.to_csv("result.csv", index=False, encoding="utf-8-sig")

    print("\nCSV出力完了: result.csv")

# =========================
# 実行
# =========================
if __name__ == "__main__":
    run("京都駅")
