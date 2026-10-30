from functools import lru_cache
from pathlib import Path
from typing import Literal
from decimal import Decimal
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HELM_", env_file=str(ROOT / ".env"), extra="ignore")
    mode: Literal["demo"] = "demo"
    clock_mode: Literal["demo", "live"] = "demo"
    partner_mode: Literal["simulator", "core"] = "simulator"
    secret_key: str = Field(
        default="local-demo-only-change-before-live-64-characters-helm-broker-portal", min_length=32
    )
    core_api_url: str = "http://127.0.0.1:8011"
    core_webhook_secret: str = "demo-webhook-secret-change-before-live"
    core_client_id: str = "helm-broker-demo"
    core_client_secret: str = "demo-core-client-secret"
    core_delivery_enabled: bool = False
    llm_provider: str = "groq"
    llm_api_key: str = ""
    llm_model: str = "groq/llama-3.3-70b-versatile"
    llm_allowed_providers: list[str] = ["groq", "anthropic"]
    llm_region: str = "unverified"
    llm_token_budget: int = 20000
    llm_daily_token_budget: int = 1000000
    llm_enabled: bool = False
    min_quotes: int = 3
    min_new_comparisons: int = 30
    demo_clock_multiplier: int = 2700
    agents_paused: bool = False
    rp_id: str = "localhost"
    auth_rate_limit: int = 5
    shadow_case_minimum: int = 20
    db_pool_size: int = 20
    db_pool_overflow: int = 20
    otlp_endpoint: str = ""
    database_url: str = f"sqlite:///{(ROOT / '.runtime/broker.db').as_posix()}"
    redis_url: str = "redis://127.0.0.1:56389/0"
    encryption_key: str = ""
    cookie_secure: bool = False
    allowed_origin: str = "http://127.0.0.1:5180"
    ipt_rate: str = "0.12"
    demo_delay_seconds: int = 8
    session_hours: int = 8
    jwt_private_key: SecretStr | None = None
    jwt_signing_key_file: str = str(ROOT / ".runtime/auth-signing.pem")
    account_lock_minutes: int = 15
    agent_runtime: Literal["python", "crewai"] = "python"

    @property
    def trusted_origins(self):
        from urllib.parse import urlsplit, urlunsplit

        origin = urlsplit(self.allowed_origin)
        values = [self.allowed_origin]
        if self.clock_mode == "demo" and origin.hostname in ("localhost", "127.0.0.1"):
            host = "localhost" if origin.hostname == "127.0.0.1" else "127.0.0.1"
            values.append(
                urlunsplit((origin.scheme, f"{host}:{origin.port}" if origin.port else host, "", "", ""))
            )
        return values

    @property
    def ipt_standard_rate(self) -> Decimal:
        return Decimal(self.ipt_rate)

    @model_validator(mode="after")
    def check_live_configuration(self):
        if self.clock_mode == "live" and (
            "demo" in self.secret_key
            or not self.encryption_key
            or not self.cookie_secure
            or not self.jwt_private_key
        ):
            raise ValueError("Live mode requires non-demo secrets, field encryption and secure cookies")
        if not 0 <= Decimal(self.ipt_rate) <= 1:
            raise ValueError("Invalid IPT rate")
        return self


@lru_cache
def settings():
    (ROOT / ".runtime").mkdir(exist_ok=True)
    return Settings()
