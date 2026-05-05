"""Answer quality evaluation using LLM-as-Judge."""

import json
import logging

from backend.llm import _get_client
from backend.config import settings

logger = logging.getLogger("smartqa")

EVAL_PROMPT = """你是一个答案质量评估专家。请评估以下问答的质量。

评估维度（每项1-5分）：
1. faithfulness（忠实度）：回答是否忠实于提供的参考资料，没有编造信息
2. relevance（相关性）：回答是否与用户问题相关，是否切中要害
3. completeness（完整性）：回答是否完整，是否遗漏了参考资料中的重要信息

参考资料：
{context}

用户问题：{question}
AI回答：{answer}

请返回 JSON 格式，只包含以下字段，不要添加任何其他文字：
{{
    "faithfulness": <1-5>,
    "relevance": <1-5>,
    "completeness": <1-5>,
    "overall": <1-5>,
    "reason": "<简短评价，50字以内>"
}}"""


def evaluate_answer(question: str, answer: str, docs: list[dict]) -> dict:
    """Evaluate answer quality using LLM-as-Judge.

    Args:
        question: The user's question.
        answer: The AI-generated answer.
        docs: The retrieved document chunks used as context.

    Returns:
        Dict with faithfulness, relevance, completeness, overall scores and reason.
    """
    if not answer or not docs:
        return _default_eval()

    # Build context from docs
    context_parts = []
    for i, doc in enumerate(docs[:5]):  # Limit to 5 docs for evaluation
        src = doc["metadata"].get("source", "未知")
        context_parts.append(f"[{i+1}] (来源: {src})\n{doc['content']}")
    context = "\n\n".join(context_parts)

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=settings.llm_model,
            messages=[{
                "role": "user",
                "content": EVAL_PROMPT.format(
                    context=context,
                    question=question,
                    answer=answer[:2000],  # Truncate long answers
                )
            }],
            temperature=0.1,
            max_tokens=300,
        )
        text = response.choices[0].message.content.strip()

        # Parse JSON (handle markdown code blocks)
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        result = json.loads(text)

        # Validate and clamp scores
        return {
            "faithfulness": _clamp(result.get("faithfulness", 3)),
            "relevance": _clamp(result.get("relevance", 3)),
            "completeness": _clamp(result.get("completeness", 3)),
            "overall": _clamp(result.get("overall", 3)),
            "reason": str(result.get("reason", ""))[:100],
        }

    except Exception as e:
        logger.warning(f"[评估] 答案评估失败: {e}")
        return _default_eval()


def _clamp(value, min_val=1, max_val=5) -> int:
    try:
        return max(min_val, min(max_val, int(value)))
    except (TypeError, ValueError):
        return 3


def _default_eval() -> dict:
    return {
        "faithfulness": 0,
        "relevance": 0,
        "completeness": 0,
        "overall": 0,
        "reason": "评估不可用",
    }
