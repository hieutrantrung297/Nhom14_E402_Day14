"""
RAG Agent:
  1. Chunking   — chia tài liệu thành chunks (400 chars, overlap 80)
  2. Indexing   — embed chunks bằng text-embedding-3-small (build 1 lần)
  3. Retrieval  — cosine similarity search, top_k chunks
  4. Generation — gpt-4o-mini sinh câu trả lời từ retrieved chunks
Fallback simulation nếu không có OPENAI_API_KEY.
"""

import asyncio
import os
import sys
from typing import Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from data.knowledge_base import get_all_docs
from data.chunker import chunk_all_docs
from data.vector_store import VectorStore

# ── Build index một lần khi module load ─────────────────────────────────────
_CHUNKS = chunk_all_docs(get_all_docs(), chunk_size=400, overlap=80)
_STORE = VectorStore()
_STORE.build(_CHUNKS)


# ── Generation ───────────────────────────────────────────────────────────────

async def _generate_with_openai(
    question: str, contexts: List[str]
) -> tuple[str, int, int]:
    """Trả về (answer, input_tokens, output_tokens)."""
    from openai import AsyncOpenAI

    context_str = "\n\n---\n\n".join(contexts)
    system = (
        "Ban la tro ly IT/HR helpdesk chuyen nghiep. "
        "Chi tra loi dua tren thong tin trong phan Context ben duoi. "
        "Neu thong tin khong co trong Context, hay noi ro: "
        "'Toi khong tim thay thong tin nay trong tai lieu.' "
        "Tra loi ngan gon, chinh xac, bang tieng Viet."
    )
    user_msg = f"Context:\n{context_str}\n\nCau hoi: {question}"

    client = AsyncOpenAI()
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        max_tokens=512,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ],
    )
    answer = response.choices[0].message.content
    return answer, response.usage.prompt_tokens, response.usage.completion_tokens


def _simulate_answer(
    question: str, contexts: List[str]
) -> tuple[str, int, int]:
    ctx = contexts[0][:200] if contexts else ""
    answer = f"[SIM] Based on: {ctx}... (answer for: {question[:50]})"
    return answer, 200, 80


# ── Agent classes ─────────────────────────────────────────────────────────────

class MainAgent:
    """
    RAG Agent V1:
    - Chunking: 400 chars, overlap 80
    - Retrieval: top_k=3 chunks via cosine similarity
    - Generation: gpt-4o-mini
    """

    def __init__(self, top_k: int = 3):
        self.name = "RAG-SupportAgent-v1"
        self.top_k = top_k
        self._has_api = bool(os.getenv("OPENAI_API_KEY"))

    async def query(self, question: str) -> Dict:
        # 1. Retrieve top_k chunks
        retrieved_chunks = _STORE.search(question, top_k=self.top_k)

        # 2. Extract unique doc_ids (cho retrieval eval)
        retrieved_ids = _STORE.get_unique_doc_ids(retrieved_chunks)

        # 3. Build contexts từ chunks
        contexts = [
            f"[{c['title']} | {c['chunk_id']}]\n{c['text']}"
            for c in retrieved_chunks
        ]

        # 4. Generate
        if self._has_api:
            try:
                answer, in_tok, out_tok = await _generate_with_openai(question, contexts)
            except Exception as e:
                answer, in_tok, out_tok = _simulate_answer(question, contexts)
                answer += f" [API error: {e}]"
        else:
            answer, in_tok, out_tok = _simulate_answer(question, contexts)

        return {
            "answer": answer,
            "contexts": contexts,
            "retrieved_ids": retrieved_ids,
            "retrieved_chunks": [c["chunk_id"] for c in retrieved_chunks],
            "metadata": {
                "model": "gpt-4o-mini" if self._has_api else "simulation",
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "sources": retrieved_ids,
                "chunk_size": 400,
                "overlap": 80,
                "top_k": self.top_k,
            },
        }


class MainAgentV2(MainAgent):
    """
    Agent V2 — Optimized:
    - top_k=2 (ít context hơn → tiết kiệm ~30% token agent)
    - Chunk size nhỏ hơn: 300 chars (tập trung hơn)
    """

    def __init__(self):
        # Build riêng với chunk_size nhỏ hơn
        self.name = "RAG-SupportAgent-v2-optimized"
        self.top_k = 2
        self._has_api = bool(os.getenv("OPENAI_API_KEY"))

        # Build store V2 riêng (chunk nhỏ hơn)
        self._store_v2 = VectorStore()
        chunks_v2 = chunk_all_docs(get_all_docs(), chunk_size=300, overlap=60)
        self._store_v2.build(chunks_v2)

    async def query(self, question: str) -> Dict:
        retrieved_chunks = self._store_v2.search(question, top_k=self.top_k)
        retrieved_ids = self._store_v2.get_unique_doc_ids(retrieved_chunks)
        contexts = [
            f"[{c['title']} | {c['chunk_id']}]\n{c['text']}"
            for c in retrieved_chunks
        ]

        if self._has_api:
            try:
                answer, in_tok, out_tok = await _generate_with_openai(question, contexts)
            except Exception as e:
                answer, in_tok, out_tok = _simulate_answer(question, contexts)
                answer += f" [API error: {e}]"
        else:
            answer, in_tok, out_tok = _simulate_answer(question, contexts)

        return {
            "answer": answer,
            "contexts": contexts,
            "retrieved_ids": retrieved_ids,
            "retrieved_chunks": [c["chunk_id"] for c in retrieved_chunks],
            "metadata": {
                "model": "gpt-4o-mini-v2" if self._has_api else "simulation-v2",
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "sources": retrieved_ids,
                "chunk_size": 300,
                "overlap": 60,
                "top_k": self.top_k,
            },
        }


# ── Quick test ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    async def _test():
        print(f"Total chunks in index: {len(_CHUNKS)}")
        agent = MainAgent()
        resp = await agent.query("Ticket P1 phai xu ly xong trong bao lau?")
        print("Answer:", resp["answer"])
        print("Retrieved doc IDs:", resp["retrieved_ids"])
        print("Chunks:", resp["retrieved_chunks"])

    asyncio.run(_test())
