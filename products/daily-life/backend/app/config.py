"""Daily Life configuration — extends seed framework."""
from noctusai_seed import ProductSettings


class DailyLifeSettings(ProductSettings):
    cors_origins: str = "@registry:own:daily-life"


settings = DailyLifeSettings()
