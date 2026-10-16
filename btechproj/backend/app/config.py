"""Application configuration loaded from environment variables."""

import os
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Backend settings."""

    # Database
    DATABASE_URL: str = "postgresql+psycopg://postgres:1235@postgres:5432/devops_db"

    # Observability endpoints
    PROMETHEUS_URL: str = "http://prometheus:9090"
    LOKI_URL: str = "http://loki:3100"
    JAEGER_URL: str = "http://jaeger:16686"

    # Collector settings
    COLLECTOR_TIMEOUT: float = 2.0

    # LLM settings (Ollama with Gemma 4)
    LLM_MODEL: str = "gemma4:31b-cloud"
    LLM_API_KEY: str = "ollama"
    LLM_BASE_URL: str = "http://host.docker.internal:11434/v1"
    LLM_TEMPERATURE: float = 0.2
    LLM_MAX_TOKENS: int = 3000

    # RAG settings
    RAG_TOP_K: int = 3
    EMBEDDING_MODEL: str = "all-MiniLM-L6-v2"

    model_config = {"env_file": ".env", "case_sensitive": True}


def get_settings() -> Settings:
    """Return application settings."""
    return Settings()
