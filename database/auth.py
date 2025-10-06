from pymongo import MongoClient
import os
import hashlib
import re
from dotenv import load_dotenv
from database.db_utils import get_users_collection  # ✅ Use dynamic DB

load_dotenv()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def is_valid_username(username):
    return re.match(r"^[A-Za-z_][A-Za-z0-9_]{2,19}$", username)

def is_valid_password(password):
    if len(password) < 8:
        return False
    if not re.search(r"[A-Z]", password):  
        return False
    if not re.search(r"[a-z]", password):  
        return False
    if not re.search(r"[0-9]", password):  
        return False
    return True

def validate_user(base_name, username, password):  # ✅ added base_name
    users = get_users_collection(base_name)
    user = users.find_one({"username": username})
    if not user:
        return False, "❌ User not found"
    if user["password"] != hash_password(password):
        return False, "❌ Incorrect password"
    return True, str(user["_id"])

def register_user(base_name, username, password):  # ✅ added base_name
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
