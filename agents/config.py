"""
AI-Mentor Agent Service — Configuration
Centralized settings management via pydantic-settings
"""
from pydantic_settings import BaseSettings
from functools import lru_cache
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    # NVIDIA NIM (OpenAI-compatible free API — replaces Bedrock)
    nvidia_api_key: str = ""
    nvidia_model: str = "meta/llama-3.3-70b-instruct"
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"

    # Database — Supabase
    database_url: str = "postgresql://postgres:password@localhost:5432/ai_mentor"
    supabase_url: str = ""
    supabase_anon_key: str = ""
    pgvector_enabled: bool = True

    # Cache
    redis_url: str = "redis://localhost:6379/0"

    # Service
    agent_service_host: str = "0.0.0.0"
    agent_service_port: int = 8000
    frontend_origin: str = "http://localhost:5173"
    node_api_origin: str = "http://localhost:3001"

    # Privacy
    anonymize_pii: bool = True

    # App
    env: str = "development"
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
