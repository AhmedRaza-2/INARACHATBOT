from pymongo import MongoClient
from datetime import datetime, timedelta
import time, json,os,re

client = MongoClient(os.getenv("MONGO_URI"))

def sanitize_db_name(name):
    return re.sub(r"[^\w\-]", "_", name)  # keeps alphanumerics, _ and -
def get_users_collection(base_name):
    """
    Returns the users collection for the given base_name (used as database name).
    """
    db = client[sanitize_db_name(base_name)]
    return db["users"]
def get_pakistan_time():
    return datetime.utcnow() + timedelta(hours=5)
def create_session_if_missing(base_name, user_id, session_id):
    # check if session exists
    existing_sessions = get_all_sessions(base_name, user_id)
    for sess in existing_sessions:
        if sess['session_id'] == session_id:
            return False  # already exists

    # if not, create new session
    new_session = {
        'session_id': session_id,
        'messages': [],
        'created_at': time.time()
    }
    user_sessions = existing_sessions
    user_sessions.append(new_session)

    path = f"conversations/{base_name}_{user_id}.json"
    os.makedirs("conversations", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(user_sessions, f, indent=2)

    return True  # session was newly created

def get_messages_for_session(base_name, username, session_id):
    users = get_users_collection(base_name)
    user = users.find_one({"username": username})
    if not user or "sessions" not in user:
        return []

    for s in user["sessions"]:
        if s["session_id"] == session_id:
            return s.get("messages", [])    
    return []

def log_message(base_name, user_id, session_id, sender, text):
    users = get_users_collection(base_name)
    timestamp = get_pakistan_time().isoformat()

    # check if session already exists
    user_doc = users.find_one({"username": user_id, "sessions.session_id": session_id})

    if not user_doc:
        # New session
        session_data = {
            "session_id": session_id,
            "title": f"Chat on {get_pakistan_time().strftime('%Y-%m-%d %H:%M')}",
            "started_at": timestamp,
            "messages": [{
                "sender": sender,
                "text": text,
                "timestamp": timestamp
            }]
        }
        users.update_one(
            {"username": user_id},
            {"$push": {"sessions": session_data}}
        )
    else:
        # Session exists, push to messages array
        users.update_one(
            {"username": user_id, "sessions.session_id": session_id},
            {
                "$push": {
                    "sessions.$.messages": {
                        "sender": sender,
                        "text": text,
                        "timestamp": timestamp
                    }
                }
            }
        )

def get_all_sessions(base_name, username):
    users = get_users_collection(base_name)
    user = users.find_one({"username": username})
    if not user or "sessions" not in user:
        return []

    # Sort by started_at descending
    sorted_sessions = sorted(
        user["sessions"],
        key=lambda x: x.get("started_at", ""),
        reverse=True
    )

    return [
        {
            "session_id": s["session_id"],
            "title": s.get("title", f"Chat {i+1}"),
            "started_at": s.get("started_at", "")
        }
        for i, s in enumerate(sorted_sessions)
    ]

def get_context(base_name, user_id, session_id, limit=5):
    users = get_users_collection(base_name)
    user = users.find_one(
        {"username": user_id, "sessions.session_id": session_id},
        {"sessions.$": 1}
    )
    if not user or "sessions" not in user:
        return ""
    
    messages = user["sessions"][0].get("messages", [])[-limit:]
    return "\n".join([f"{m['sender']}: {m['text']}" for m in messages])

def create_session(user_id, session_id, base_name=None, title="New Chat"):
    users = get_users_collection(base_name)
    timestamp = get_pakistan_time().isoformat()

    #  Correctly check if session already exists
    existing = users.find_one({
        "username": user_id,
        "sessions": {
            "$elemMatch": {
                "session_id": session_id
            }
        }
    })

    if existing:
        return  # Session already exists

    users.update_one(
        { "username": user_id },
        {
            "$push": {
                "sessions": {
                    "session_id": session_id,
                    "title": title,
                    "started_at": timestamp,
                    "messages": []
                }
            }
        }
    )