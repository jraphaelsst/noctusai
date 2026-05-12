"""
YouTube Crawler configuration.

Extends the framework's ProductSettings with the Phase 1 credentials fields
(Google OAuth client + Fernet vault key). All three are optional at
construction time — empty strings drop the router into FakeOAuthProvider
mode so the rest of the product wires + tests work before real Google
credentials are provisioned.
"""
from noctusai_seed import ProductSettings


class SeedSettings(ProductSettings):
    """YouTube Crawler specific settings.

    Phase 1 (`youtube-crawler-domain-implementation`) added three OAuth-shaped
    fields. They default to "" so unit tests don't need the real values and so
    the product boots without them (the credentials router degrades to
    `FakeOAuthProvider` until both client_id + client_secret are present).
    """

    cors_origins: str = "@registry:own:youtube-crawler"

    # ─── Phase 1 ─ Google OAuth + Fernet vault ──────────────────────────────
    #
    # The vault key is generated out-of-band:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # and dropped into `.env` as `YOUTUBE_CRAWLER_VAULT_KEY=…`. NEVER commit.
    #
    # Google OAuth credentials come from Google Cloud Console → APIs &
    # Services → Credentials → OAuth 2.0 Client IDs (type "Web application").
    youtube_crawler_vault_key: str = ""
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""


settings = SeedSettings()
