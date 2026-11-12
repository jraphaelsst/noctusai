"""Vocabulary of the assignment organ: strategies, event kinds, criteria, rule kinds (all generic -- no market nouns)."""
from __future__ import annotations

import re

#: The strategies the organ ships. A host adds one more by NAME through a hook (`strategy.StrategyHook`), never a fork.
STRATEGY_ROUND_ROBIN = "round_robin"
STRATEGY_BY_TEAM = "by_team"
STRATEGY_BY_SOURCE = "by_source"
STRATEGY_BY_UNIT = "by_unit"  # the declared `org_unit_id` seam (roadmap T-UNIT): a nullable uuid convention, no unit table here
STRATEGY_MANUAL = "manual"
BUILTIN_STRATEGIES: tuple[str, ...] = (STRATEGY_ROUND_ROBIN, STRATEGY_BY_TEAM, STRATEGY_BY_SOURCE, STRATEGY_BY_UNIT, STRATEGY_MANUAL)

#: Intent-named events (`asg_events`, append-only). `no_candidate` records an auto-assign that found nobody, so
#: "how often did a lead wait for a human" is a query, not a guess.
EVENT_ASSIGNED = "assigned"
EVENT_REASSIGNED = "reassigned"
EVENT_UNASSIGNED = "unassigned"
EVENT_CLOSED = "closed"
EVENT_NO_CANDIDATE = "no_candidate"
EVENT_KINDS: tuple[str, ...] = (EVENT_ASSIGNED, EVENT_REASSIGNED, EVENT_UNASSIGNED, EVENT_CLOSED, EVENT_NO_CANDIDATE)

#: Why the owner is who it is (`asg_assignments.criterion` / `asg_events.criterion`): measurable per criterion.
CRITERION_KEEP_LAST = "keep_last"
CRITERION_MANUAL = "manual"
CRITERION_CUSTOM_PREFIX = "custom:"

RULE_SOURCE = "source"
RULE_UNIT = "unit"
RULE_KINDS: tuple[str, ...] = (RULE_SOURCE, RULE_UNIT)

#: A strategy name: a lowercase slug (matches the DB CHECK on `asg_settings.strategy`).
STRATEGY_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
SUBJECT_KIND_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")

#: Why a member is not eligible right now.
UNAVAILABLE_INACTIVE = "inactive"
UNAVAILABLE_OUT_OF_OFFICE = "out_of_office"
UNAVAILABLE_AT_CAPACITY = "at_capacity"

#: Why nobody was picked (`NoPick.reason`).
NO_PICK_MANUAL = "manual"
NO_PICK_NO_TEAM = "no_team"
NO_PICK_NO_MEMBER = "no_available_member"
NO_PICK_HOOK_DECLINED = "hook_declined"

__all__ = [n for n in dir() if n.isupper() and not n.startswith("_")]
