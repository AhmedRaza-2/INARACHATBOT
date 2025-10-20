import faiss, numpy as np, tempfile, os
from langchain.text_splitter import RecursiveCharacterTextSplitter
from typing import List, Dict

# ---------- Chunking ----------
def split_into_chunks(text: str, chunk_size=1000, overlap=200) -> List[str]:
    """
    Split raw text into overlapping chunks for embedding.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap
    )
    return splitter.split_text(text)

# ---------- FAISS Index ----------
def build_faiss_index(embedding_model, chunks: list):
    """
    Build FAISS index from a list of chunks (dicts with "text" and optional "title").
    Returns:
        index (faiss.Index)
        mapping = list of {"text": chunk, "title": ...}
    """
    if not chunks:
        raise ValueError("No chunks provided to index.")

    texts, mapping = [], []

    for c in chunks:
        # If it's a dict, get 'text'; otherwise convert to string
        text = c.get("text") if isinstance(c, dict) else str(c)
        if not text.strip():
            continue
        texts.append(text)
        mapping.append({
            "text": text,
            "title": c.get("title", "") if isinstance(c, dict) else ""
        })

    if not texts:
        raise ValueError("No valid text to index.")

    # Build embeddings
    embeddings = embedding_model.encode(
        texts,
        convert_to_numpy=True,
        normalize_embeddings=True
    )

# ---------- Persistence ----------
def faiss_index_to_bytes(index: faiss.Index) -> bytes:
    tmp_name = None
    try:
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_name = tmp.name
            faiss.write_index(index, tmp_name)
            tmp.flush()
            tmp.seek(0)
            return tmp.read()
    finally:
        try:
            if tmp_name and os.path.exists(tmp_name):
                os.unlink(tmp_name)
        except Exception:
            pass

def load_index_from_bytes(index_bytes: bytes) -> faiss.Index:
    tmp_name = None
    try:
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_name = tmp.name
            tmp.write(index_bytes)
            tmp.flush()
        return faiss.read_index(tmp_name)
    finally:
        try:
            if tmp_name and os.path.exists(tmp_name):
                os.unlink(tmp_name)
        except Exception:
            pass