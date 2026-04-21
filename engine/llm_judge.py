"""
Multi-Model Judge: gpt-4o-mini (Judge A) + gpt-4o (Judge B).
Tính Agreement Rate, xử lý xung đột điểm, kiểm tra position bias.
Fallback về simulation nếu không có API key.
"""

import asyncio
import json
import os
from typing import Dict, Any

# Chi phí ước tính (USD / 1M tokens)
_COST = {
    "gpt-4o-mini": {"input": 0.15,  "output": 0.60},
    "gpt-4o":      {"input": 2.50,  "output": 10.00},
}

_JUDGE_PROMPT = """\
Bạn là chuyên gia đánh giá chất lượng câu trả lời AI.

CÂU HỎI: {question}

GROUND TRUTH (câu trả lời đúng chuẩn):
{ground_truth}

CÂU TRẢ LỜI CỦA AI:
{answer}

Chấm điểm trên thang 1–5:
5 — Hoàn hảo: Chính xác, đầy đủ, chuyên nghiệp so với Ground Truth.
4 — Tốt: Chính xác nhưng thiếu một vài chi tiết nhỏ.
3 — Chấp nhận được: Đúng phần lớn, có vài sai sót nhỏ.
2 — Kém: Sai nhiều, thiếu thông tin quan trọng.
1 — Sai: Hoàn toàn sai hoặc bịa đặt (hallucination).

Trả về JSON duy nhất (không markdown):
{{"score": <số nguyên 1-5>, "reasoning": "<lý do ngắn gọn 1 câu>"}}
"""


async def _call_openai_judge(model: str, question: str, answer: str, ground_truth: str) -> Dict[str, Any]:
    """Gọi 1 OpenAI judge, trả về {score, reasoning, input_tokens, output_tokens}."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI()
    prompt = _JUDGE_PROMPT.format(
        question=question, ground_truth=ground_truth, answer=answer
    )
    response = await client.chat.completions.create(
        model=model,
        max_tokens=128,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response.choices[0].message.content.strip()
    try:
        parsed = json.loads(raw)
        score = int(parsed.get("score", 3))
        reasoning = parsed.get("reasoning", "")
    except (json.JSONDecodeError, ValueError):
        score = 3
        reasoning = f"[parse error] raw: {raw[:80]}"

    score = max(1, min(5, score))
    return {
        "score": score,
        "reasoning": reasoning,
        "input_tokens": response.usage.prompt_tokens,
        "output_tokens": response.usage.completion_tokens,
    }


def _simulate_judge(model: str, question: str, answer: str, ground_truth: str) -> Dict[str, Any]:
    """Fallback khi không có API key."""
    import random
    rng = random.Random(hash(question + answer) & 0xFFFF)
    score = rng.choices([3, 4, 4, 5, 2], k=1)[0]
    return {"score": score, "reasoning": f"[simulation] {model}", "input_tokens": 200, "output_tokens": 30}


def _compute_cost(model: str, in_tok: int, out_tok: int) -> float:
    rates = _COST.get(model, {"input": 1.0, "output": 5.0})
    return (in_tok * rates["input"] + out_tok * rates["output"]) / 1_000_000


class LLMJudge:
    """
    Consensus Judge: gemini-2.0-flash (Judge A) + gpt-4o (Judge B).
    - Agreement Rate: 1.0 nếu |score_A - score_B| <= 1, else 0.5
    - Conflict resolution khi |diff| > 1: lấy điểm thấp hơn (conservative)
    - Position bias check: swap thứ tự response A/B để phát hiện thiên vị vị trí
    """

    JUDGE_A = "gpt-4o-mini"
    JUDGE_B = "gpt-4o"

    def __init__(self):
        self._has_openai = bool(os.getenv("OPENAI_API_KEY"))

    async def evaluate_multi_judge(
        self, question: str, answer: str, ground_truth: str
    ) -> Dict[str, Any]:
        """Chạy song song 2 judge, tính consensus."""
        if self._has_openai:
            result_a, result_b = await asyncio.gather(
                _call_openai_judge(self.JUDGE_A, question, answer, ground_truth),
                _call_openai_judge(self.JUDGE_B, question, answer, ground_truth),
            )
        else:
            result_a = _simulate_judge(self.JUDGE_A, question, answer, ground_truth)
            result_b = _simulate_judge(self.JUDGE_B, question, answer, ground_truth)

        score_a = result_a["score"]
        score_b = result_b["score"]
        diff = abs(score_a - score_b)

        agreement_rate = 1.0 if diff <= 1 else 0.5

        # Conflict resolution: chênh > 1 điểm → conservative (lấy điểm thấp hơn)
        if diff > 1:
            final_score = float(min(score_a, score_b))
            conflict_resolved = True
        else:
            final_score = (score_a + score_b) / 2.0
            conflict_resolved = False

        cost_a = _compute_cost(self.JUDGE_A, result_a["input_tokens"], result_a["output_tokens"])
        cost_b = _compute_cost(self.JUDGE_B, result_b["input_tokens"], result_b["output_tokens"])

        return {
            "final_score": round(final_score, 2),
            "agreement_rate": agreement_rate,
            "conflict_resolved": conflict_resolved,
            "individual_scores": {
                self.JUDGE_A: score_a,
                self.JUDGE_B: score_b,
            },
            "reasoning": {
                self.JUDGE_A: result_a["reasoning"],
                self.JUDGE_B: result_b["reasoning"],
            },
            "cost_usd": round(cost_a + cost_b, 6),
            "tokens": {
                self.JUDGE_A: {"in": result_a["input_tokens"], "out": result_a["output_tokens"]},
                self.JUDGE_B: {"in": result_b["input_tokens"], "out": result_b["output_tokens"]},
            },
        }

    async def check_position_bias(
        self, question: str, answer_a: str, answer_b: str, ground_truth: str
    ) -> Dict[str, Any]:
        """
        Position bias check: đánh giá (A, B) rồi đánh giá (B, A).
        Nếu judge đổi lựa chọn khi swap vị trí → có position bias.
        """
        if not self._has_openai:
            return {"bias_detected": False, "note": "simulation mode"}


        from openai import AsyncOpenAI
        client = AsyncOpenAI()

        async def _ask(resp1: str, resp2: str) -> int:
            prompt = (
                f"Câu hỏi: {question}\nGround Truth: {ground_truth}\n"
                f"Câu trả lời 1: {resp1}\nCâu trả lời 2: {resp2}\n"
                "Câu nào tốt hơn? JSON: {\"better\": 1 hoặc 2}"
            )
            msg = await client.chat.completions.create(
                model=self.JUDGE_A,
                max_tokens=32,
                response_format={"type": "json_object"},
                messages=[{"role": "user", "content": prompt}],
            )
            try:
                return int(json.loads(msg.choices[0].message.content)["better"])
            except Exception:
                return 1

        pref_ab, pref_ba = await asyncio.gather(
            _ask(answer_a, answer_b),
            _ask(answer_b, answer_a),
        )
        consistent = (pref_ab == 1 and pref_ba == 2) or (pref_ab == 2 and pref_ba == 1)
        return {
            "bias_detected": not consistent,
            "pref_order_AB": pref_ab,
            "pref_order_BA": pref_ba,
        }
