import os
from pathlib import Path
from typing import List, Optional, Dict, Any
import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class RepositoryConfig(BaseModel):
    path: str
    name: Optional[str] = None


class SchedulerConfig(BaseModel):
    full_index_cron: str = "0 2 * * *"
    incremental_cron: str = "*/15 * * * *"
    polling_interval_minutes: int = 15
    staleness_check_minutes: int = 30


class EmbeddingConfig(BaseModel):
    provider: str = "mock"
    model: str = "nomic-embed-text"
    fallback_provider: str = "openai"
    dimension: int = 768
    ollama_url: Optional[str] = "http://127.0.0.1:11434"
    openai_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None


class VectorStoreConfig(BaseModel):
    backend: str = "lancedb"
    path: str = ".repolens/vectors"


class DatabaseConfig(BaseModel):
    url: str = "sqlite+aiosqlite:///.repolens/repolens.db"


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8420
    mcp_transport: str = "stdio"


class AlertThresholds(BaseModel):
    mcp_latency_p95_ms: int = 2000
    pipeline_duration_warn_s: int = 300
    embedding_error_rate_pct: int = 5


class ObservabilityConfig(BaseModel):
    enable_prometheus: bool = True
    metrics_port: int = 9090
    enable_dashboard: bool = True
    log_level: str = "INFO"
    alert_thresholds: AlertThresholds = Field(default_factory=AlertThresholds)


class RepoLensSettings(BaseSettings):
    repositories: List[RepositoryConfig] = Field(default_factory=list)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    vector_store: VectorStoreConfig = Field(default_factory=VectorStoreConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)

    model_config = SettingsConfigDict(
        env_prefix="REPOLENS_",
        env_nested_delimiter="__",
        env_file=".env",
        extra="ignore"
    )

    @classmethod
    def load(cls, config_path: str = "config.yaml") -> "RepoLensSettings":
        config_data: Dict[str, Any] = {}
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                yaml_data = yaml.safe_load(f)
                if yaml_data:
                    config_data.update(yaml_data)

        # Merge with environment variables via pydantic-settings
        return cls(**config_data)
