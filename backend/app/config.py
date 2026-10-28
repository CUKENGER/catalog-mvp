from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False)

    database_url: str
    internal_api_token: str

    s3_endpoint_url: str
    s3_public_base_url: str
    s3_bucket: str = "catalog"
    s3_access_key: str
    s3_secret_key: str

    max_image_size_bytes: int = 8 * 1024 * 1024


settings = Settings()
