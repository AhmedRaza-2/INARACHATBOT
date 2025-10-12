<<<<<<< Updated upstream
from pymongo import MongoClient
import certifi, os
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")

try:
    client = MongoClient(
        MONGO_URI,
        tls=True,
        tlsCAFile=certifi.where()
    )
    print("Connected:", client.server_info()["version"])
except Exception as e:
    print("❌ Connection failed:", e)
=======
import time
import requests

MODEL ="phi-3-mini:latest"  # change per file
PROMPT = "Summarize this: Artificial Intelligence is transforming industries."

print(f"🚀 Testing model: {MODEL}")

start = time.time()
try:
    response = requests.post(
        "http://localhost:11434/api/generate",
        json={"model": MODEL, "prompt": PROMPT, "stream": False},
        timeout=60
    )
    response.raise_for_status()
    output = response.json().get("response", "")
    print(f"\n🧩 Response: {output}")
except Exception as e:
    print(f"❌ Error: {e}")
finally:
    print(f"⏱️ Time taken: {time.time() - start:.2f} sec")
>>>>>>> Stashed changes
