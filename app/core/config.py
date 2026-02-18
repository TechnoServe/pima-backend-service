from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "MyPIMA API"
    environment: str = Field(default="dev")
    api_prefix: str = "/api/v1"

    database_url: str = Field(alias="DATABASE_URL")
    db_schema: str = Field(default="pima", alias="DB_SCHEMA")
    jwt_secret: str = Field(alias="JWT_SECRET")
    jwt_algorithm: str = "HS256"
    access_token_exp_minutes: int = 60 * 12  # 12h

    cors_origins: str = "*"  # comma-separated list or '*'
    gcp_project_id: str
    gcs_bucket_name: str

    commcare_username: str | None = Field(default=None, alias="COMMCARE_USERNAME")
    commcare_password: str | None = Field(default=None, alias="COMMCARE_PASSWORD")
    commcare_base_url: str | None = Field(default=None, alias="COMMCARE_BASE_URL")

settings = Settings()
