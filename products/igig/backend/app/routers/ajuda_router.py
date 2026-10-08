"""Assistente de ajuda do IgIg — the always-available help-chat bubble.

  POST /api/ajuda/chat        (SSE stream; auth required)
  POST /api/ajuda/avaliacao   (end-of-attendance rating 1-5, 204; auth required)

Consumer #1 of the seed organ `noctusai_lib.domain.help_chat`. Everything
behavioural (preamble, streaming, error mapping, rate limit, prompt caching,
conversation storage + rating) lives in the seed; this module only binds
IgIg's auth tuple `(user, token, org_id)` and the product knowledge guide.

The guide (`app/knowledge/guia-igig.md`) is the assistant's ENTIRE knowledge:
when a page or rule changes, the guide changes in the same commit — a stale
guide makes the assistant confidently describe behaviour that no longer
exists. It is loaded once at import; a missing/empty file fails startup.
"""
from pathlib import Path

from noctusai_lib.domain.help_chat import create_help_chat_router, make_help_chat_store

from app import database
from app.dependencies import coerce_org_uuid, get_current_user_org

GUIA_PATH = Path(__file__).resolve().parent.parent / "knowledge" / "guia-igig.md"

router = create_help_chat_router(
    product_name="IgIg",
    product_slug="igig",
    knowledge_path=GUIA_PATH,
    # Conversations are stored in `public.help_chat_*` (service role only,
    # readable by the NoctusAI platform team) - hence the CORE client, not
    # the igig-schema admin client.
    store=make_help_chat_store(client_fn=lambda: database._db.get_core_client()),
    auth_dependency=get_current_user_org,
    org_id_from_auth=lambda auth: str(coerce_org_uuid(auth[2])),
    user_id_from_auth=lambda auth: str(auth[0].id),
    model="claude-haiku-4-5",
)
