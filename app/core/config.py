"""Typed application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Groq / LLM (OpenAI-API-compatible)
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    llm_model: str = "openai/gpt-oss-120b"
    llm_temperature: float = 0
    # "" = do not send reasoning_effort; "low"/"medium"/"high" to enable.
    # When set, response_format={"type":"json_object"} is suppressed because
    # Groq's reasoning models reject the combination.
    llm_reasoning_effort: str = "low"
    llm_timeout_seconds: int = 10
    llm_max_retries: int = 2
    llm_mock: bool = False

    # App
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"

    # Cache
    cache_ttl_seconds: int = 300
    cache_max_entries: int = 512


settings = Settings()
