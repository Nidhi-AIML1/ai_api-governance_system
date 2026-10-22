"""
Docker ke andar backend start karne wali script.

1. Pehli baar: image ke andar rakhi database (governance.db) ko /data volume mein copy karti hai.
   (/data ek Docker volume hai, isliye container band hone par bhi data bacha rehta hai.)
2. Agar ML model train nahi hai to train karti hai.
3. Server start karti hai.
"""
import os
import shutil
import sys

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DATA_DIR", "/data")
PORT = int(os.environ.get("PORT", "8000"))
SEED_DB = os.path.join(APP_DIR, "governance.db")

os.makedirs(DATA_DIR, exist_ok=True)
db_path = os.path.join(DATA_DIR, "governance.db")
if not os.path.exists(db_path):
    if os.path.exists(SEED_DB):
        shutil.copyfile(SEED_DB, db_path)
        print("[start] Database copied from the image (first run).")
    else:
        print("[start] No seed database found. Starting with an empty database.")

# database.py "sqlite:///./governance.db" use karta hai, isliye working folder /data bana dete hain
os.chdir(DATA_DIR)
sys.path.insert(0, APP_DIR)

import main  # noqa: E402  (ye tables bana deta hai)
import ml  # noqa: E402
from database import SessionLocal  # noqa: E402

if not ml.is_model_trained():
    db = SessionLocal()
    try:
        info = ml.train_and_save_model(db)
        print(f"[start] ML model trained on {info['windows_count']} windows.")
    except Exception as exc:  # database khali ho to training skip ho jati hai
        print("[start] ML model not trained:", exc)
    finally:
        db.close()

import uvicorn  # noqa: E402

print(f"[start] Server starting on port {PORT}")
uvicorn.run(main.app, host="0.0.0.0", port=PORT)