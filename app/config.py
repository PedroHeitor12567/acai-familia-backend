from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PREFIXO_SEGREDO_EXEMPLO = "troque-por"  # valor placeholder do .env.example


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"
    database_url: str
    secret_key: str = Field(min_length=32)
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    cors_origins: list[str] = []
    login_max_attempts: int = 5
    login_lockout_seconds: int = 300
    max_body_bytes: int = 1_000_000

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @model_validator(mode="after")
    def _segredo_nao_pode_ser_o_do_exemplo(self) -> Self:
        if self.is_production and self.secret_key.startswith(_PREFIXO_SEGREDO_EXEMPLO):
            raise ValueError("SECRET_KEY de produção não pode ser o valor de .env.example")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
