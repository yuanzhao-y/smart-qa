from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LLM API
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"

    # Embedding model — use a strong Chinese model for better retrieval
    embedding_model: str = "BAAI/bge-small-zh-v1.5"

    # Vector store
    chroma_persist_dir: str = "./data/chroma"

    # Text splitting
    chunk_size: int = 500
    chunk_overlap: int = 50
    # Chunking strategy: "fixed" (separator-based) or "semantic" (embedding-based)
    chunk_strategy: str = "fixed"

    # Retrieval
    top_k: int = 5

    # Reranker
    enable_rerank: bool = True
    reranker_model: str = "BAAI/bge-reranker-base"
    rerank_top_n: int = 5

    class Config:
        env_file = ".env"


settings = Settings()
