"""
Vector Store: embed chunks bằng OpenAI text-embedding-3-small,
tìm kiếm bằng cosine similarity.
Nếu không có API key thì fallback về keyword overlap (BM25-style).
"""

import os
import re
import numpy as np
from typing import List, Dict


def _tokenize(text: str) -> set:
    return set(re.findall(r"\w+", text.lower()))


class VectorStore:
    """
    In-memory vector store.
    Build một lần lúc khởi động agent, query nhiều lần.
    """

    EMBED_MODEL = "text-embedding-3-small"

    def __init__(self):
        self._chunks: List[Dict] = []
        self._embeddings: np.ndarray | None = None
        self._built = False
        self._has_api = bool(os.getenv("OPENAI_API_KEY"))

    # ── Build index ──────────────────────────────────────────────────────

    def build(self, chunks: List[Dict]) -> None:
        """Embed tất cả chunks và lưu vào memory."""
        self._chunks = chunks
        if self._has_api:
            texts = [c["text"] for c in chunks]
            self._embeddings = self._embed_batch(texts)
            print(f"  [VectorStore] Built index: {len(chunks)} chunks, dim={self._embeddings.shape[1]}")
        else:
            print(f"  [VectorStore] Simulation mode: {len(chunks)} chunks (no embedding)")
        self._built = True

    def _embed_batch(self, texts: List[str]) -> np.ndarray:
        from openai import OpenAI
        client = OpenAI()
        all_embs = []
        # batch tối đa 100 texts mỗi lần gọi
        for i in range(0, len(texts), 100):
            batch = texts[i : i + 100]
            resp = client.embeddings.create(model=self.EMBED_MODEL, input=batch)
            embs = [r.embedding for r in sorted(resp.data, key=lambda x: x.index)]
            all_embs.extend(embs)
        arr = np.array(all_embs, dtype=np.float32)
        # L2 normalize
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        return arr / np.maximum(norms, 1e-9)

    def _embed_one(self, text: str) -> np.ndarray:
        from openai import OpenAI
        client = OpenAI()
        resp = client.embeddings.create(model=self.EMBED_MODEL, input=text)
        vec = np.array(resp.data[0].embedding, dtype=np.float32)
        return vec / max(np.linalg.norm(vec), 1e-9)

    # ── Search ───────────────────────────────────────────────────────────

    def search(self, query: str, top_k: int = 3) -> List[Dict]:
        """Trả về top_k chunks liên quan nhất."""
        if not self._built:
            raise RuntimeError("VectorStore chưa được build. Gọi .build() trước.")
        if self._has_api:
            return self._vector_search(query, top_k)
        return self._keyword_search(query, top_k)

    def _vector_search(self, query: str, top_k: int) -> List[Dict]:
        q_emb = self._embed_one(query)
        sims = self._embeddings @ q_emb          # cosine similarity (đã normalize)
        top_idx = np.argsort(sims)[::-1][:top_k]
        return [self._chunks[int(i)] for i in top_idx]

    def _keyword_search(self, query: str, top_k: int) -> List[Dict]:
        """Fallback BM25-style khi không có API key."""
        q_tokens = _tokenize(query)
        scored = []
        for chunk in self._chunks:
            c_tokens = _tokenize(chunk["text"])
            score = len(q_tokens & c_tokens) / (len(q_tokens) + 1e-9)
            scored.append((score, chunk))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in scored[:top_k]]

    def get_unique_doc_ids(self, chunks: List[Dict]) -> List[str]:
        """Lấy danh sách doc_id không trùng từ danh sách chunks."""
        seen = []
        for c in chunks:
            if c["doc_id"] not in seen:
                seen.append(c["doc_id"])
        return seen


if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
    from data.knowledge_base import get_all_docs
    from data.chunker import chunk_all_docs

    docs = get_all_docs()
    chunks = chunk_all_docs(docs)
    vs = VectorStore()
    vs.build(chunks)
    results = vs.search("Ticket P1 phai duoc xu ly trong bao lau?", top_k=3)
    for r in results:
        print(f"  [{r['doc_id']}] {r['chunk_id']}: {r['text'][:80]}...")
