"""LLM integration using OpenAI-compatible API."""

import logging
from openai import OpenAI, APITimeoutError, APIConnectionError
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from backend.config import settings

logger = logging.getLogger(__name__)

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            timeout=30.0,
            max_retries=2,
        )
    return _client


SYSTEM_PROMPT = """你是一个智能问答助手。请根据提供的参考资料回答用户的问题。

规则：
1. 如果参考资料中有相关内容，请基于资料回答，并在相关段落标注来源，格式为：（来源：文件名，第x页/第x段）
2. 如果参考资料中没有相关内容，直接正常回答即可，不要刻意说明内容来源
3. 只有在你完全不确定答案时，才说明"根据现有资料，我无法回答这个问题"
4. 回答要简洁准确，使用中文"""


def build_context(docs: list[dict]) -> str:
    """Build context string from retrieved documents."""
    parts = []
    for i, doc in enumerate(docs):
        meta = doc["metadata"]
        source = meta.get("source", "未知来源")
        page = meta.get("page") or meta.get("paragraph") or meta.get("chunk_index", "")
        parts.append(f"[参考资料{i+1}] (来源: {source}, 第{page}部分)\n{doc['content']}")
    return "\n\n".join(parts)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((APITimeoutError, APIConnectionError)),
    before_sleep=lambda _: logger.warning("LLM 请求超时，正在重试..."),
)
def chat(question: str, docs: list[dict], history: list[dict] = None) -> str:
    """Generate answer based on question and retrieved documents.

    Args:
        question: User's question
        docs: Retrieved relevant documents
        history: Optional conversation history [{role, content}]
    """
    client = _get_client()

    context = build_context(docs)

    user_message = f"""参考资料：
{context}

用户问题：{question}"""

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    if history:
        messages.extend(history)

    messages.append({"role": "user", "content": user_message})

    response = client.chat.completions.create(
        model=settings.llm_model,
        messages=messages,
        temperature=0.3,
        max_tokens=2000,
    )

    return response.choices[0].message.content


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((APITimeoutError, APIConnectionError)),
    before_sleep=lambda _: logger.warning("LLM 请求超时，正在重试..."),
)
def chat_stream(question: str, docs: list[dict], history: list[dict] = None):
    """Stream version of chat() - yields text chunks."""
    client = _get_client()

    context = build_context(docs)

    user_message = f"""参考资料：
{context}

用户问题：{question}"""

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    if history:
        messages.extend(history)

    messages.append({"role": "user", "content": user_message})

    stream = client.chat.completions.create(
        model=settings.llm_model,
        messages=messages,
        temperature=0.3,
        max_tokens=2000,
        stream=True,
    )

    for chunk in stream:
        if chunk.choices[0].delta.content:
            yield chunk.choices[0].delta.content
