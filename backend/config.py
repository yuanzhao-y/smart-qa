from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LLM API
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"

    # Embedding model
    embedding_model: str = "paraphrase-multilingual-MiniLM-L12-v2"

    # Vector store
    chroma_persist_dir: str = "./data/chroma"

    # Text splitting (no overlap to avoid confusing repetition)
    chunk_size: int = 500
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
