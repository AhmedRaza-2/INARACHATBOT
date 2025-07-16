import os
import json
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

class RAGEngine:
    def __init__(self, data_path, index_path="faq_index.faiss"):
        self.data_path = data_path
        self.index_path = index_path
        self.model = SentenceTransformer('all-MiniLM-L6-v2')

        if os.path.exists(index_path):
            print("Loading FAISS index from disk...")
            self.load_index()
        else:
            print("No saved index found, generating from scratch...")
            self.build_and_save_index()

    def build_and_save_index(self):
        # Load and process raw data
        with open(self.data_path, 'r', encoding='utf-8') as f:
            self.data = json.load(f)
        
        self.questions = [item['question'] for item in self.data]
        self.answers = [item['answer'] for item in self.data]
        self.embeddings = self.model.encode(self.questions, show_progress_bar=True)

        # Build FAISS index
        self.index = faiss.IndexFlatL2(self.embeddings.shape[1])
        self.index.add(np.array(self.embeddings))

        # Save index to disk
        faiss.write_index(self.index, self.index_path)
        print("FAISS index and metadata saved.")

    def load_index(self):
        self.index = faiss.read_index(self.index_path)

    def retrieve_top_k(self, user_input, k=3):
        query_vec = self.model.encode([user_input])
        D, I = self.index.search(np.array(query_vec), k)
        results = [{"question": self.questions[i], "answer": self.answers[i]} for i in I[0]]
        return results
