from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Configuración de la aplicación."""
    # Directorios
    pdf_path: str = "/files/input-pdf"
    md_path: str = "/files/md-files"

    # Logging
    log_level: str = "DEBUG"

    # Embedding
    EMBED_MODEL: str = "BAAI/bge-m3"
    MAX_TOKENS: int = 512
    BATCH_SIZE: int = 64

    model_config = SettingsConfigDict(
        env_file= ".env",
        case_sensitive=False
    )

settings = Settings()