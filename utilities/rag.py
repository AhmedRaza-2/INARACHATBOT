import os,google.generativeai as genai
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
)
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
