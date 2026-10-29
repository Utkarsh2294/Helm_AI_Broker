from functools import lru_cache
from pathlib import Path
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HELM_", env_file=str(ROOT / ".env"), extra="ignore")
    mode: Literal["demo"] = "demo"
    database_url: str = f"sqlite:///{(ROOT / '.runtime/broker.db').as_posix()}"
    encryption_key: str = ""
    cookie_secure: bool = False
    allowed_origin: str = "http://127.0.0.1:5180"
    ipt_rate: str = "0.12"
    demo_delay_seconds: int = 8
    session_hours: int = 8
    agent_runtime: Literal["python", "crewai"] = "python"


@lru_cache
def settings():
    (ROOT / ".runtime").mkdir(exist_ok=True)
    return Settings()
