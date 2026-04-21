"""
Retrieval Evaluator: tính Hit Rate@K và MRR cho toàn bộ dataset.
Cũng tính RAGAS-like faithfulness/relevancy (heuristic dựa trên keyword overlap).
"""

from typing import List, Dict
import re


def _tokenize(text: str) -> set:
    return set(re.findall(r"\w+", text.lower()))


class RetrievalEvaluator:

    def calculate_hit_rate(
        self, expected_ids: List[str], retrieved_ids: List[str], top_k: int = 3
    ) -> float:
        """
        Hit Rate@K: 1.0 nếu ít nhất 1 expected_id nằm trong top_k retrieved_ids.
        Với out-of-context cases (expected_ids rỗng), trả về 1.0 (agent đúng khi không retrieve).
        """
        if not expected_ids:
            return 1.0  # out-of-context: không cần retrieve tài liệu nào
        top_retrieved = retrieved_ids[:top_k]
        hit = any(doc_id in top_retrieved for doc_id in expected_ids)
        return 1.0 if hit else 0.0

    def calculate_mrr(
        self, expected_ids: List[str], retrieved_ids: List[str]
    ) -> float:
        """
        Mean Reciprocal Rank: 1/rank của expected_id đầu tiên tìm thấy.
        Out-of-context cases (expected_ids rỗng) → 1.0.
        """
        if not expected_ids:
            return 1.0
        for i, doc_id in enumerate(retrieved_ids):
            if doc_id in expected_ids:
                return 1.0 / (i + 1)
        return 0.0

    def _faithfulness_score(self, answer: str, contexts: List[str]) -> float:
        """
        Heuristic faithfulness: tỉ lệ từ trong câu trả lời xuất hiện trong context.
        Thay thế RAGAS đầy đủ (không cần LLM judge riêng).
        """
        if not answer or not contexts:
            return 0.0
        answer_tokens = _tokenize(answer)
        ctx_tokens = set()
        for ctx in contexts:
            ctx_tokens.update(_tokenize(ctx))
        if not answer_tokens:
            return 0.0
        overlap = len(answer_tokens & ctx_tokens) / len(answer_tokens)
        # Clamp vào [0, 1] và scale nhẹ để phân biệt rõ hơn
        return min(1.0, overlap * 1.2)

    def _relevancy_score(self, question: str, answer: str) -> float:
        """
        Heuristic relevancy: tỉ lệ từ trong câu hỏi xuất hiện trong câu trả lời.
        """
        if not question or not answer:
            return 0.0
        q_tokens = _tokenize(question)
        a_tokens = _tokenize(answer)
        if not q_tokens:
            return 0.0
        overlap = len(q_tokens & a_tokens) / len(q_tokens)
        return min(1.0, overlap * 1.5)

    async def score(self, test_case: Dict, response: Dict) -> Dict:
        """
        Chạy tất cả retrieval + RAGAS-like metrics cho 1 test case.
        test_case cần: expected_retrieval_ids
        response cần: answer, contexts, retrieved_ids
        """
        expected_ids: List[str] = test_case.get("expected_retrieval_ids", [])
        retrieved_ids: List[str] = response.get("retrieved_ids", [])
        answer: str = response.get("answer", "")
        contexts: List[str] = response.get("contexts", [])

        hit_rate = self.calculate_hit_rate(expected_ids, retrieved_ids, top_k=3)
        mrr = self.calculate_mrr(expected_ids, retrieved_ids)
        faithfulness = self._faithfulness_score(answer, contexts)
        relevancy = self._relevancy_score(test_case.get("question", ""), answer)

        return {
            "faithfulness": round(faithfulness, 3),
            "relevancy": round(relevancy, 3),
            "retrieval": {
                "hit_rate": hit_rate,
                "mrr": round(mrr, 3),
                "expected_ids": expected_ids,
                "retrieved_ids": retrieved_ids[:3],
            },
        }

    async def evaluate_batch(self, dataset: List[Dict], responses: List[Dict]) -> Dict:
        """Tổng hợp metrics cho toàn bộ dataset."""
        n = len(dataset)
        if n == 0:
            return {}

        hit_rates, mrrs, faithfulnesses, relevancies = [], [], [], []
        for case, resp in zip(dataset, responses):
            scores = await self.score(case, resp)
            hit_rates.append(scores["retrieval"]["hit_rate"])
            mrrs.append(scores["retrieval"]["mrr"])
            faithfulnesses.append(scores["faithfulness"])
            relevancies.append(scores["relevancy"])

        return {
            "avg_hit_rate": round(sum(hit_rates) / n, 3),
            "avg_mrr":      round(sum(mrrs) / n, 3),
            "avg_faithfulness": round(sum(faithfulnesses) / n, 3),
            "avg_relevancy":    round(sum(relevancies) / n, 3),
            "n": n,
        }
