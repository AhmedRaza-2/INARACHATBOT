from pymongo import MongoClient
import os,hashlib,re
from dotenv import load_dotenv

load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI, maxPoolSize=50, connect=True)

def get_users_collection(base_name):
    db = client[base_name]
    users = db["users"]
    users.create_index("username", unique=True)
    return users

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()
def is_valid_username(username):
    return re.match(r"^[A-Za-z_][A-Za-z0-9_]{2,19}$", username)
def is_valid_password(password):
    return (
        len(password) >= 8
        and re.search(r"[A-Z]", password)
        and re.search(r"[a-z]", password)
        and re.search(r"[0-9]", password)
    )
def validate_user(base_name, username, password):
    users = get_users_collection(base_name)
    user = users.find_one({"username": username}, {"password": 1})
    if not user:
        return False, "❌ User not found"
    if user["password"] != hash_password(password):
        return False, "❌ Incorrect password"
    return True, str(user["_id"])

def register_user(base_name, username, password):
    users = get_users_collection(base_name)
    if not is_valid_username(username):
        return False, "❌ Invalid username (3-20 chars, no spaces, no digits at start)"    
    if not is_valid_password(password):
        return False, "❌ Weak password (min 8 chars, must include uppercase, lowercase, digit)"
    if users.find_one({"username": username}):
        return False, "❌ Username already taken"    
    users.insert_one({
        "username": username,
        "password": hash_password(password),
        "sessions": []
    })
    return True, "✅ Signup successful"