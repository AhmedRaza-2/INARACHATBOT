from pymongo import MongoClient
from datetime import datetime
import os

client = MongoClient(os.getenv("MONGO_URI"))
db = client["inarabot"]
sessions = db["chat_sessions"]

def start_new_session(user_id):
    session_id = "sess_" + datetime.utcnow().strftime('%Y%m%d%H%M%S')
    doc = {
        "user_id": user_id,
        "session_id": session_id,
        "started_at": datetime.utcnow().isoformat(),
        "title": f"Chat on {datetime.utcnow().strftime('%b %d %Y')}",
        "messages": []
    }
    sessions.insert_one(doc)
    return session_id

def log_message(user_id, session_id, sender, text):
    timestamp = datetime.utcnow().isoformat()
    sessions.update_one(
        {"user_id": user_id, "session_id": session_id},
        {
            "$setOnInsert": {"user_id": user_id, "session_id": session_id, "started_at": timestamp},
            "$push": {
                "messages": {
                    "sender": sender,
                    "text": text,
                    "timestamp": timestamp
                }
            }
        },
        upsert=True
    )

def get_user_sessions(user_id):
    return list(sessions.find({"user_id": user_id}).sort("started_at", -1))

def get_context(user_id, session_id, limit=3):
    session = sessions.find_one({"user_id": user_id, "session_id": session_id})
    if not session or "messages" not in session:
        return ""
    return "\n".join([f"{m['sender']}: {m['text']}" for m in session["messages"][-limit:]])
