"""The CLOSED list of WAHA lines social-wiring may provision on, and each line's per-line secrets.

WAHA Core allows ONE session per container, so one WhatsApp number = one container (`deploy/fleet/waha-instances.yml`, THE source of
truth; KB § CONTEXT/INTEGRATIONS/whatsapp.md § One WAHA per number). The list is NOT kept here: it is read from the GENERATED seed
module `noctusai_lib.integrations.whatsapp.declared_lines.DECLARED_LINES` (rendered from the yml; drift is caught by
`check_waha_instances_render_sync`), filtered to `product == "social-wiring"`. A name not listed is refused at provisioning.

Secrets are NOT here: each row names the ENV VARS (`api_key_env`, `hmac_secret_env`) the product container must carry; they are
read per request, never at import. A line resolves ITS row's key and HMAC secret, so two orgs on two instances cannot sign for each
other's webhooks. The legacy shared host (`shared: True`) keeps the product's global `WAHA_API_KEY` / `WAHA_WEBHOOK_HMAC_SECRET`.
"""
import os
from dataclasses import dataclass

PRODUCT = "social-wiring"


@dataclass(frozen=True)
class WahaInstance:
    name: str
    base_url: str
    session: str
    api_key_env: str
    hmac_env: str
    shared: bool = False

    def api_key(self) -> str:
        return (os.environ.get(self.api_key_env) or "").strip()

    def hmac_secret(self) -> str:
        return (os.environ.get(self.hmac_env) or "").strip()


def instances_from_lines(lines: dict) -> tuple[WahaInstance, ...]:
    """The rows of THIS product in a `DECLARED_LINES`-shaped mapping."""
    return tuple(
        WahaInstance(
            name=name,
            base_url=str(row["base_url"]).rstrip("/"),
            session=str(row.get("session") or "default"),
            api_key_env=row["api_key_env"],
            hmac_env=row["hmac_secret_env"],
            shared=bool(row.get("shared")),
        )
        for name, row in sorted(lines.items())
        if row.get("product") == PRODUCT
    )


def get_waha_instances() -> tuple[WahaInstance, ...]:
    """DI seam: the closed list, derived from the generated seed module. Tests override THIS dependency."""
    from noctusai_lib.integrations.whatsapp.declared_lines import DECLARED_LINES

    return instances_from_lines(DECLARED_LINES)


def find_instance(instances, name: str) -> "WahaInstance | None":
    wanted = (name or "").strip()
    return next((i for i in instances if i.name == wanted), None)


def instance_for_base_url(instances, base_url: str) -> "WahaInstance | None":
    """The NON-shared line hosted at `base_url` (a shared/legacy host resolves to None: it keeps the global secret)."""
    wanted = (base_url or "").strip().rstrip("/")
    return next((i for i in instances if not i.shared and i.base_url == wanted), None)
