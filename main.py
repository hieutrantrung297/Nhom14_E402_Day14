"""
Entry point: chạy benchmark V1 vs V2, regression gate, xuất reports.
Chạy: python main.py
"""

import asyncio
import json
import os
import time

from dotenv import load_dotenv

load_dotenv()  # load ANTHROPIC_API_KEY từ .env

from agent.main_agent import MainAgent, MainAgentV2
from engine.runner import BenchmarkRunner
from engine.llm_judge import LLMJudge
from engine.retrieval_eval import RetrievalEvaluator


# ─── Thresholds cho Regression Gate ────────────────────────────────────────
GATE_MIN_SCORE = 3.5        # điểm judge tối thiểu
GATE_MIN_HIT_RATE = 0.70    # hit rate tối thiểu 70%
GATE_MIN_AGREEMENT = 0.70   # agreement rate tối thiểu 70%
GATE_MAX_REGRESSION = -0.2  # không cho phép giảm quá 0.2 điểm so với V1


def _load_dataset(path: str) -> list:
    if not os.path.exists(path):
        print(f"❌ Thiếu {path}. Hãy chạy 'python data/synthetic_gen.py' trước.")
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = [json.loads(line) for line in f if line.strip()]
    if not data:
        print(f"❌ File {path} rỗng.")
    return data


def _build_summary(version: str, results: list, cost_summary: dict) -> dict:
    n = len(results)
    passed = sum(1 for r in results if r["status"] == "pass")
    return {
        "metadata": {
            "version": version,
            "total": n,
            "passed": passed,
            "failed": n - passed,
            "pass_rate": round(passed / n, 3) if n else 0,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        },
        "metrics": {
            "avg_score": round(
                sum(r["judge"]["final_score"] for r in results) / n, 3
            ) if n else 0,
            "hit_rate": round(
                sum(r["ragas"]["retrieval"]["hit_rate"] for r in results) / n, 3
            ) if n else 0,
            "avg_mrr": round(
                sum(r["ragas"]["retrieval"]["mrr"] for r in results) / n, 3
            ) if n else 0,
            "faithfulness": round(
                sum(r["ragas"]["faithfulness"] for r in results) / n, 3
            ) if n else 0,
            "relevancy": round(
                sum(r["ragas"]["relevancy"] for r in results) / n, 3
            ) if n else 0,
            "agreement_rate": round(
                sum(r["judge"]["agreement_rate"] for r in results) / n, 3
            ) if n else 0,
            "avg_latency_s": round(
                sum(r["latency_s"] for r in results) / n, 3
            ) if n else 0,
        },
        "cost": cost_summary,
    }


def _print_summary(label: str, s: dict):
    m = s["metrics"]
    c = s["cost"]
    print(f"\n{'-'*50}")
    print(f"  {label} | {s['metadata']['version']}")
    print(f"{'-'*50}")
    print(f"  Pass/Fail:       {s['metadata']['passed']}/{s['metadata']['failed']}  ({s['metadata']['pass_rate']*100:.1f}%)")
    print(f"  Avg Judge Score: {m['avg_score']:.2f} / 5.0")
    print(f"  Hit Rate @3:     {m['hit_rate']*100:.1f}%")
    print(f"  MRR:             {m['avg_mrr']:.3f}")
    print(f"  Faithfulness:    {m['faithfulness']:.3f}")
    print(f"  Agreement Rate:  {m['agreement_rate']*100:.1f}%")
    print(f"  Avg Latency:     {m['avg_latency_s']:.2f}s")
    print(f"  Total Cost:      ${c['total_usd']:.4f}  (${c['cost_per_case_usd']:.6f}/case)")


def _regression_gate(v1: dict, v2: dict) -> tuple[bool, list]:
    """
    Quyết định APPROVE / BLOCK dựa trên ngưỡng tuyệt đối + delta so với V1.
    Trả về (passed: bool, reasons: list[str])
    """
    m2 = v2["metrics"]
    m1 = v1["metrics"]
    reasons = []
    passed = True

    # Kiểm tra ngưỡng tuyệt đối
    if m2["avg_score"] < GATE_MIN_SCORE:
        reasons.append(f"avg_score {m2['avg_score']:.2f} < threshold {GATE_MIN_SCORE}")
        passed = False
    if m2["hit_rate"] < GATE_MIN_HIT_RATE:
        reasons.append(f"hit_rate {m2['hit_rate']*100:.1f}% < threshold {GATE_MIN_HIT_RATE*100:.0f}%")
        passed = False
    if m2["agreement_rate"] < GATE_MIN_AGREEMENT:
        reasons.append(f"agreement_rate {m2['agreement_rate']*100:.1f}% < threshold {GATE_MIN_AGREEMENT*100:.0f}%")
        passed = False

    delta_score = m2["avg_score"] - m1["avg_score"]
    if delta_score < GATE_MAX_REGRESSION:
        reasons.append(f"score delta {delta_score:.2f} < threshold {GATE_MAX_REGRESSION}")
        passed = False

    return passed, reasons


async def run_benchmark(version: str, agent) -> tuple[list, dict]:
    dataset = _load_dataset("data/golden_set.jsonl")
    if not dataset:
        return [], {}

    evaluator = RetrievalEvaluator()
    judge = LLMJudge()
    runner = BenchmarkRunner(agent, evaluator, judge)

    print(f"\n[START] Benchmark [{version}] tren {len(dataset)} test cases...")
    t0 = time.perf_counter()
    results = await runner.run_all(dataset, batch_size=5)
    elapsed = time.perf_counter() - t0
    print(f"  [DONE] Hoan thanh trong {elapsed:.1f}s")

    cost_summary = runner.compute_cost_summary(results)
    summary = _build_summary(version, results, cost_summary)
    return results, summary


async def main():
    # ── V1 Benchmark ──────────────────────────────────────────────────────
    v1_results, v1_summary = await run_benchmark("Agent_V1_Base", MainAgent())
    if not v1_results:
        return

    # ── V2 Benchmark ──────────────────────────────────────────────────────
    v2_results, v2_summary = await run_benchmark("Agent_V2_Optimized", MainAgentV2())
    if not v2_results:
        return

    # ── So sánh ───────────────────────────────────────────────────────────
    _print_summary("V1", v1_summary)
    _print_summary("V2", v2_summary)

    delta = v2_summary["metrics"]["avg_score"] - v1_summary["metrics"]["avg_score"]
    print(f"\n[DELTA] Score (V2 - V1): {'+' if delta >= 0 else ''}{delta:.3f}")

    # ── Regression Gate ───────────────────────────────────────────────────
    gate_pass, reasons = _regression_gate(v1_summary, v2_summary)
    print(f"\n{'='*50}")
    if gate_pass:
        print("[APPROVE] REGRESSION GATE: CHAP NHAN BAN CAP NHAT V2")
    else:
        print("[BLOCK]   REGRESSION GATE: TU CHOI RELEASE V2")
        for r in reasons:
            print(f"   - {r}")
    print(f"{'='*50}")

    # ── Cost Report ───────────────────────────────────────────────────────
    c = v2_summary["cost"]
    print(f"\n[COST] Chi phi Eval V2:")
    print(f"   Agent generation: ${c['total_agent_usd']:.4f}")
    print(f"   Judge (2 models): ${c['total_judge_usd']:.4f}")
    print(f"   Tong:             ${c['total_usd']:.4f}  (~${c['cost_per_case_usd']:.6f}/case)")
    print(f"   Tip: {c['cost_reduction_tip']}")

    # ── Export reports ────────────────────────────────────────────────────
    os.makedirs("reports", exist_ok=True)
    v2_summary["regression"] = {
        "v1_score": v1_summary["metrics"]["avg_score"],
        "v2_score": v2_summary["metrics"]["avg_score"],
        "delta": round(delta, 3),
        "gate_pass": gate_pass,
        "gate_reasons": reasons,
    }
    with open("reports/summary.json", "w", encoding="utf-8") as f:
        json.dump(v2_summary, f, ensure_ascii=False, indent=2)
    with open("reports/benchmark_results.json", "w", encoding="utf-8") as f:
        json.dump(v2_results, f, ensure_ascii=False, indent=2)

    print("\n[SAVED]")
    print("   reports/summary.json")
    print("   reports/benchmark_results.json")


if __name__ == "__main__":
    asyncio.run(main())
