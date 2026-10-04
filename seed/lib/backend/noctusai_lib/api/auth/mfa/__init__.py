"""Admin-MFA building blocks (project ``platform-admin-mfa``, slice M1).

M1 ships the pieces only — NO gate, NO router: nothing here changes runtime
behaviour until M2 composes the gate into the admin factories. See
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

__all__ = [
    "Aal", "read_aal", "read_aal_issued",
    "FakeMfaClient", "MfaChallenge", "MfaClient", "MfaEnrollment", "MfaError", "MfaFactor",
    "MfaSession", "SupabaseMfaClient", "make_mfa_client",
    "FLEET_SCOPE", "MFA_POLICY_TABLE", "FakeMfaPolicy", "MfaMode", "MfaPolicy",
    "SupabaseMfaPolicy", "make_mfa_policy", "pick_mode",
]
