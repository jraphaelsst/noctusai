"""Idempotent Pub/Sub provisioning for Gmail push-watch — REST, no gcloud.

`ensure_push_subscription(...)` converges a GCP project to the state
Gmail push needs, creating/patching only what is missing:

1. topic ``projects/<project_id>/topics/<topic>`` exists;
2. `gmail-api-push@system.gserviceaccount.com` holds
   `roles/pubsub.publisher` on that topic (else `users.watch` 403s);
3. a PUSH subscription on that topic delivers to `push_endpoint` with an
   OIDC token (`serviceAccountEmail=push_service_account`,
   `audience=audience`) — what `push.verify_push_token` checks.

Re-running is a no-op once converged (every step reads first). A
same-named subscription bound to a DIFFERENT topic raises
`PubSubProvisioningError` rather than being silently repointed.

It talks to the Pub/Sub v1 REST API through `googleapiclient` (static
discovery doc ships with the library — no network discovery fetch).

One-time GCP prerequisites (NOT automatable from here — a human with
project Owner does these once; full list in
`KB § CONTEXT/INTEGRATIONS/google.md § 5a`):

- Enable the **Gmail API** and **Cloud Pub/Sub API** on the GCP project
  that owns the OAuth client (`GOOGLE_OAUTH_CLIENT_ID`).
- Create a **push-auth service account** (e.g.
  ``gmail-push@<project>.iam.gserviceaccount.com``) — the identity Pub/Sub
  signs push tokens as. No roles needed on it. (Projects created before
  2021-04-08 must also grant the Pub/Sub service agent
  ``service-<PROJECT_NUMBER>@gcp-sa-pubsub.iam.gserviceaccount.com``
  `roles/iam.serviceAccountTokenCreator` on it.)
- The `credentials` passed here need `roles/pubsub.admin` (or
  `roles/pubsub.editor` + permission to set topic IAM) on the project,
  scope `PUBSUB_SCOPE` or cloud-platform. Typically a platform
  service-account key, never a tenant's mailbox OAuth.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from googleapiclient.errors import HttpError

from noctusai_lib.integrations.gmail.errors import PubSubProvisioningError
from noctusai_lib.integrations.gmail.types import GMAIL_PUSH_SERVICE_ACCOUNT

logger = logging.getLogger(__name__)

PUBLISHER_ROLE = "roles/pubsub.publisher"


@dataclass(frozen=True)
class PushSubscriptionResult:
    """What `ensure_push_subscription` found / changed.

    `topic_name` is the FULL resource name to pass to
    `GmailClient.watch(topic_name=...)`."""

    topic_name: str
    subscription_name: str
    created_topic: bool = False
    granted_publisher: bool = False
    created_subscription: bool = False
    updated_push_config: bool = False

    @property
    def changed(self) -> bool:
        return (
            self.created_topic
            or self.granted_publisher
            or self.created_subscription
            or self.updated_push_config
        )


def _full_name(project_id: str, kind: str, name: str) -> str:
    prefix = f"projects/{project_id}/{kind}/"
    if name.startswith("projects/"):
        if not name.startswith(prefix):
            raise ValueError(f"{name!r} is not a {kind} of project {project_id!r}")
        return name
    if not name or "/" in name:
        raise ValueError(f"invalid {kind} id {name!r}")
    return prefix + name


def _status(exc: HttpError) -> int | None:
    return getattr(exc.resp, "status", None)


def _build_service(credentials: Any) -> Any:
    from googleapiclient.discovery import build

    from noctusai_lib.integrations.gmail.real import _as_google_credentials

    return build(
        "pubsub",
        "v1",
        credentials=_as_google_credentials(credentials),
        cache_discovery=False,
    )


def _ensure_topic(topics: Any, topic_name: str) -> bool:
    try:
        topics.get(topic=topic_name).execute()
        return False
    except HttpError as exc:
        if _status(exc) != 404:
            logger.warning("pubsub.topic_get_failed topic=%s status=%s", topic_name, _status(exc))
            raise PubSubProvisioningError(f"cannot read topic {topic_name}: {exc}") from exc
    try:
        topics.create(name=topic_name, body={}).execute()
    except HttpError as exc:
        if _status(exc) == 409:  # created concurrently — converged anyway
            return False
        logger.warning("pubsub.topic_create_failed topic=%s status=%s", topic_name, _status(exc))
        raise PubSubProvisioningError(f"cannot create topic {topic_name}: {exc}") from exc
    logger.info("pubsub.topic_created topic=%s", topic_name)
    return True


def _ensure_publisher(topics: Any, topic_name: str) -> bool:
    member = f"serviceAccount:{GMAIL_PUSH_SERVICE_ACCOUNT}"
    try:
        policy = topics.getIamPolicy(resource=topic_name).execute() or {}
    except HttpError as exc:
        raise PubSubProvisioningError(f"cannot read IAM policy of {topic_name}: {exc}") from exc
    bindings = list(policy.get("bindings", []) or [])
    for binding in bindings:
        if binding.get("role") == PUBLISHER_ROLE and member in (binding.get("members") or []):
            return False
    for binding in bindings:
        if binding.get("role") == PUBLISHER_ROLE and not binding.get("condition"):
            binding["members"] = list(binding.get("members") or []) + [member]
            break
    else:
        bindings.append({"role": PUBLISHER_ROLE, "members": [member]})
    new_policy = {**policy, "bindings": bindings}  # keeps etag → optimistic concurrency
    try:
        topics.setIamPolicy(resource=topic_name, body={"policy": new_policy}).execute()
    except HttpError as exc:
        raise PubSubProvisioningError(
            f"cannot grant {PUBLISHER_ROLE} to {GMAIL_PUSH_SERVICE_ACCOUNT} on {topic_name}: {exc}"
        ) from exc
    logger.info("pubsub.gmail_publisher_granted topic=%s", topic_name)
    return True


def _ensure_subscription(
    subs: Any,
    subscription_name: str,
    topic_name: str,
    push_config: dict[str, Any],
    ack_deadline_seconds: int,
) -> tuple[bool, bool]:
    try:
        existing = subs.get(subscription=subscription_name).execute()
    except HttpError as exc:
        if _status(exc) != 404:
            raise PubSubProvisioningError(
                f"cannot read subscription {subscription_name}: {exc}"
            ) from exc
        existing = None

    if existing is None:
        body = {
            "topic": topic_name,
            "pushConfig": push_config,
            "ackDeadlineSeconds": ack_deadline_seconds,
        }
        try:
            subs.create(name=subscription_name, body=body).execute()
        except HttpError as exc:
            raise PubSubProvisioningError(
                f"cannot create subscription {subscription_name}: {exc}"
            ) from exc
        logger.info("pubsub.subscription_created subscription=%s", subscription_name)
        return True, False

    if existing.get("topic") != topic_name:
        raise PubSubProvisioningError(
            f"subscription {subscription_name} is bound to {existing.get('topic')!r}, "
            f"not {topic_name!r} — refusing to repoint it; pick another subscription id"
        )
    current = existing.get("pushConfig") or {}
    if (
        current.get("pushEndpoint") == push_config["pushEndpoint"]
        and (current.get("oidcToken") or {}) == push_config["oidcToken"]
    ):
        return False, False
    try:
        subs.modifyPushConfig(
            subscription=subscription_name, body={"pushConfig": push_config}
        ).execute()
    except HttpError as exc:
        raise PubSubProvisioningError(
            f"cannot update push config of {subscription_name}: {exc}"
        ) from exc
    logger.info("pubsub.push_config_updated subscription=%s", subscription_name)
    return False, True


def ensure_push_subscription(
    project_id: str,
    topic: str,
    push_endpoint: str,
    audience: str,
    credentials: Any,
    *,
    push_service_account: str,
    subscription: str | None = None,
    ack_deadline_seconds: int = 60,
    service: Any = None,
) -> PushSubscriptionResult:
    """Converge topic + Gmail publisher grant + OIDC push subscription.

    Args:
        project_id: GCP project id owning the topic.
        topic: topic id (``"gmail-replies"``) or full resource name.
        push_endpoint: public HTTPS URL of our push webhook.
        audience: OIDC `aud` Pub/Sub stamps on each push token — pass the
            SAME value to `verify_push_token(audience=...)` (the endpoint
            URL is the conventional choice).
        credentials: google `Credentials` (or `OAuthGmailCredentials`)
            allowed to administer Pub/Sub on `project_id`.
        push_service_account: email Pub/Sub signs push tokens as — pass
            the SAME value to `verify_push_token(expected_service_account=)`.
        subscription: subscription id/full name; default ``<topic>-push``.
        ack_deadline_seconds: ack deadline on CREATE (10-600).
        service: injected Pub/Sub v1 discovery service (DI seam for tests);
            built from `credentials` when omitted.

    Raises `ValueError` on bad arguments, `PubSubProvisioningError` when
    the API refuses or a conflicting subscription exists."""
    if not project_id:
        raise ValueError("project_id is required")
    if not push_endpoint.startswith("https://"):
        raise ValueError("push_endpoint must be an https:// URL (Pub/Sub refuses plain http)")
    if not audience:
        raise ValueError("audience is required (it is what verify_push_token checks)")
    if not push_service_account or "@" not in push_service_account:
        raise ValueError("push_service_account must be a service-account email")
    if not 10 <= ack_deadline_seconds <= 600:
        raise ValueError("ack_deadline_seconds must be within 10..600")

    topic_name = _full_name(project_id, "topics", topic)
    topic_id = topic_name.rsplit("/", 1)[-1]
    subscription_name = _full_name(project_id, "subscriptions", subscription or f"{topic_id}-push")
    push_config = {
        "pushEndpoint": push_endpoint,
        "oidcToken": {"serviceAccountEmail": push_service_account, "audience": audience},
    }

    svc = service if service is not None else _build_service(credentials)
    topics = svc.projects().topics()
    subs = svc.projects().subscriptions()

    created_topic = _ensure_topic(topics, topic_name)
    granted = _ensure_publisher(topics, topic_name)
    created_sub, updated = _ensure_subscription(
        subs, subscription_name, topic_name, push_config, ack_deadline_seconds
    )
    return PushSubscriptionResult(
        topic_name=topic_name,
        subscription_name=subscription_name,
        created_topic=created_topic,
        granted_publisher=granted,
        created_subscription=created_sub,
        updated_push_config=updated,
    )


__all__ = [
    "PUBLISHER_ROLE",
    "PushSubscriptionResult",
    "ensure_push_subscription",
]
