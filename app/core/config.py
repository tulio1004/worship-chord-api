from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Literal


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Server
    port: int = Field(default=8000, alias="PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    environment: str = Field(default="production", alias="ENVIRONMENT")

    # Audio limits
    max_audio_duration_seconds: int = Field(default=600, alias="MAX_AUDIO_DURATION_SECONDS")
    temp_dir: str = Field(default="/tmp/worship_chords", alias="TEMP_DIR")

    # Whisper
    whisper_model_size: str = Field(default="small", alias="WHISPER_MODEL_SIZE")
    whisper_device: str = Field(default="cpu", alias="WHISPER_DEVICE")
    whisper_compute_type: str = Field(default="int8", alias="WHISPER_COMPUTE_TYPE")

    # Features
    enable_llm_cleanup: bool = Field(default=False, alias="ENABLE_LLM_CLEANUP")
    default_language: str = Field(default="en", alias="DEFAULT_LANGUAGE")

    # Chord engine
    chord_engine: Literal["auto", "chordino", "librosa"] = Field(default="auto", alias="CHORD_ENGINE")

    # App version
    version: str = "1.0.0"
    app_name: str = "Worship Chord API"


settings = Settings()
