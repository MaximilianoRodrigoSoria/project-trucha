from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """Configuración de la aplicación."""
    # Directorios
    pdf_path: str = "/files/input-pdf"
    md_path: str = "/files/md-files"

    model_config = SettingsConfigDict(
        env_file= ".env",
        case_sensitive=False
    )

settings = Settings()