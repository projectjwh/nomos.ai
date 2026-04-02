"""Centralized configuration for the PhD Platform."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PHD_", env_file=".env")

    # LLM provider: "anthropic" or "ollama"
    llm_provider: str = "anthropic"

    # Anthropic settings
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"
    anthropic_max_tokens: int = 4096

    # Ollama (local Llama) settings
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"

    # Database
    database_url: str = "sqlite+aiosqlite:///phd_platform.db"

    # Logging
    log_level: str = "INFO"

    # API
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Cost tier routing
    tier2_model: str = "llama3.1:8b"
    tier3_model: str = "claude-sonnet-4-20250514"
    tutoring_provider: str = "ollama"
    defense_provider: str = "anthropic"

    # Assessment thresholds
    weakness_threshold: float = 0.80
    remediation_depth: int = 2
    retest_cooldown_days: int = 7

    # Integrity thresholds
    integrity_timing_min_ratio: float = 0.15
    integrity_max_flags: int = 3
    integrity_concept_match_min: float = 0.40
    integrity_socratic_depth_min: str = "procedural"

    # Auth
    secret_key: str = "change-me-in-production"
    session_max_age: int = 86400  # 24 hours


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
