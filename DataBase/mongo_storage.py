from pymongo import MongoClient
import bson
import tempfile
import faiss

def get_db():
    client = MongoClient("mongodb+srv://araza:araza012.pgc@inaracluster.eyp887n.mongodb.net/?retryWrites=true&w=majority&appName=InaraCluster/")
    return client["inara_pk"]

# --- FIXED: Use consistent database naming ---
def get_domain_db(base_name):
    """Get database using the same naming convention as save_chatbot_data"""
    client = MongoClient("mongodb+srv://araza:araza012.pgc@inaracluster.eyp887n.mongodb.net/?retryWrites=true&w=majority&appName=InaraCluster/")
    db_name = base_name.replace(".", "_")  # Same as in save_chatbot_data
    return client[db_name]

# --- Dynamic collection helper (UPDATED) ---
def get_collection(name, base_name):
    """This function now supports both storage methods"""
    try:
        # First try the new method (domain-specific database)
        domain_db = get_domain_db(base_name)
        if name in domain_db.list_collection_names():
            return domain_db[name]
    except:
        pass
    
    # Fallback to old method (inara_pk database with prefixed collections)
    return get_db()[f"{name}_{base_name}"]

# --- Title ---
def get_title(base_name):
    try:
        # Try domain-specific database first
        domain_db = get_domain_db(base_name)
        doc = domain_db.title.find_one()
        if doc:
            return doc['title']
    except:
        pass
    
    # Fallback to old method
    doc = get_db()[f"title_{base_name}"].find_one()
    return doc['title'] if doc else ""

def store_title(base_name, title_text):
    domain_db = get_domain_db(base_name)
    domain_db.title.delete_many({})
    domain_db.title.insert_one({"title": title_text})

# --- Summary ---
def get_summary(base_name):
    try:
        # Try domain-specific database first
        domain_db = get_domain_db(base_name)
        doc = domain_db.summary.find_one()
        if doc:
            return doc['summary']
    except:
        pass
    
    # Fallback to old method
    doc = get_db()[f"summary_{base_name}"].find_one()
    return doc['summary'] if doc else ""

def store_summary(base_name, summary_text):
    domain_db = get_domain_db(base_name)
    domain_db.summary.delete_many({})
    domain_db.summary.insert_one({"summary": summary_text})

# --- FAQs ---
def get_faqs(base_name):
    try:
        # Try domain-specific database first
        domain_db = get_domain_db(base_name)
        faqs = list(domain_db.faqs.find({}, {"_id": 0}))
        if faqs:
            print(f"✅ Found {len(faqs)} FAQs in domain database for {base_name}")
            return faqs
    except Exception as e:
        print(f"⚠️ Domain database lookup failed for {base_name}: {e}")
    
    # Fallback to old method
    try:
        faqs = list(get_db()[f"faqs_{base_name}"].find({}, {"_id": 0}))
        if faqs:
            print(f"✅ Found {len(faqs)} FAQs in inara_pk database for {base_name}")
            return faqs
    except Exception as e:
        print(f"⚠️ Inara_pk database lookup failed for {base_name}: {e}")
    
    print(f"❌ No FAQs found for {base_name}")
    return []

def store_faqs(base_name, qa_list):
    domain_db = get_domain_db(base_name)
    domain_db.faqs.delete_many({})
    domain_db.faqs.insert_many(qa_list)
    print(f"✅ Stored {len(qa_list)} FAQs for {base_name}")

# --- FAISS Index (FIXED) ---
def get_faiss_index(base_name):
    try:
        # Try domain-specific database first
        domain_db = get_domain_db(base_name)
        doc = domain_db.faiss_index.find_one({"name": "faiss_index"})
        if doc:
            return doc["index_data"]
    except:
        pass
    
    # Fallback to old method
    doc = get_db()[f"faiss_{base_name}"].find_one({"name": "faiss_index"})
    return doc["index_data"] if doc else None

def store_faiss_index(base_name, index_bytes):
    domain_db = get_domain_db(base_name)
    domain_db.faiss_index.delete_many({})
    domain_db.faiss_index.insert_one({
        "name": "faiss_index",
        "index_data": bson.Binary(index_bytes)
    })

# --- Full Save (CONSISTENT) ---
def save_chatbot_data(domain, title, summary, faqs, index_obj):
    """This function now uses the same database access pattern as the get functions"""
    
    print(f"💾 Saving chatbot data for domain: {domain}")
    
    # Use consistent database naming
    client = MongoClient("mongodb+srv://araza:araza012.pgc@inaracluster.eyp887n.mongodb.net/?retryWrites=true&w=majority&appName=InaraCluster/")
    db_name = domain.replace(".", "_")  # MongoDB doesn't allow dots in DB names
    db = client[db_name]
    
    print(f"📁 Using database: {db_name}")

    # Store title
    db.title.delete_many({})
    db.title.insert_one({"title": title})
    print(f"✅ Stored title: {title}")

    # Store summary
    db.summary.delete_many({})
    db.summary.insert_one({"summary": summary})
    print(f"✅ Stored summary ({len(summary)} chars)")

    # Store FAQs
    db.faqs.delete_many({})
    if faqs:
        db.faqs.insert_many(faqs)
        print(f"✅ Stored {len(faqs)} FAQs")
    else:
        print("❌ No FAQs to store!")

    # Store FAISS index (write to file first, then store bytes)
    if index_obj is not None:
        try:
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                faiss.write_index(index_obj, tmp.name)
                tmp.seek(0)
                index_bytes = tmp.read()

            db.faiss_index.delete_many({})
            db.faiss_index.insert_one({
                "name": "faiss_index",
                "index_data": bson.Binary(index_bytes)
            })
            print("✅ Stored FAISS index")
        except Exception as e:
            print(f"❌ Failed to store FAISS index: {e}")
    else:
        print("⚠️ No FAISS index to store")
    
    client.close()
    print(f"💾 Finished saving data for {domain}")

# --- Debug helper function ---
def debug_data(base_name):
    """Debug function to check what data exists for a base_name"""
    print(f"\n🔍 DEBUGGING DATA FOR: {base_name}")
    print("=" * 50)
    
    try:
        # Check domain-specific database
        domain_db = get_domain_db(base_name)
        db_name = base_name.replace(".", "_")
        collections = domain_db.list_collection_names()
        print(f"📁 Database '{db_name}' collections: {collections}")
        
        for collection in ['title', 'summary', 'faqs', 'faiss_index']:
            if collection in collections:
                count = domain_db[collection].count_documents({})
                print(f"   📄 {collection}: {count} documents")
                
                if collection == 'faqs' and count > 0:
                    sample = domain_db[collection].find_one()
                    print(f"      Sample: {sample}")
    
    except Exception as e:
        print(f"❌ Error accessing domain database: {e}")
    
    # Check old inara_pk database
    try:
        inara_db = get_db()
        inara_collections = inara_db.list_collection_names()
        matching_collections = [c for c in inara_collections if base_name in c]
        print(f"📁 inara_pk matching collections: {matching_collections}")
        
        for collection in matching_collections:
            count = inara_db[collection].count_documents({})
            print(f"   📄 {collection}: {count} documents")
            
    except Exception as e:
        print(f"❌ Error accessing inara_pk database: {e}")