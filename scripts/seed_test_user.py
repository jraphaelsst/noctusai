"""
Seed script — Create a test user for local development.

Usage:
    python scripts/seed_test_user.py

Requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in core/backend/.env
"""
import os
import sys
import subprocess
from pathlib import Path

# Load .env from repo root
ROOT = Path(__file__).resolve().parent.parent
env_path = ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

try:
    from supabase import create_client
except ImportError:
    print("Installing supabase-py ...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "supabase", "-q"])
    from supabase import create_client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    print("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in environment / .env file")
    sys.exit(1)

# ── Test user config ──────────────────────────────────────────
TEST_EMAIL = "jraphaelsst@noctusai.com"
TEST_PASSWORD = "1281ksks"
TEST_NOME = "Raphael"
TEST_EMPRESA = "NoctusAI (Test)"
# ──────────────────────────────────────────────────────────────

def main():
    db = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

    # 1. Create auth user
    print(f"Creating auth user: {TEST_EMAIL} ...")
    try:
        auth_response = db.auth.admin.create_user({
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
            "email_confirm": True,
        })
        user = auth_response.user
        if not user:
            print("Error: Supabase returned no user object.")
            sys.exit(1)
        print(f"  Auth user created: {user.id}")
    except Exception as e:
        if "already been registered" in str(e).lower() or "already exists" in str(e).lower():
            print(f"  User {TEST_EMAIL} already exists — skipping auth creation.")
            # Fetch existing user
            users = db.auth.admin.list_users()
            user = next((u for u in users if u.email == TEST_EMAIL), None)
            if not user:
                print("  Could not find existing user. Aborting.")
                sys.exit(1)
            print(f"  Found existing user: {user.id}")
        else:
            print(f"  Error: {e}")
            sys.exit(1)

    user_id = user.id

    # 2. Create organization
    print(f"Creating organization: {TEST_EMPRESA} ...")
    slug = TEST_EMPRESA.strip().lower().replace(" ", "-").replace("(", "").replace(")", "")
    existing_org = db.table("organizations").select("id").eq("owner_id", user_id).execute()
    if existing_org.data:
        org = existing_org.data[0]
        print(f"  Organization already exists: {org['id']}")
    else:
        org_result = db.table("organizations").insert({
            "nome": TEST_EMPRESA,
            "slug": slug,
            "plano": "free",
            "owner_id": user_id,
            "category": "test",
        }).execute()
        if not org_result.data:
            print("  Error creating organization.")
            sys.exit(1)
        org = org_result.data[0]
        print(f"  Organization created: {org['id']}")

    org_id = org["id"]

    # 3. Create noctus_users profile (admin role)
    print("Creating user profile ...")
    existing_profile = db.table("noctus_users").select("id").eq("id", user_id).execute()
    if existing_profile.data:
        print(f"  Profile already exists for {user_id}")
    else:
        db.table("noctus_users").insert({
            "id": user_id,
            "email": TEST_EMAIL,
            "nome": TEST_NOME,
            "org_id": org_id,
            "role": "admin",
        }).execute()
        print(f"  Profile created (role=admin)")

    # 4. Auto-grant all active product licenses
    print("Granting product licenses ...")
    products = db.table("products").select("id, nome").eq("ativo", True).execute()
    for product in (products.data or []):
        existing = db.table("licenses").select("id").eq("org_id", org_id).eq("product_id", product["id"]).execute()
        if existing.data:
            print(f"  License already exists for: {product['nome']}")
        else:
            db.table("licenses").insert({
                "org_id": org_id,
                "product_id": product["id"],
                "status": "active",
            }).execute()
            print(f"  License granted: {product['nome']}")

    if not products.data:
        print("  No active products found — skipping licenses.")

    # 5. Create subscription (highest plan)
    print("Setting up subscription ...")
    existing_sub = db.table("subscriptions").select("id").eq("org_id", org_id).eq("status", "active").execute()
    if existing_sub.data:
        print("  Active subscription already exists.")
    else:
        plans = db.table("plans").select("id, name").eq("is_active", True).order("price_monthly", desc=True).execute()
        if plans.data:
            db.table("subscriptions").insert({
                "org_id": org_id,
                "plan_id": plans.data[0]["id"],
                "status": "active",
                "metadata": {"test_account": True, "unlimited": True},
            }).execute()
            print(f"  Subscription created: {plans.data[0]['name']}")
        else:
            print("  No active plans found — skipping subscription.")

    print()
    print("=" * 50)
    print("Test user ready!")
    print(f"  Email:    {TEST_EMAIL}")
    print(f"  Password: {TEST_PASSWORD}")
    print(f"  Org:      {TEST_EMPRESA} ({org_id})")
    print(f"  Role:     admin")
    print("=" * 50)


if __name__ == "__main__":
    main()
