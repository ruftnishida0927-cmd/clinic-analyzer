from flask import Flask, Response
import threading
import time
import json

from analyzer.core import run

app = Flask(__name__)

# =========================
# 🔥 キャッシュ（ここに結果を貯める）
# =========================
CACHE = []

# =========================
# 🔥 API（軽くする）
# =========================
@app.route("/")
def home():
    return Response(
        json.dumps(CACHE, ensure_ascii=False),
        content_type="application/json; charset=utf-8"
    )

# =========================
# 🔥 バックグラウンド処理（重い処理はこっち）
# =========================
def background_job():
    global CACHE
    while True:
        try:
            print("分析開始")
            CACHE = run("京都駅")
            print("分析完了")
        except Exception as e:
            print("エラー:", e)

        time.sleep(3600)  # 1時間ごと

# =========================
# 🔥 起動処理
# =========================
if __name__ == "__main__":
    thread = threading.Thread(target=background_job)
    thread.daemon = True
    thread.start()

    app.run(host="0.0.0.0", port=10000)
