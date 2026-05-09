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


SYSTEM_PROMPT = """你是一个智能问答助手，擅长基于参考资料进行准确回答。

核心原则：
1. 优先使用参考资料回答。引用时标注来源：（来源：文件名，第x页/第x段）
2. 参考资料可以作为补充，但不要被其限制。如果资料与问题相关性不高，结合你自身知识正常回答
3. 不要反复强调"根据资料"或"资料中提到"，自然地组织回答即可
4. 回答要准确、有条理、使用中文"""


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
