"""
Social/Content Studio service — campaigns CRUD, posts CRUD,
and the token-gated approval workflow.

Token design (public approval):
  - An approval row carries a `public_token` (uuid). The agency sends the
    client a link containing this token.
  - The public GET /api/content/approve/{token} endpoint reads the approval
    + its post via the admin (service_role) client, validates token+expiry,
    and returns a safe PublicApprovalView (no org_id).
  - The public POST /api/content/approve/{token} endpoint writes the decision
    (approved|revision + optional feedback) and sets decided_at, then updates
    the parent post's status to match — all via the admin client.
  - RLS is bypassed on the admin path. The security guarantee is: token must
    exist, must not be expired, must not already be decided. Never trust a
    client-supplied org_id for the write.

NOC-REMEDIATE[orbity-content-publish]: when a post status moves to "approved"
  and the agency wants to auto-publish, call the seed Meta integration here:
      from noctusai_lib.integrations.meta import get_meta_adapter
      adapter = get_meta_adapter(...)
      adapter.publish_instagram_post(...)
  The Meta adapter ships in noctusai_lib.integrations.meta (Real+Fake+factory).
  Wire at the service layer with the org's FB access token from client_credentials. — 2026-06-03

No silent errors: every except logs at the right level and re-raises.
No monkey-patching our own code.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any
from uuid import UUID

from noctusai_lib.domain.notifications import write_in_app
from noctusai_lib.primitives.roles import ADMIN_ROLES

logger = logging.getLogger(__name__)


class SocialContentService:
    """Authed service — uses a user-scoped Supabase client (RLS enforced)."""

    def __init__(self, db: Any, org_id: UUID) -> None:
        self._db = db
        self._org_id = str(org_id)

    def _t(self, table: str):
        # Schema-scoped at the database module level (orbity). Do NOT call
        # .schema() again here — would break MockSupabaseClient tracking.
        return self._db.table(table)

    # ------------------------------------------------------------------
    # Campaigns CRUD
    # ------------------------------------------------------------------

    def list_campaigns(
        self,
        client_id: str | None = None,
        month: str | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        try:
            query = (
                self._t("content_campaigns")
                .select("*")
                .eq("org_id", self._org_id)
                .order("created_at", desc=True)
            )
            if client_id:
                query = query.eq("client_id", client_id)
            if month:
                query = query.eq("month", month)
            if status:
                query = query.eq("status", status)
            result = query.execute()
        except Exception:
            logger.exception("social_content.list_campaigns failed org=%s", self._org_id)
            raise
        items = result.data or []
        offset = (page - 1) * page_size
        return {
            "items": items[offset: offset + page_size],
            "total": len(items),
            "page": page,
            "page_size": page_size,
        }

    def create_campaign(self, data: dict[str, Any]) -> dict[str, Any]:
        row = {**data, "org_id": self._org_id}
        try:
            result = self._t("content_campaigns").insert(row).execute()
        except Exception:
            logger.exception("social_content.create_campaign failed org=%s", self._org_id)
            raise
        rows = result.data or []
        if not rows:
            raise RuntimeError("Insert returned no data")
        return rows[0]

    def get_campaign(self, campaign_id: str) -> dict[str, Any] | None:
        try:
            result = (
                self._t("content_campaigns")
                .select("*")
                .eq("org_id", self._org_id)
                .eq("id", campaign_id)
                .execute()
            )
        except Exception:
            logger.exception(
                "social_content.get_campaign failed org=%s id=%s", self._org_id, campaign_id
            )
            raise
        rows = result.data or []
        return rows[0] if rows else None

    def update_campaign(self, campaign_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        try:
            result = (
                self._t("content_campaigns")
                .update(data)
                .eq("org_id", self._org_id)
                .eq("id", campaign_id)
                .execute()
            )
        except Exception:
            logger.exception(
                "social_content.update_campaign failed org=%s id=%s", self._org_id, campaign_id
            )
            raise
        rows = result.data or []
        return rows[0] if rows else None

    def delete_campaign(self, campaign_id: str) -> bool:
        try:
            result = (
                self._t("content_campaigns")
                .delete()
                .eq("org_id", self._org_id)
                .eq("id", campaign_id)
                .execute()
            )
        except Exception:
            logger.exception(
                "social_content.delete_campaign failed org=%s id=%s", self._org_id, campaign_id
            )
            raise
        return bool(result.data)

    # ------------------------------------------------------------------
    # Posts CRUD
    # ------------------------------------------------------------------

    def list_posts(
        self,
        campaign_id: str | None = None,
        client_id: str | None = None,
        platform: str | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        try:
            query = (
                self._t("content_posts")
                .select("*")
                .eq("org_id", self._org_id)
                .order("scheduled_for", desc=False)
            )
            if campaign_id:
                query = query.eq("campaign_id", campaign_id)
            if client_id:
                query = query.eq("client_id", client_id)
            if platform:
                query = query.eq("platform", platform)
            if status:
                query = query.eq("status", status)
            result = query.execute()
        except Exception:
            logger.exception("social_content.list_posts failed org=%s", self._org_id)
            raise
        items = result.data or []
        offset = (page - 1) * page_size
        return {
            "items": items[offset: offset + page_size],
            "total": len(items),
            "page": page,
            "page_size": page_size,
        }

    def create_post(self, data: dict[str, Any]) -> dict[str, Any]:
        row = {**data, "org_id": self._org_id}
        try:
            result = self._t("content_posts").insert(row).execute()
        except Exception:
            logger.exception("social_content.create_post failed org=%s", self._org_id)
            raise
        rows = result.data or []
        if not rows:
            raise RuntimeError("Insert returned no data")
        return rows[0]

    def get_post(self, post_id: str) -> dict[str, Any] | None:
        try:
            result = (
                self._t("content_posts")
                .select("*")
                .eq("org_id", self._org_id)
                .eq("id", post_id)
                .execute()
            )
        except Exception:
            logger.exception(
                "social_content.get_post failed org=%s id=%s", self._org_id, post_id
            )
            raise
        rows = result.data or []
        return rows[0] if rows else None

    def update_post(self, post_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        try:
            result = (
                self._t("content_posts")
                .update(data)
                .eq("org_id", self._org_id)
                .eq("id", post_id)
                .execute()
            )
        except Exception:
            logger.exception(
                "social_content.update_post failed org=%s id=%s", self._org_id, post_id
            )
            raise
        rows = result.data or []
        return rows[0] if rows else None

    def delete_post(self, post_id: str) -> bool:
        try:
            result = (
                self._t("content_posts")
                .delete()
                .eq("org_id", self._org_id)
                .eq("id", post_id)
                .execute()
            )
        except Exception:
            logger.exception(
                "social_content.delete_post failed org=%s id=%s", self._org_id, post_id
            )
            raise
        return bool(result.data)

    # ------------------------------------------------------------------
    # Approvals — authed side (create link, list, get)
    # ------------------------------------------------------------------

    def create_approval(self, post_id: str, expires_in_days: int = 7) -> dict[str, Any]:
        """Create an approval link for a post and set its status to pending_approval."""
        expires_at = (
            datetime.now(timezone.utc) + timedelta(days=expires_in_days)
        ).isoformat()
        row = {
            "org_id": self._org_id,
            "post_id": post_id,
            "expires_at": expires_at,
        }
        try:
            approval_result = self._t("post_approvals").insert(row).execute()
            rows = approval_result.data or []
            if not rows:
                raise RuntimeError("Approval insert returned no data")
            approval = rows[0]
            # Update post status to pending_approval
            self._t("content_posts").update({"status": "pending_approval"}).eq(
                "org_id", self._org_id
            ).eq("id", post_id).execute()
        except Exception:
            logger.exception(
                "social_content.create_approval failed org=%s post=%s", self._org_id, post_id
            )
            raise
        return approval

    def list_approvals(self, post_id: str | None = None) -> list[dict[str, Any]]:
        try:
            query = (
                self._t("post_approvals")
                .select("*")
                .eq("org_id", self._org_id)
                .order("created_at", desc=True)
            )
            if post_id:
                query = query.eq("post_id", post_id)
            result = query.execute()
        except Exception:
            logger.exception("social_content.list_approvals failed org=%s", self._org_id)
            raise
        return result.data or []

    def get_approval(self, approval_id: str) -> dict[str, Any] | None:
        try:
            result = (
                self._t("post_approvals")
                .select("*")
                .eq("org_id", self._org_id)
                .eq("id", approval_id)
                .execute()
            )
        except Exception:
            logger.exception(
                "social_content.get_approval failed org=%s id=%s", self._org_id, approval_id
            )
            raise
        rows = result.data or []
        return rows[0] if rows else None


class PublicApprovalService:
    """Admin-client service for the public token-gated approval path.

    Uses the service_role client (bypasses RLS). The token is the only
    authorization — validated server-side (existence + expiry + not-decided).
    No org_id is ever trusted from the caller.
    """

    def __init__(self, admin_db: Any, core_db: Any = None) -> None:
        self._db = admin_db
        # core `public` client — notification recipients + writes. None ⇒ the
        # decision is still recorded but `notify_team` reports it was skipped.
        self._core = core_db

    def _t(self, table: str):
        return self._db.table(table)

    def fetch_by_token(self, token: str) -> tuple[dict[str, Any], dict[str, Any]] | None:
        """Fetch (approval, post) by public_token.

        Returns None if token not found. Raises ValueError if expired or decided.

        Callers MUST validate that `token` parses as a UUID before calling
        this method — both public_get_approval and public_submit_approval
        in social_content_router do this (a malformed token is a 404, not
        a DB round-trip). A non-UUID token handed to this method would
        otherwise reach postgres as a raw string comparison against a
        UUID column (public_token) and raise 22P02, which propagates as
        an unhandled Exception (caller raises 502).
        """
        try:
            result = (
                self._t("post_approvals")
                .select("*")
                .eq("public_token", token)
                .execute()
            )
        except Exception:
            logger.exception("public_approval.fetch_by_token failed token=%s", token)
            raise
        rows = result.data or []
        if not rows:
            return None
        approval = rows[0]

        # Expiry check
        expires_at_str = approval.get("expires_at", "")
        if expires_at_str:
            try:
                expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
                if datetime.now(timezone.utc) > expires_at:
                    raise ValueError("Approval link has expired")
            except ValueError:
                raise
            except Exception:
                logger.warning(
                    "public_approval.fetch_by_token: could not parse expires_at=%s",
                    expires_at_str,
                )

        # Fetch the post
        post_id = approval.get("post_id", "")
        try:
            post_result = (
                self._t("content_posts")
                .select("*")
                .eq("id", post_id)
                .execute()
            )
        except Exception:
            logger.exception(
                "public_approval.fetch_by_token: post fetch failed post_id=%s", post_id
            )
            raise
        post_rows = post_result.data or []
        if not post_rows:
            logger.warning(
                "public_approval.fetch_by_token: post not found post_id=%s", post_id
            )
            return None
        return approval, post_rows[0]

    def decide(
        self,
        token: str,
        decision: str,
        feedback: str | None,
    ) -> dict[str, Any]:
        """Apply client decision (approved|revision) and update post status.

        Validates token, expiry, and idempotency (already-decided) before writing.
        Returns the updated approval row.
        """
        pair = self.fetch_by_token(token)
        if pair is None:
            raise LookupError("Approval token not found")
        approval, post = pair

        # Idempotency: already decided
        if approval.get("status") != "pending":
            raise ValueError(f"Approval already decided: {approval['status']}")

        approval_id = approval["id"]
        post_id = approval["post_id"]
        decided_at = datetime.now(timezone.utc).isoformat()

        update_approval = {
            "status": decision,
            "client_feedback": feedback,
            "decided_at": decided_at,
        }
        try:
            a_result = (
                self._t("post_approvals")
                .update(update_approval)
                .eq("id", approval_id)
                .execute()
            )
            rows = a_result.data or []
            if not rows:
                raise RuntimeError("Approval update returned no data")
            updated_approval = rows[0]

            # Mirror decision onto post status
            new_post_status = "approved" if decision == "approved" else "revision"
            self._t("content_posts").update({"status": new_post_status}).eq(
                "id", post_id
            ).execute()

            # NOC-REMEDIATE[orbity-content-publish]: if new_post_status == "approved"
            # and auto-publish is configured, call the seed Meta integration here:
            #   from noctusai_lib.integrations.meta import get_meta_adapter
            #   adapter = get_meta_adapter(org_id=..., access_token=...)
            #   adapter.publish_instagram_post(post_id=post_id, ...) — 2026-06-03

        except (LookupError, ValueError):
            raise
        except Exception:
            logger.exception(
                "public_approval.decide failed token=%s approval_id=%s", token, approval_id
            )
            raise
        # The client's decision is already committed; a notification failure must
        # not undo it, so it is logged at ERROR (never swallowed) and returned.
        updated_approval["team_notified"] = self.notify_team(approval, post, decision, feedback)
        return updated_approval

    def notify_team(
        self,
        approval: dict[str, Any],
        post: dict[str, Any],
        decision: str,
        feedback: str | None,
    ) -> int:
        """In-app notification for the agency when a client decides.

        Recipients: the post's `assignee_user_id` when set, otherwise the org's
        admins (`ADMIN_ROLES` in core `noctus_users`). Written through the seed's
        single writer `write_in_app`. Returns how many were notified (0 on skip
        or failure — both logged).
        """
        org_id = str(approval["org_id"])
        if self._core is None:
            logger.error("public_approval.notify skipped: no core client org=%s", org_id)
            return 0
        try:
            if post.get("assignee_user_id"):
                recipients = [str(post["assignee_user_id"])]
            else:
                rows = (
                    self._core.table("noctus_users").select("id").eq("org_id", org_id)
                    .in_("org_role", list(ADMIN_ROLES)).execute().data or []
                )
                recipients = [str(r["id"]) for r in rows if r.get("id")]
            caption = (post.get("caption") or "").strip()
            label = f"“{caption[:60]}…”" if len(caption) > 60 else (f"“{caption}”" if caption else "um post")
            if decision == "approved":
                title, message = "Cliente aprovou um post", f"O cliente aprovou {label}."
            else:
                title = "Cliente pediu revisão de um post"
                message = f"O cliente pediu revisão de {label}." + (f" Comentário: {feedback}" if feedback else "")
            sent = write_in_app(
                self._core, user_ids=recipients, kind="aprovacao_conteudo",
                title=title, message=message, org_id=org_id,
                metadata={"post_id": str(approval["post_id"]), "approval_id": str(approval["id"]), "decision": decision},
            )
            if not sent:
                logger.warning("public_approval.notify no recipients org=%s", org_id)
            return sent
        except Exception:
            logger.exception("public_approval.notify failed org=%s approval_id=%s", org_id, approval["id"])
            return 0
