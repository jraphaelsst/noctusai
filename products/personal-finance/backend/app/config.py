"""Personal Finance configuration — extends seed framework."""
from noctusai_seed import ProductSettings


class PFSettings(ProductSettings):
    cors_origins: str = "http://localhost:8090,http://localhost:5173,http://localhost:3000"


settings = PFSettings()
