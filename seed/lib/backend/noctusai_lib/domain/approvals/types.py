"""Approvals vocabulary: the closed event set and the derived status of a subject's current versao."""
from __future__ import annotations

EVENT_SUBMITTED = "submitted"
EVENT_APPROVED = "approved"
EVENT_REJECTED = "rejected"
EVENT_KINDS = (EVENT_SUBMITTED, EVENT_APPROVED, EVENT_REJECTED)
DECISION_EVENTS = (EVENT_APPROVED, EVENT_REJECTED)

STATUS_NONE = "none"
STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUSES = (STATUS_NONE, STATUS_PENDING, STATUS_APPROVED, STATUS_REJECTED)
