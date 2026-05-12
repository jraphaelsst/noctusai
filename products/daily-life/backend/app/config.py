"""Daily Life configuration — extends seed framework."""
from noctusai_seed import ProductSettings


class DailyLifeSettings(ProductSettings):
    cors_origins: str = "@registry:own:daily-life"

    # Optional Postgres URL for SQLAlchemy-bound flows (tool-call audit-hook
    # write side effects). Empty → `app.services.audit_hook.get_audit_writer`
    # returns a noop writer (debug-log + skip). Primary data path stays on
    # the Supabase admin client; SQLAlchemy is a SECONDARY surface used only
    # by the seed `make_audit_writer(db, table_class)` contract.
    postgres_url: str = ""


settings = DailyLifeSettings()
