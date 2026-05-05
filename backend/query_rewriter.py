"""Query rewriting using HyDE (Hypothetical Document Embeddings)."""

import logging

from backend.llm import _get_client
from backend.config import settings

logger = logging.getLogger("smartqa")

REWRITE_PROMPT = """你是一个检索优化助手。用户的原始问题可能太模糊或太宽泛，不利于检索。

请将用户的问题改写为 2-3 个更具体、更适合检索的子问题。每个子问题单独一行，不要编号，不要解释。

示例：
用户问题：数据结构怎么学
改写：
数据结构的学习路线和方法
数据结构各章节的重点内容
数据结构考研复习建议

现在请改写：
用户问题：{question}
改写："""


HYDE_PROMPT = """请根据以下问题，写一段简短的、可能出现在教科书中的回答（100字左右）。不需要准确，只需要风格和内容像教科书即可。

问题：{question}
回答："""


def rewrite_query(question: str) -> list[str]:
    """Rewrite a question into multiple specific sub-questions."""
    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=settings.llm_model,
            messages=[{"role": "user", "content": REWRITE_PROMPT.format(question=question)}],
            temperature=0.3,
            max_tokens=300,
        )
        text = response.choices[0].message.content.strip()
        sub_queries = [q.strip() for q in text.split("\n") if q.strip()]
        return sub_queries if sub_queries else [question]
    except Exception as e:
        logger.warning(f"[HyDE] 查询改写失败，使用原始问题: {e}")
        return [question]


def hyde_rewrite(question: str) -> str:
    """Generate a hypothetical answer to use for retrieval (HyDE)."""
    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=settings.llm_model,
            messages=[{"role": "user", "content": HYDE_PROMPT.format(question=question)}],
            temperature=0.5,
            max_tokens=200,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.warning(f"[HyDE] 假设性回答生成失败，使用原始问题: {e}")
        return question
