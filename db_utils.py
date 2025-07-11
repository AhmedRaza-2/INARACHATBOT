from pymongo import MongoClient
from datetime import datetime
import os

client = MongoClient(os.getenv("MONGO_URI"))
db = client["inarabot"]
users = db["users"]


def create_session_if_missing(user_id, session_id):
    user = users.find_one({"username": user_id})
    if not user:
        return

    sessions = user.get("sessions", [])
    if not any(s["session_id"] == session_id for s in sessions):
        title = "Chat on " + datetime.utcnow().strftime("%b %d, %I:%M %p")
        create_session(user_id, session_id, title)

def get_messages_for_session(username, session_id):
    user = users.find_one({"username": username})
    if not user or "sessions" not in user:
        return []

    for s in user["sessions"]:
        if s["session_id"] == session_id:
            return s.get("messages", [])
    
    return []

def log_message(user_id, session_id, sender, text):
    timestamp = datetime.utcnow().isoformat()

    # check if session already exists
    user_doc = users.find_one({"username": user_id, "sessions.session_id": session_id})

    if not user_doc:
        # 🆕 New session
        session_data = {
            "session_id": session_id,
            "title": f"Chat on {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
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
        # ✅ Session exists, push to messages array
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
def get_all_sessions(username):
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

def get_context(user_id, session_id, limit=5):
    user = users.find_one(
        {"username": user_id, "sessions.session_id": session_id},
        {"sessions.$": 1}
    )
    if not user or "sessions" not in user:
        return ""
    
    messages = user["sessions"][0].get("messages", [])[-limit:]
    return "\n".join([f"{m['sender']}: {m['text']}" for m in messages])


def create_session(user_id, session_id, title="New Chat"):
    timestamp = datetime.utcnow().isoformat()

    # ✅ Correctly check if session already exists
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

    # ✅ Push new session into sessions array
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