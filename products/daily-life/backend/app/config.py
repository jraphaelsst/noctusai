"""Daily Life configuration — extends seed framework."""
from noctusai_seed import ProductSettings


class DailyLifeSettings(ProductSettings):
    cors_origins: str = "http://localhost:8005,http://localhost:8110,http://localhost:5173,http://localhost:3000"


settings = DailyLifeSettings()
