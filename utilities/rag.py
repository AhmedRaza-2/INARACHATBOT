import os
import google.generativeai as genai
from sentence_transformers import SentenceTransformer
from database.mongo_storage import (
    get_chunks,
    get_faiss_index,
    store_faiss_index,
    store_chunks
)
from utilities.faiss_utils import (
    build_faiss_index,
    faiss_index_to_bytes,
    load_index_from_bytes,
    retrieve_faiss
)

# ---------- Gemini Setup ----------
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

def run_gemini(prompt: str) -> str:
    model = genai.GenerativeModel("gemini-2.0-flash")
    return model.generate_content(prompt).text.strip()

def generate_website_context(text: str) -> str:
    prompt = f"Summarize this website in 3–5 concise sentences:\n\n{text[:8000]}"
    try:
        return run_gemini(prompt)
    except Exception as e:
        print(f"Summary error: {e}")
        return "No summary available."

# ---------- RAG Engine ----------
class RAGEngine:
    def __init__(self, base_name: str):
        self.base_name = base_name
        self.chunks = get_chunks(base_name) or []  # [{"text": ..., "title": ...}]

        self.embedding_model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

        # Load FAISS index if exists
        index_bytes = get_faiss_index(base_name)
        if index_bytes:
            self.index = load_index_from_bytes(index_bytes)
            self.mapping = self.chunks
        else:
            if not self.chunks:
                self.index, self.mapping = None, []
                return

            # Build new FAISS index
            website_text = " ".join([c["text"] for c in self.chunks])
            title = self.chunks[0]["title"] if self.chunks else ""
            self.index, self.mapping = build_faiss_index(self.embedding_model, website_text, title)

            # Save to DB
            index_bytes = faiss_index_to_bytes(self.index)
            store_faiss_index(base_name, index_bytes)
            store_chunks(base_name, self.mapping)

    def retrieve_top_k(self, query: str, k: int = 3):
        if not self.index:
            return [{"text": "No data found. Please crawl this domain first.", "title": "system"}]

        return retrieve_faiss(
            query=query,
            embedding_model=self.embedding_model,
            index=self.index,
            mapping=self.mapping,
            k=k
        )
