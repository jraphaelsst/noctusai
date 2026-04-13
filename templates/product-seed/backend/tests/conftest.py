"""
{{PRODUCT_NAME}} — Test fixtures.

Provides MockSupabaseClient, AuthClient, and the wired `client` fixture
with mocked auth and Supabase operations.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Mock Supabase
# ---------------------------------------------------------------------------

class MockSupabaseResponse:
    def __init__(self, data=None, error=None, count=None):
        self.data = data or []
        self.error = error
        self.count = count if count is not None else len(self.data)


class MockQueryBuilder:
    def __init__(self):
        self._data = []
        self._single = False

    def set_data(self, data):
        self._data = data

    # Chainable methods
    def select(self, *a, **kw): return self
    def insert(self, *a, **kw): return self
    def update(self, *a, **kw): return self
    def upsert(self, *a, **kw): return self
    def delete(self, *a, **kw): return self
    def eq(self, *a, **kw): return self
    def neq(self, *a, **kw): return self
    def in_(self, *a, **kw): return self
    def is_(self, *a, **kw): return self
    def or_(self, *a, **kw): return self
    def ilike(self, *a, **kw): return self
    def order(self, *a, **kw): return self
    def range(self, *a, **kw): return self
    def limit(self, *a, **kw): return self
    def single(self):
        self._single = True
        return self

    def execute(self):
        data = self._data
        if self._single:
            data = data[0] if data else None
            self._single = False
        return MockSupabaseResponse(data=data, count=len(self._data) if isinstance(self._data, list) else 1)


class MockSupabaseClient:
    def __init__(self):
        self._tables = {}
        self.auth = MagicMock()

    def table(self, name):
        if name not in self._tables:
            self._tables[name] = MockQueryBuilder()
        return self._tables[name]

    def set_table_data(self, name, data):
        if name not in self._tables:
            self._tables[name] = MockQueryBuilder()
        self._tables[name].set_data(data if isinstance(data, list) else [data])


# ---------------------------------------------------------------------------
# Auth Client wrapper
# ---------------------------------------------------------------------------

class AuthClient:
    """TestClient wrapper that adds Authorization header automatically."""

    def __init__(self, test_client, mock_supabase):
        self._client = test_client
        self.mock_supabase = mock_supabase

    def get(self, url, **kw):
        kw.setdefault("headers", {})["Authorization"] = "Bearer test-token"
        return self._client.get(url, **kw)

    def post(self, url, **kw):
        kw.setdefault("headers", {})["Authorization"] = "Bearer test-token"
        return self._client.post(url, **kw)

    def patch(self, url, **kw):
        kw.setdefault("headers", {})["Authorization"] = "Bearer test-token"
        return self._client.patch(url, **kw)

    def put(self, url, **kw):
        kw.setdefault("headers", {})["Authorization"] = "Bearer test-token"
        return self._client.put(url, **kw)

    def delete(self, url, **kw):
        kw.setdefault("headers", {})["Authorization"] = "Bearer test-token"
        return self._client.delete(url, **kw)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MOCK_USER_ID = "00000000-0000-0000-0000-000000000001"
MOCK_ORG_ID = "00000000-0000-0000-0000-000000000099"


@pytest.fixture
def client():
    """Fully wired test client with mocked auth and Supabase."""
    mock_sb = MockSupabaseClient()

    mock_user = MagicMock()
    mock_user.id = MOCK_USER_ID
    mock_user.email = "test@example.com"
    mock_user.user_metadata = {"org_id": MOCK_ORG_ID, "role": "user"}

    async def mock_get_current_user(*args, **kwargs):
        return mock_user, "test-token"

    # Patch all router modules that import get_current_user and get_admin_client
    patches = {
        "app.dependencies.get_current_user": mock_get_current_user,
        "app.database.get_supabase_client": lambda *a, **kw: mock_sb,
        "app.database.get_admin_client": lambda: mock_sb,
        "app.database.get_user_client": lambda t: mock_sb,
        "app.database.get_core_client": lambda: mock_sb,
    }

    # Auto-patch all routers that import these
    import pkgutil
    import app.routers as routers_pkg
    for _, name, _ in pkgutil.iter_modules(routers_pkg.__path__):
        module = f"app.routers.{name}"
        for dep in ["get_current_user", "get_admin_client", "get_core_client"]:
            try:
                patches[f"{module}.{dep}"] = patches.get(f"app.dependencies.{dep}", patches.get(f"app.database.{dep}"))
            except Exception:
                pass

    active_patches = []
    for target, mock_val in patches.items():
        try:
            p = patch(target, mock_val)
            p.start()
            active_patches.append(p)
        except (AttributeError, ModuleNotFoundError):
            pass

    from app.main import app as fastapi_app
    test_client = TestClient(fastapi_app)
    auth_client = AuthClient(test_client, mock_sb)

    yield auth_client

    for p in active_patches:
        p.stop()
