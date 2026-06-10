from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # LLM provider — swap model or base URL here (or in .env) with no code changes
    ollama_base_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "qwen2.5-coder:7b"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # Scan limits
    max_parallel_scans: int = 5
    result_ttl_seconds: int = 86400  # 24h
    scan_job_timeout_seconds: int = 300  # max time before an in-flight scan is considered abandoned


settings = Settings()
