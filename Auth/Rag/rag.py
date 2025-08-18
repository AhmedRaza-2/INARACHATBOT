from DataBase.mongo_storage import get_faqs, get_faiss_index, store_faiss_index
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
import tempfile

class RAGEngine:
    def __init__(self, base_name):
        self.base_name = base_name
        self.data = get_faqs(base_name) or []
        self.questions = [item['question'] for item in self.data]
        self.answers = [item['answer'] for item in self.data]

        self.model = SentenceTransformer('all-MiniLM-L6-v2')

        index_bytes = get_faiss_index(base_name)
        if index_bytes:
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                tmp.write(index_bytes)
                tmp.flush()
                self.index = faiss.read_index(tmp.name)
        else:
            if not self.questions:
                self.index = faiss.IndexFlatL2(384)  # 384 is the dim for all-MiniLM-L6-v2
                return

            embeddings = self.model.encode(self.questions, show_progress_bar=True)
            embeddings = np.array(embeddings).astype('float32')  # FAISS requires float32
            self.index = faiss.IndexFlatL2(embeddings.shape[1])
            self.index.add(embeddings)

            # Save index using file-based method
            with tempfile.NamedTemporaryFile(delete=False) as tmp:
                faiss.write_index(self.index, tmp.name)
                tmp.seek(0)
                index_bytes = tmp.read()
                store_faiss_index(base_name, index_bytes)

    def retrieve_top_k(self, user_input, k=3):
        if not self.questions or not hasattr(self, "index"):
            return [{"question": "No data found.", "answer": "Please check if FAQ data was stored."}]

        query_vec = self.model.encode([user_input])
        query_vec = np.array(query_vec).astype('float32')  # ensure dtype

        D, I = self.index.search(query_vec, k)

        results = []
        for i in I[0]:
            if 0 <= i < len(self.questions):
                results.append({
                    "question": self.questions[i],
                    "answer": self.answers[i]
                })
        return results
