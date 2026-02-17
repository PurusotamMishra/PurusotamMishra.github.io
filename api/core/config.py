from pydantic import ConfigDict
from pydantic_settings import BaseSettings
import os
from pathlib import Path

class Settings(BaseSettings):
    APP_NAME: str = "Bloo-Agent-API"
    APP_ENV: str = "development"
    APP_PORT: int = 80
    DEBUG: bool = True

    # Logging settings
    LOG_LEVEL: str = "info"
    LOG_DIR: str = os.path.join(Path(__file__).parents[2], "logs")
    
    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",  # Allow extra variables in .env file
    )
    
    
settings = Settings()