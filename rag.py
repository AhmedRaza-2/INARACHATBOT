import json
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
import os

class RAGEngine:
    def __init__(self, data_path, index_path="faq_index.faiss"):
        self.data = self.load_data(data_path)
        device = "cpu"
        self.model = SentenceTransformer('all-MiniLM-L6-v2',device=device)
        self.questions = [item['question'] for item in self.data]
        self.answers = [item['answer'] for item in self.data]

        if os.path.exists(index_path):
            self.index = faiss.read_index(index_path)
        else:
            self.embeddings = self.model.encode(self.questions, show_progress_bar=True)
            self.index = faiss.IndexFlatL2(self.embeddings.shape[1])
            self.index.add(np.array(self.embeddings))
            faiss.write_index(self.index, index_path)

    def load_data(self, path):
        
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def retrieve_top_k(self, user_input, k=3):
        # Generate embedding for the user query
        query_vec = self.model.encode([user_input])
        
        # Search top-k results
        D, I = self.index.search(np.array(query_vec), k)
        
        # Collect matched FAQs
        results = [{"question": self.questions[i], "answer": self.answers[i]} for i in I[0]]
        return results
