"""Multi-turn conversation history compression."""

import logging

from backend.llm import _get_client
from backend.config import settings

logger = logging.getLogger("smartqa")

COMPRESS_PROMPT = """请将以下对话历史压缩为一段简洁的摘要，保留关键信息（用户的问题主题、重要的结论、提到的文件名等）。

对话历史：
{history}

要求：
1. 只输出摘要内容，不要添加任何前缀或解释
2. 摘要控制在200字以内
3. 保留对话的核心主题和关键结论"""

# Thresholds
MAX_HISTORY_MESSAGES = 10  # Compress when history exceeds this
KEEP_RECENT = 4  # Always keep this many recent messages


def needs_compression(history: list[dict]) -> bool:
    """Check if history needs compression."""
    return len(history) > MAX_HISTORY_MESSAGES


def compress_history(history: list[dict]) -> list[dict]:
    """Compress old history into a summary, keep recent messages intact.

    Args:
        history: Full conversation history [{role, content}].

    Returns:
        Compressed history with summary prepended.
    """
    if not needs_compression(history):
        return history

    # Split into old (to compress) and recent (to keep)
    old_messages = history[:-KEEP_RECENT]
    recent_messages = history[-KEEP_RECENT:]

    # Build history text
    history_text = ""
    for msg in old_messages:
        role = "用户" if msg["role"] == "user" else "助手"
        content = msg["content"][:500]  # Truncate very long messages
        history_text += f"{role}：{content}\n"

    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=settings.llm_model,
            messages=[{"role": "user", "content": COMPRESS_PROMPT.format(history=history_text)}],
            temperature=0.2,
            max_tokens=300,
        )
        summary = response.choices[0].message.content.strip()
        logger.info(f"[压缩] 对话历史已压缩: {len(old_messages)} 条 → 摘要")

        # Build compressed history
        compressed = [{"role": "system", "content": f"以下是之前对话的摘要：\n{summary}"}]
        compressed.extend(recent_messages)
        return compressed

    except Exception as e:
        logger.warning(f"[压缩] 对话压缩失败，使用原始历史: {e}")
        return history
