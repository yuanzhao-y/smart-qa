"""Document summarization using LLM."""

import logging

from backend.llm import _get_client
from backend.config import settings

logger = logging.getLogger("smartqa")

SUMMARY_PROMPT = """请分析以下文档内容，返回一个 JSON 格式的摘要，包含以下字段：
1. "summary": 文档核心内容摘要（150-200字）
2. "keywords": 5-8个关键词（数组）
3. "topics": 3-5个主要主题/章节（数组）
4. "doc_type": 文档类型（如：技术文档、学术论文、教程、报告、法律文件、其他）

只返回 JSON，不要添加任何其他文字或 markdown 标记。

文档内容：
{content}"""


def generate_summary(chunks: list[dict], max_chars: int = 6000) -> dict:
    """Generate document summary from chunks.

    Args:
        chunks: List of document chunks with 'content' key.
        max_chars: Maximum characters to send to LLM.

    Returns:
        Dict with summary, keywords, topics, doc_type fields.
    """
    if not chunks:
        return _empty_summary()

    # Concatenate chunks up to max_chars
    content = ""
    for chunk in chunks:
        text = chunk["content"]
        if len(content) + len(text) + 2 > max_chars:
            # Add partial text to fill remaining space
            remaining = max_chars - len(content) - 2
            if remaining > 100:
                content += "\n" + text[:remaining]
            break
        content += "\n" + text if content else text

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=settings.llm_model,
            messages=[{"role": "user", "content": SUMMARY_PROMPT.format(content=content)}],
            temperature=0.2,
            max_tokens=800,
        )
        text = response.choices[0].message.content.strip()

        # Parse JSON response (handle markdown code blocks)
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

        import json
        result = json.loads(text)

        # Validate fields
        return {
            "summary": str(result.get("summary", "")),
            "keywords": list(result.get("keywords", []))[:8],
            "topics": list(result.get("topics", []))[:5],
            "doc_type": str(result.get("doc_type", "其他")),
        }

    except Exception as e:
        logger.warning(f"[摘要] 生成失败: {e}")
        return _empty_summary()


def _empty_summary() -> dict:
    return {
        "summary": "",
        "keywords": [],
        "topics": [],
        "doc_type": "其他",
    }
