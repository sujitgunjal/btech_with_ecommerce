"""Environment-backed settings shared by the shop API and payment gateway."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    fault_injection_enabled: bool = False
    database_url: str = "postgresql+psycopg://shop:shop@ecommerce-postgres:5432/shop"
    jwt_secret: str = "change-me"
    jwt_expire_minutes: int = 180
    payment_service_url: str = ""
    payment_shared_secret: str = ""
    payment_timeout_seconds: float = 2.0
    internal_fault_token: str = ""
    ops_username: str = ""
    ops_password: str = ""
    cors_origins: str = "http://localhost:5174,http://localhost:8088"
    otel_exporter_otlp_endpoint: str = ""
    otel_service_name: str = "ecommerce-shop-api"
    deployment_environment: str = "development"
    db_pool_size: int = 5
    db_max_overflow: int = 0
    db_pool_timeout: float = 2.0
    internal_base_url: str = "http://127.0.0.1:8000"
    load_test_email: str = "loadbot@northline.shop"
    load_test_password: str = "LoadbotPass123!"
    scenario_catalogue_path: str = ""
    investigation_api_url: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
