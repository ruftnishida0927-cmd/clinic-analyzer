from flask import Flask, Response
import threading
import time
import json

from analyzer.core import run

app = Flask(__name__)

@app.route("/")
def home():
    result = run("京都駅")
    return Response(
        json.dumps(result, ensure_ascii=False, indent=2),
        content_type="application/json; charset=utf-8"
    )

def background_job():
    while True:
        try:
            print("分析開始")
            run("京都駅")
            print("分析完了")
        except Exception as e:
            print("エラー:", e)

        time.sleep(3600)

if __name__ == "__main__":
    thread = threading.Thread(target=background_job)
    thread.start()

    app.run(host="0.0.0.0", port=10000)
