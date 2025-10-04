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
