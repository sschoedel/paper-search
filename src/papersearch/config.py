"""Configuration management for papersearch."""

import os
from pathlib import Path
from typing import Literal, Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Zotero API
    zotero_library_id: Optional[str] = None
    zotero_library_type: str = "user"  # or "group"
    zotero_api_key: Optional[str] = None

    # LLM API Keys
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None

    # Summarization
    summarization_enabled: bool = True
    summarization_model: str = "claude-3-haiku-20240307"

    # Embeddings
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    # Collection
    collection_hour: int = 9
    lookback_hours: int = 24

    # Rate Limits (requests per second)
    arxiv_rate_limit: float = 1.0
    llm_rate_limit: float = 10.0

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    def get_llm_provider(self) -> Literal["anthropic", "openai"]:
        """Determine which LLM provider to use based on model name."""
        if "claude" in self.summarization_model.lower():
            return "anthropic"
        elif "gpt" in self.summarization_model.lower():
            return "openai"
        else:
            raise ValueError(f"Unknown model type: {self.summarization_model}")

    def get_embedding_provider(self) -> Literal["local", "openai"]:
        """Determine which embedding provider to use based on model name."""
        if self.embedding_model.startswith("sentence-transformers/"):
            return "local"
        elif "text-embedding" in self.embedding_model:
            return "openai"
        else:
            return "local"

    def validate_api_keys(self) -> None:
        """Validate that required API keys are present."""
        # Zotero credentials
        if not self.zotero_library_id:
            raise ValueError("ZOTERO_LIBRARY_ID required")
        if not self.zotero_api_key:
            raise ValueError("ZOTERO_API_KEY required")

        # LLM credentials (only needed if summarization is enabled)
        if self.summarization_enabled:
            llm_provider = self.get_llm_provider()
            if llm_provider == "anthropic" and not self.anthropic_api_key:
                raise ValueError("ANTHROPIC_API_KEY required for Claude models")
            if llm_provider == "openai" and not self.openai_api_key:
                raise ValueError("OPENAI_API_KEY required for OpenAI models")


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get or create global settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """Reload settings from environment (useful for testing)."""
    global _settings
    _settings = Settings()
    return _settings
