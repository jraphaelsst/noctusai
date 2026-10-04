"""Admin-MFA building blocks (project ``platform-admin-mfa``, slice M1).

M1 shipped the pieces; M2 adds ``gate`` (composed inside the admin factories, default off). See
``projects/platform-admin-mfa/PROJECT.md`` §5.
"""
from noctusai_lib.api.auth.mfa.aal import Aal, read_aal, read_aal_issued
from noctusai_lib.api.auth.mfa.client import (
    FakeMfaClient, MfaChallenge, MfaClient, MfaEnrollment, MfaError, MfaFactor,
    MfaSession, SupabaseMfaClient, make_mfa_client,
)
from noctusai_lib.api.auth.mfa.policy import (
    FLEET_SCOPE, MFA_POLICY_TABLE, FakeMfaPolicy, MfaMode, MfaPolicy,
    SupabaseMfaPolicy, make_mfa_policy, pick_mode,
)

from noctusai_lib.api.auth.mfa.gate import (
    ADMIN_TIER_ROLES, MFA_WARN_HEADER, MfaGateConfig, require_admin_assurance,
)

__all__ = [
    "ADMIN_TIER_ROLES", "MFA_WARN_HEADER", "MfaGateConfig", "require_admin_assurance",
    "Aal", "read_aal", "read_aal_issued",
    "FakeMfaClient", "MfaChallenge", "MfaClient", "MfaEnrollment", "MfaError", "MfaFactor",
    "MfaSession", "SupabaseMfaClient", "make_mfa_client",
    "FLEET_SCOPE", "MFA_POLICY_TABLE", "FakeMfaPolicy", "MfaMode", "MfaPolicy",
    "SupabaseMfaPolicy", "make_mfa_policy", "pick_mode",
]
