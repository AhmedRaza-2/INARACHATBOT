from pymongo import MongoClient
import os
import hashlib
from dotenv import load_dotenv

load_dotenv()

client = MongoClient(os.getenv("MONGO_URI"))
db = client["inarabot"]
users = db["users"]

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def validate_user(username, password):
    user = users.find_one({"username": username})
    if not user:
        return False, "User not found"
    if user["password"] != hash_password(password):
        return False, "Incorrect password"
    return True, str(user["_id"])

def register_user(username, password):
    if users.find_one({"username": username}):
        return False, "Username already exists"
    users.insert_one({
        "username": username,
        "password": hash_password(password)
    })
    return True, "Signup successful"
