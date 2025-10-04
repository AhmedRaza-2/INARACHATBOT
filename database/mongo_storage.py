from pymongo import MongoClient
import os, bson, tempfile, certifi, faiss, numpy as np
from sentence_transformers import SentenceTransformer
from utilities.faiss_utils import faiss_index_to_bytes, load_index_from_bytes

MONGO_URI = os.getenv("MONGO_URI")
EMBED_MODEL = os.getenv("EMBED_MODEL", "all-MiniLM-L6-v2")
embedding_model = SentenceTransformer(EMBED_MODEL)

def get_client():
    return MongoClient(
        MONGO_URI,
        serverSelectionTimeoutMS=5000,
        tlsCAFile=certifi.where()
    )

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

# --- Summary ---
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

# --- FAISS Index ---
def get_faiss_index(base_name):
    doc = get_domain_db(base_name).faiss_index.find_one({"name": "faiss_index"})
    return bytes(doc["index_data"]) if doc else None

def store_faiss_index(base_name, index_bytes):
    domain_db = get_domain_db(base_name)
    domain_db.faiss_index.delete_many({})
    domain_db.faiss_index.insert_one({"name": "faiss_index", "index_data": bson.Binary(index_bytes)})
    print("✅ Stored FAISS index bytes")

# --- Cached retrieval ---
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

# --- Save Everything in One Shot ---
def save_chunks_and_index_to_mongo(base_name, title, summary, chunks, faiss_index):
    """
    Store website title, summary, chunks, and FAISS index into MongoDB.
    """
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
