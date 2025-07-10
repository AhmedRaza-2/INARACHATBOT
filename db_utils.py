# db_utils.py

from pymongo import MongoClient
from datetime import datetime
import os

client = MongoClient(os.getenv("MONGO_URI"))
db = client["inarabot"]
sessions = db["chat_sessions"]

def log_message(user_id, session_id, sender, text):
    timestamp = datetime.utcnow().isoformat()

    # Try to find user document
    user_doc = sessions.find_one({ "user_id": user_id })

    if not user_doc:
        # Create new user doc if doesn't exist
        sessions.insert_one({
            "user_id": user_id,
            "sessions": [{
                "session_id": session_id,
                "started_at": timestamp,
                "messages": [{
                    "sender": sender,
                    "text": text,
                    "timestamp": timestamp
                }]
            }]
        })
    else:
        result = sessions.update_one(
            { "user_id": user_id, "sessions.session_id": session_id },
            {
                "$push": { "sessions.$.messages": {
                    "sender": sender,
                    "text": text,
                    "timestamp": timestamp
                }}
            }
        )

        if result.matched_count == 0:
            # If session doesn't exist, add it
            sessions.update_one(
                { "user_id": user_id },
                { "$push": {
                    "sessions": {
                        "session_id": session_id,
                        "started_at": timestamp,
                        "messages": [{
                            "sender": sender,
                            "text": text,
                            "timestamp": timestamp
                        }]
                    }
                }}
            )
def get_context(user_id, session_id, limit=3):
    user = sessions.find_one({ "user_id": user_id })
    if not user:
        return ""

    for sess in user.get("sessions", []):
        if sess["session_id"] == session_id:
            msgs = sess.get("messages", [])[-limit:]
            return "\n".join([f"{m['sender']}: {m['text']}" for m in msgs])

    return ""