"""Settings, read from environment variables and the .env file."""

import re
from functools import lru_cache
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # postgresql+psycopg://user:password@host:port/database
    database_url: str

    # "openai" for the hosted model, "local" for sentence-transformers, "fake" for tests.
    embedding_provider: Literal["openai", "local", "fake"] = "openai"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    embedding_price_per_million_tokens: float = 0.02  # USD, for cost estimates only
    openai_api_key: SecretStr | None = None

    edgar_user_agent: str = ""

    @property
    def chunks_table(self) -> str:
        """One table per embedding configuration, e.g. chunks_text_embedding_3_small_1536.

        Vectors from different models are not comparable, so they never share a table.
        It also lets two configurations sit side by side for the ablation table.
        """
        model = re.sub(r"[^a-z0-9]+", "_", self.embedding_model.lower()).strip("_")[:40]
        return f"chunks_{model}_{self.embedding_dimensions}"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # database_url comes from the environment
