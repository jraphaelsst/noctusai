"""Fixtures for the therapy scheduling-pilot real-DB smoke tests.

Mirrors the established realdb pattern (`products/erp-imobiliario/.../realdb/`):
service-role client targets the `therapy` schema, a `core_db` client targets
public for `auth.users` admin operations, and a `cleanup` fixture deletes
inserted rows in reverse order on teardown.

Tests skip automatically when SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY are
not set — keeps CI green without real-DB credentials.

Reactivation note: these tests prove the wiring against the live Supabase
the migration was applied to. A failing assertion here means the deployed
schema/RPCs/RLS are out of sync with the code, not just a unit-level bug.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from supabase import create_client
from supabase.lib.client_options import ClientOptions

# Load the repo-root .env so SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY are
# visible to os.environ without requiring shell exports. Silent no-op
# when python-dotenv isn't installed or the file doesn't exist.
try:
    from dotenv import load_dotenv

    _repo_root_env = Path(__file__).resolve().parents[5] / ".env"
    if _repo_root_env.exists():
        load_dotenv(_repo_root_env, override=False)
except ImportError:
    pass

pytestmark = pytest.mark.realdb


# ---------------------------------------------------------------------------
# Env / clients
# ---------------------------------------------------------------------------


def _get_credentials() -> tuple[str, str]:
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        pytest.skip(
            "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set — skipping realdb"
        )
    return url, key


@pytest.fixture(scope="session")
def core_db():
    """Service-role client for the public schema (auth.users admin)."""
    url, key = _get_credentials()
    return create_client(url, key)


@pytest.fixture(scope="session")
def therapy_db():
    """Service-role client bound to the `therapy` schema."""
    url, key = _get_credentials()
    return create_client(url, key, options=ClientOptions(schema="therapy"))


# ---------------------------------------------------------------------------
# Cleanup helper — dispatches by kind so user-keyed tables work too
# ---------------------------------------------------------------------------

# Tables whose PK is `user_id` (not `id`).
_USER_KEYED_TABLES = {"therapist_profiles", "patient_profiles"}


@pytest.fixture
def cleanup(therapy_db, core_db):
    """Track (kind, id) tuples; delete in reverse order on teardown.

    Special kinds:
      - `("user", user_id)` → `core_db.auth.admin.delete_user(...)`.
      - `("therapist_profiles" | "patient_profiles", user_id)` → delete
        by `user_id` column (those tables' PK).
      - any other tuple → `therapy_db.table(table).delete().eq("id", rid)`.
    """
    records: list[tuple[str, str]] = []
    yield records
    for kind, rid in reversed(records):
        try:
            if kind == "user":
                core_db.auth.admin.delete_user(rid)
            elif kind in _USER_KEYED_TABLES:
                therapy_db.table(kind).delete().eq("user_id", rid).execute()
            else:
                therapy_db.table(kind).delete().eq("id", rid).execute()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Tenant fixtures — clinic, therapist (auth user + profile), patient
# ---------------------------------------------------------------------------


def _new_email(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@scheduling-realdb.test"


@pytest.fixture
def test_clinic(therapy_db, cleanup):
    """A real `therapy.clinics` row + its `therapy.clinic_settings` row.

    `clinic_settings.transition_buffer_minutes` defaults to 15 (per
    migration 011); we leave it at the default so the smoke test
    exercises the default-resolution path."""
    clinic = (
        therapy_db.table("clinics")
        .insert(
            {
                "name": f"Clinica Smoke {uuid.uuid4().hex[:6]}",
                "is_active": True,
            }
        )
        .execute()
        .data[0]
    )
    cleanup.append(("clinics", clinic["id"]))

    therapy_db.table("clinic_settings").insert({"clinic_id": clinic["id"]}).execute()
    # clinic_settings.clinic_id is the PK (no `id`); rely on the
    # `clinics` ON DELETE CASCADE FK to clean it up.

    return clinic


def _create_auth_user(core_db, *, role: str, clinic_id: str | None = None):
    email = _new_email(f"{role}-realdb")
    password = f"TestPass!{uuid.uuid4().hex[:10]}"
    metadata = {"role": role}
    if clinic_id:
        metadata["clinic_id"] = clinic_id
    resp = core_db.auth.admin.create_user(
        {
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": metadata,
        }
    )
    return resp.user, email, password


@pytest.fixture
def test_therapist(therapy_db, core_db, test_clinic, cleanup):
    """A real auth user + therapy.therapist_profiles row, attached to test_clinic."""
    user, email, password = _create_auth_user(
        core_db, role="therapist", clinic_id=test_clinic["id"]
    )
    cleanup.append(("user", user.id))

    therapy_db.table("therapist_profiles").insert(
        {
            "user_id": user.id,
            "clinic_id": test_clinic["id"],
            "crp": f"CRP-{uuid.uuid4().hex[:6]}",
            "is_approved": True,
            "is_active": True,
            "session_duration_minutes": 50,
        }
    ).execute()
    cleanup.append(("therapist_profiles", user.id))

    return {
        "user_id": user.id,
        "email": email,
        "password": password,
        "clinic_id": test_clinic["id"],
    }


@pytest.fixture
def test_patient(therapy_db, core_db, cleanup):
    """A real auth user + therapy.patient_profiles row."""
    user, email, _password = _create_auth_user(core_db, role="patient")
    cleanup.append(("user", user.id))

    therapy_db.table("patient_profiles").insert(
        {
            "user_id": user.id,
            "origin": "platform",
            "is_active": True,
        }
    ).execute()
    cleanup.append(("patient_profiles", user.id))

    return {"user_id": user.id, "email": email}
