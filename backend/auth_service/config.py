from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_HOST: str
    POSTGRES_PORT: int = 5432

    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    SMTP_SERVER: str
    SMTP_PORT: int
    SMTP_USER: str
    SMTP_PASSWORD: str
    EMAIL_PROVIDER: str = "smtp"
    BREVO_API_KEY: str = ""
    BREVO_API_URL: str = "https://api.brevo.com/v3/smtp/email"
    RESEND_API_KEY: str = ""
    RESEND_API_URL: str = "https://api.resend.com/emails"
    EMAILS_FROM_EMAIL: str
    APP_PUBLIC_URL: str = "http://localhost:5173"

    MARKETPLACE_SERVICE_URL: str = "http://host.docker.internal:8002"
    FAVORITES_REFRESH_POLL_SECONDS: int = 60
    FAVORITES_REFRESH_BATCH_SIZE: int = 50
    FAVORITES_REFRESH_CONCURRENCY: int = 3
    FAVORITES_HISTORY_RETENTION_DAYS: int = 30
    FAVORITES_MARKETPLACE_TIMEOUT_SECONDS: int = 15

    @property
    def DATABASE_URL(self):
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

settings = Settings()
