from pymongo import MongoClient
import os, hashlib, re, logging
from dotenv import load_dotenv

load_dotenv()
MONGO_URI = os.getenv("MONGO_URI")
client = MongoClient(MONGO_URI, maxPoolSize=50, connect=True)

# Cache collections to avoid repeated index creation
_collections_cache = {}

def get_users_collection(base_name):
    """Get users collection with cached index creation for performance."""
    if base_name not in _collections_cache:
        db = client[base_name]
        users = db["users"]
        try:
            # Create index only once per base_name
            users.create_index("username", unique=True)
            _collections_cache[base_name] = users
            logging.info(f"✅ Initialized users collection for {base_name}")
        except Exception as e:
            logging.warning(f"Index may already exist for {base_name}: {e}")
            _collections_cache[base_name] = users
    return _collections_cache[base_name]

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
    """Validate user credentials with proper error handling."""
    try:
        if not username or not password:
            return False, "❌ Username and password are required"
        
        users = get_users_collection(base_name)
        user = users.find_one({"username": username}, {"password": 1})
        
        if not user:
            return False, "❌ User not found"
        
        if "password" not in user:
            logging.error(f"User {username} missing password field")
            return False, "❌ Account error. Please contact support."
        
        if user["password"] != hash_password(password):
            return False, "❌ Incorrect password"
        
        return True, str(user["_id"])
    
    except Exception as e:
        logging.exception(f"❌ Error validating user {username}: {e}")
        return False, "❌ Login failed. Please try again."

def register_user(base_name, username, password):
    """Register a new user with validation and error handling."""
    try:
        if not username or not password:
            return False, "❌ Username and password are required"
        
        users = get_users_collection(base_name)
        
        if not is_valid_username(username):
            return False, "❌ Invalid username (3-20 chars, no spaces, no digits at start)"
        
        if not is_valid_password(password):
            return False, "❌ Weak password (min 8 chars, must include uppercase, lowercase, digit)"
        
        # Check if username already exists
        if users.find_one({"username": username}):
            return False, "❌ Username already taken"
        
        # Insert new user
        users.insert_one({
            "username": username,
            "password": hash_password(password),
            "sessions": []
        })
        
        logging.info(f"✅ New user registered: {username}")
        return True, "✅ Signup successful"
    
    except Exception as e:
        logging.exception(f"❌ Error registering user {username}: {e}")
        # Check if it's a duplicate key error (race condition)
        if "duplicate key" in str(e).lower():
            return False, "❌ Username already taken"
        return False, "❌ Signup failed. Please try again."