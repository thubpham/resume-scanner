import os
from pathlib import Path
import sys
import logging
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional, Literal

# Use PROJECT_ROOT for better path resolution
PROJECT_ROOT = Path(__file__).parent.parent

class Settings(BaseSettings):
    # The defaults here are just hardcoded to have 'something'. 
    PROJECT_NAME: str = "Resume Scanner"
    FRONTEND_PATH: str = os.path.join(os.path.dirname(__file__), "frontend", "assets")
    ALLOWED_ORIGINS: List[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    DB_ECHO: bool = False
    PYTHONDONTWRITEBYTECODE: int = 1
    SYNC_DATABASE_URL: Optional[str] = None
    ASYNC_DATABASE_URL: Optional[str] = None
    SESSION_SECRET_KEY: Optional[str] = None
    LLM_PROVIDER: Optional[str] = "ollama"
    LLM_API_KEY: Optional[str] = None
    LLM_BASE_URL: Optional[str] = None
    LL_MODEL: Optional[str] = "gemma3:4b"
    EMBEDDING_PROVIDER: Optional[str] = "ollama"
    EMBEDDING_API_KEY: Optional[str] = None
    EMBEDDING_BASE_URL: Optional[str] = None
    EMBEDDING_MODEL: Optional[str] = "dengcao/Qwen3-Embedding-0.6B:Q8_0"

    # Updated model_config to use PROJECT_ROOT
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

# DEBUG before creating settings instance

print("----DEBUGGING STARTS HERE----")

env_path = PROJECT_ROOT / ".env"
print(f"DEBUG: Looking for .env at: {env_path}")
print(f"DEBUG: .env exists: {env_path.exists()}")
print(f"DEBUG: PROJECT_ROOT: {PROJECT_ROOT}")
print(f"DEBUG: __file__: {__file__}")

if env_path.exists():
    print(f"DEBUG: .env file content:")
    with open(env_path, "r") as f:
        for line in f:
            if line.strip() and not line.startswith("#"):
                key = line.split("=")[0] if '=' in line else line
                print(f" {key}")

settings = Settings()

# DEBUG: Print after creating settings
print(f"DEBUG: SYNC_DATABASE_URL: {settings.SYNC_DATABASE_URL}")
print(f"DEBUG: ASYNC_DATABASE_URL: {settings.ASYNC_DATABASE_URL}")
print(f"DEBUG: DB_ECHO: {settings.DB_ECHO}")

print("----DEBUGGING ENDS HERE----")

_LEVEL_BY_ENV: dict[Literal["production", "staging", "local"], int] = {
    "production": logging.INFO,
    "staging": logging.DEBUG,
    "local": logging.DEBUG,
}

def setup_logging() -> None:
    """
    Configure the root logger exactly once,

    * Console only (StreamHandler -> stderr)
    * ISO - 8601 timestamps
    * Env - based log level: production -> INFO, else DEBUG
    * Prevents duplicate handler creation if called twice
    """
    root = logging.getLogger()
    if root.handlers:
        return

    env = settings.ENV.lower() if hasattr(settings, "ENV") else "production"
    level = _LEVEL_BY_ENV.get(env, logging.INFO)

    formatter = logging.Formatter(
        fmt="[%(asctime)s - %(name)s - %(levelname)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)

    root.setLevel(level)
    root.addHandler(handler)

    for noisy in ("sqlalchemy.engine", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)