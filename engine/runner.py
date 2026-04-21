"""
Async Benchmark Runner: chạy song song theo batch, thu thập kết quả + cost.
"""

import asyncio
import time
from typing import List, Dict

# Chi phí agent generation (USD / 1M tokens)
_AGENT_COST = {
    "gpt-4o-mini":    {"input": 0.15,  "output": 0.60},
    "gpt-4o-mini-v2": {"input": 0.15,  "output": 0.60},
    "simulation":     {"input": 0.0,   "output": 0.0},
    "simulation-v2":  {"input": 0.0,   "output": 0.0},
}


def _agent_cost(model: str, in_tok: int, out_tok: int) -> float:
    rates = _AGENT_COST.get(model, {"input": 1.0, "output": 5.0})
    return (in_tok * rates["input"] + out_tok * rates["output"]) / 1_000_000


class BenchmarkRunner:
    def __init__(self, agent, evaluator, judge):
        self.agent = agent
        self.evaluator = evaluator   # RetrievalEvaluator
        self.judge = judge           # LLMJudge

    async def run_single_test(self, test_case: Dict) -> Dict:
        start_time = time.perf_counter()

        # 1. Gọi Agent
        response = await self.agent.query(test_case["question"])
        latency = time.perf_counter() - start_time

        # 2. Retrieval + RAGAS metrics
        ragas_scores = await self.evaluator.score(test_case, response)

        # 3. Multi-Judge
        judge_result = await self.judge.evaluate_multi_judge(
            test_case["question"],
            response["answer"],
            test_case.get("expected_answer", ""),
        )

        # 4. Cost agent generation
        meta = response.get("metadata", {})
        agent_cost = _agent_cost(
            meta.get("model", "simulation"),
            meta.get("input_tokens", 0),
            meta.get("output_tokens", 0),
        )
        total_cost = agent_cost + judge_result.get("cost_usd", 0.0)

        return {
            "test_case_id": test_case.get("id", "?"),
            "test_case": test_case["question"],
            "agent_response": response["answer"],
            "latency_s": round(latency, 3),
            "ragas": ragas_scores,
            "judge": judge_result,
            "cost": {
                "agent_usd": round(agent_cost, 6),
                "judge_usd": round(judge_result.get("cost_usd", 0.0), 6),
                "total_usd": round(total_cost, 6),
            },
            "metadata": {
                "difficulty": test_case.get("metadata", {}).get("difficulty", "unknown"),
                "type": test_case.get("metadata", {}).get("type", "unknown"),
            },
            "status": "fail" if judge_result["final_score"] < 3 else "pass",
        }

    async def run_all(self, dataset: List[Dict], batch_size: int = 5) -> List[Dict]:
        """
        Chạy song song theo batch để không bị Rate Limit.
        batch_size=5 đảm bảo không vượt giới hạn API.
        """
        results = []
        total = len(dataset)
        for i in range(0, total, batch_size):
            batch = dataset[i : i + batch_size]
            tasks = [self.run_single_test(case) for case in batch]
            batch_results = await asyncio.gather(*tasks)
            results.extend(batch_results)
            done = min(i + batch_size, total)
            print(f"  ... Da chay {done}/{total} cases")
        return results

    def compute_cost_summary(self, results: List[Dict]) -> Dict:
        """Tổng hợp chi phí toàn pipeline."""
        total_agent = sum(r["cost"]["agent_usd"] for r in results)
        total_judge = sum(r["cost"]["judge_usd"] for r in results)
        total = total_agent + total_judge
        n = len(results)
        return {
            "total_agent_usd":  round(total_agent, 6),
            "total_judge_usd":  round(total_judge, 6),
            "total_usd":        round(total, 6),
            "cost_per_case_usd": round(total / n, 6) if n else 0,
            "n_cases": n,
            "cost_reduction_tip": (
                "Use gpt-4o-mini for both judges instead of gpt-4o: "
                "saves ~95% judge cost with only ~5-10% accuracy drop."
            ),
        }
