"""Personal Finance configuration — extends seed framework."""
from noctusai_seed import ProductSettings


class PFSettings(ProductSettings):
    cors_origins: str = "@registry:own:personal-finance"


settings = PFSettings()
