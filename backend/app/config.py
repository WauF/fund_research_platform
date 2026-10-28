"""Runtime settings, read from environment variables (and backend/../.env when run locally)."""

from functools import cache

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")

    postgres_user: str = "fund"
    postgres_password: str = ""
    postgres_db: str = "fund_platform"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    s3_endpoint_url: str = "http://localhost:8333"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = "documents"
    # SeaweedFS ignores the region, but SigV4 signing needs one.
    s3_region: str = "us-east-1"

    max_upload_mb: int = 50

    @property
    def database_url(self) -> URL:
        return URL.create(
            "postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )


@cache
def get_settings() -> Settings:
    return Settings()
