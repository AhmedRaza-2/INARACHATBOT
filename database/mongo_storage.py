from pymongo import MongoClient
import re,os, bson, tempfile, certifi, faiss, numpy as np
from sentence_transformers import SentenceTransformer
from utilities.faiss_utils import faiss_index_to_bytes, load_index_from_bytes
from datetime import datetime, timedelta

client = MongoClient(os.getenv("MONGO_URI"), tlsCAFile=certifi.where())
MONGO_URI = os.getenv("MONGO_URI")
EMBED_MODEL = os.getenv("EMBED_MODEL", "all-MiniLM-L6-v2")
embedding_model = SentenceTransformer(EMBED_MODEL)

def get_client():
    return MongoClient(MONGO_URI,serverSelectionTimeoutMS=5000,tlsCAFile=certifi.where())

def get_domain_db(base_name):
    client = get_client()
    db_name = base_name.replace(".", "_")
    return client[db_name]

# --- Title ---
def get_title(base_name):
    doc = get_domain_db(base_name).title.find_one()
    return doc['title'] if doc else ""

def store_title(base_name, title_text):
    domain_db = get_domain_db(base_name)
    domain_db.title.delete_many({})
    domain_db.title.insert_one({"title": title_text})

def get_summary(base_name):
    doc = get_domain_db(base_name).summary.find_one()
    return doc['summary'] if doc else ""

def store_summary(base_name, summary_text):
    domain_db = get_domain_db(base_name)
    domain_db.summary.delete_many({})
    domain_db.summary.insert_one({"summary": summary_text})

# --- Chunks (now only: text + title) ---
def get_chunks(base_name):
    return list(get_domain_db(base_name).chunks.find({}, {"_id": 0})) or []

def store_chunks(base_name, chunks):
    """
    Store website chunks (dicts with text + title).
    """
    domain_db = get_domain_db(base_name)
    domain_db.chunks.delete_many({})

    if not chunks:
        print("⚠️ No chunks to store")
        return

    formatted = []
    for c in chunks:
        formatted.append({
            "text": c.get("text", ""),
            "title": c.get("title", "")
        })
    if formatted:
        domain_db.chunks.insert_many(formatted)
        print(f"✅ Stored {len(formatted)} chunks for {base_name}")

def get_faiss_index(base_name):
    doc = get_domain_db(base_name).faiss_index.find_one({"name": "faiss_index"})
    return bytes(doc["index_data"]) if doc else None

def store_faiss_index(base_name, index_bytes):
    domain_db = get_domain_db(base_name)
    domain_db.faiss_index.delete_many({})
    domain_db.faiss_index.insert_one({"name": "faiss_index", "index_data": bson.Binary(index_bytes)})
    print("✅ Stored FAISS index bytes")

faiss_cache, chunks_cache = {}, {}

def get_cached_index(base_name):
    if base_name in faiss_cache:
        return faiss_cache[base_name], chunks_cache[base_name]

    index_bytes = get_faiss_index(base_name)
    chunks = get_chunks(base_name)
    if not index_bytes or not chunks:
        return None, None

    index = load_index_from_bytes(index_bytes)
    faiss_cache[base_name], chunks_cache[base_name] = index, chunks
    return index, chunks

def retrieve_top_k_from_mongo(base_name, user_input, k=4):
    index, chunks = get_cached_index(base_name)
    if not index or not chunks:
        return []
    qvec = embedding_model.encode([user_input], show_progress_bar=False)
    qarr = np.array(qvec).astype('float32')
    D, I = index.search(qarr, k)
    return [chunks[i] for i in I[0] if 0 <= i < len(chunks)]

def save_chunks_and_index_to_mongo(base_name, title, summary, chunks, faiss_index):
#    Store website title, summary, chunks, and FAISS index into MongoDB.
    try:
        store_title(base_name, title)
        store_summary(base_name, summary)
        store_chunks(base_name, chunks)
        index_bytes = faiss_index_to_bytes(faiss_index)
        store_faiss_index(base_name, index_bytes)

        print(f"✅ Saved all data for {base_name} (title, summary, chunks, index)")
        return True
    except Exception as e:
        print(f"❌ Failed to save data for {base_name}: {e}")
        return False

def sanitize_db_name(name: str) -> str:
    #Ensure valid MongoDB db name (replace invalid chars)
    return re.sub(r"[^\w\-]", "_", name or "default")

def get_users_collection(base_name: str):
    #Returns the users collection for the given base_name (used as database name).#
    db = client[sanitize_db_name(base_name)]
    return db["users"]


def get_pakistan_time():
    return datetime.utcnow() + timedelta(hours=5)


def create_session_if_missing(base_name, user_id, session_id):
    users = get_users_collection(base_name)
    existing = users.find_one({
        "username": user_id,
        "sessions": {"$elemMatch": {"session_id": session_id}}
    })
    return not existing


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
    """Log a message to MongoDB. Creates session if missing and updates title from first user message."""
    users = get_users_collection(base_name)
    timestamp = get_pakistan_time().isoformat()

    user_doc = users.find_one({"username": user_id, "sessions.session_id": session_id})
    if not user_doc:
        # Create new session with smart title from first user message
        title = text[:40] + "..." if len(text) > 40 else text if sender == "user" else f"Chat {get_pakistan_time().strftime('%b %d, %I:%M %p')}"
        session_data = {
            "session_id": session_id,
            "title": title,
            "started_at": timestamp,
            "messages": [{"sender": sender, "text": text, "timestamp": timestamp}]
        }
        users.update_one(
            {"username": user_id},
            {"$push": {"sessions": session_data}},
            upsert=True
        )
    else:
        # Update title with first user message if current title is generic
        session = next((s for s in user_doc.get("sessions", []) if s["session_id"] == session_id), None)
        if session and sender == "user" and len(session.get("messages", [])) == 0:
            # This is the first user message - update title
            title = text[:40] + "..." if len(text) > 40 else text
            users.update_one(
                {"username": user_id, "sessions.session_id": session_id},
                {"$set": {"sessions.$.title": title}}
            )
        
        # Add message
        users.update_one(
            {"username": user_id, "sessions.session_id": session_id},
            {"$push": {"sessions.$.messages": {"sender": sender, "text": text, "timestamp": timestamp}}}
        )


def get_all_sessions(base_name, username):
    users = get_users_collection(base_name)
    user = users.find_one({"username": username})
    if not user or "sessions" not in user:
        return []

    sorted_sessions = sorted(user["sessions"], key=lambda x: x.get("started_at", ""), reverse=True)
    return [
        {"session_id": s["session_id"], "title": s.get("title", f"Chat {i+1}"), "started_at": s.get("started_at", "")}
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


def create_session(user_id, session_id, base_name=None, title=None):
    """Create a new chat session. Title will be auto-generated from first message."""
    users = get_users_collection(base_name)
    timestamp = get_pakistan_time().isoformat()

    existing = users.find_one({"username": user_id, "sessions.session_id": session_id})
    if existing:
        return

    # Auto-generate title from timestamp if not provided
    if not title:
        title = f"Chat {get_pakistan_time().strftime('%b %d, %I:%M %p')}"

    users.update_one(
        {"username": user_id},
        {
            "$setOnInsert": {"username": user_id},
            "$push": {
                "sessions": {
                    "session_id": session_id,
                    "title": title,
                    "started_at": timestamp,
                    "messages": []  # No greeting here - frontend handles it
                }
            }
        },
        upsert=True
    )


# --- Retrain & Custom Data Functions ---

def delete_all_data(base_name):
    """Delete all data for a domain. Chat sessions preserved."""
    try:
        domain_db = get_domain_db(base_name)
        domain_db.chunks.delete_many({})
        domain_db.faiss_index.delete_many({})
        domain_db.title.delete_many({})
        domain_db.summary.delete_many({})
        
        if base_name in faiss_cache:
            del faiss_cache[base_name]
        if base_name in chunks_cache:
            del chunks_cache[base_name]
        
        print(f"✅ Deleted all data for {base_name}")
        return True
    except Exception as e:
        print(f"❌ Delete failed for {base_name}: {e}")
        return False


def add_custom_chunks(base_name, custom_text, title="Custom Data"):
    """Add custom chunks to existing knowledge base."""
    try:
        from utilities.faiss_utils import split_into_chunks, build_faiss_index
        
        existing_chunks = get_chunks(base_name)
        new_chunks = split_into_chunks(custom_text, chunk_size=1000, overlap=200)
        
        formatted_new = [
            {"text": c if isinstance(c, str) else c.get("text", ""), 
             "title": title, 
             "source": "custom"}
            for c in new_chunks
        ]
        
        all_chunks = existing_chunks + formatted_new
        faiss_index, _ = build_faiss_index(embedding_model, all_chunks)
        
        store_chunks(base_name, all_chunks)
        index_bytes = faiss_index_to_bytes(faiss_index)
        store_faiss_index(base_name, index_bytes)
        
        if base_name in faiss_cache:
            del faiss_cache[base_name]
        if base_name in chunks_cache:
            del chunks_cache[base_name]
        
        print(f"✅ Added {len(formatted_new)} custom chunks to {base_name}")
        return True, len(formatted_new)
    except Exception as e:
        print(f"❌ Add custom chunks failed: {e}")
        return False, 0


def get_data_stats(base_name):
    """Get knowledge base statistics."""
    try:
        chunks = get_chunks(base_name)
        total = len(chunks)
        custom = len([c for c in chunks if c.get("source") == "custom"])
        
        return {
            "total_chunks": total,
            "crawled_chunks": total - custom,
            "custom_chunks": custom,
            "title": get_title(base_name),
            "summary": get_summary(base_name),
            "has_data": total > 0
        }
    except Exception as e:
        print(f"❌ Get stats failed: {e}")
        return {
            "total_chunks": 0,
            "crawled_chunks": 0,
            "custom_chunks": 0,
            "title": "",
            "summary": "",
            "has_data": False
        }


