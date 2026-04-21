from flask import Flask
import threading
import time

# ====== ここに今のコード全部貼る ======

app = Flask(__name__)

@app.route("/")
def home():
    return "Clinic Analyzer Running"

def background_job():
    while True:
        run("京都駅")
        time.sleep(3600)

if __name__ == "__main__":
    thread = threading.Thread(target=background_job)
    thread.start()

    app.run(host="0.0.0.0", port=10000)
