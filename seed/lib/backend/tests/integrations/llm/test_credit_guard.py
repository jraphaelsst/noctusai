"""Prepaid credit enforcement in the seed budget guard (core migration 093).

`enforce_budget` → `enforce_credits` refuses a PREPAID org at/below its overdraft
floor with `LLMCreditsExhausted` (402) BEFORE the provider call, and is
fail-CLOSED: an unreadable wallet of an unknown / prepaid org is refused
(`LLMCreditsUnverifiable`, 503) and marked for the platform admins. Orgs without a
wallet, `byok` and `postpaid_trusted` keep today's behaviour. The fake client below
is the injected admin client (`configure_budget_module`) — no patching.
"""
from __future__ import annotations

import pytest

from noctusai_lib.integrations.llm import budget
from noctusai_lib.integrations.llm.exceptions import LLMCreditsExhausted, LLMCreditsUnverifiable

ORG = "11111111-1111-1111-1111-111111111111"


class _Result:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, db, table):
        self.db, self.table_name, self.filters, self._insert = db, table, {}, None

    def select(self, _cols):
        return self

    def eq(self, col, value):
        self.filters[col] = value
        return self

    def gte(self, *_a):
        return self

    def lte(self, *_a):
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, _n):
        return self

    def range(self, start, end):
        return self

    def insert(self, rows):
        self._insert = rows
        return self

    def execute(self):
        if self.db.fail_tables and self.table_name in self.db.fail_tables:
            raise RuntimeError(self.db.fail_tables[self.table_name])
        if self._insert is not None:
            self.db.inserted.setdefault(self.table_name, []).extend(self._insert)
            return _Result(self._insert)
        self.db.reads[self.table_name] = self.db.reads.get(self.table_name, 0) + 1
        rows = [r for r in self.db.tables.get(self.table_name, [])
                if all(str(r.get(k)) == str(v) for k, v in self.filters.items())]
        return _Result(rows)


class FakeAdmin:
    def __init__(self):
        self.tables: dict[str, list[dict]] = {"org_settings": [], "ai_usage": [], "credit_wallets": [],
                                              "noctus_users": [{"id": "admin-1", "role": "admin"}]}
        self.fail_tables: dict[str, str] = {}
        self.inserted: dict[str, list[dict]] = {}
        self.reads: dict[str, int] = {}

    def schema(self, name):
        assert name == "public"
        return self

    def table(self, name):
        return _Query(self, name)

    def wallet(self, **row):
        self.tables["credit_wallets"] = [{"org_id": ORG, "mode": "prepaid", "balance_credits": 0,
                                          "overdraft_limit_credits": 0, **row}]


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def env(monkeypatch):
    db = FakeAdmin()
    clock = Clock()
    budget._reset_credit_state_for_tests(clock=clock)
    budget.configure_budget_module(admin_client_factory=lambda: db)
    monkeypatch.delenv("LLM_CREDITS_CACHE_TTL_S", raising=False)
    yield db, clock
    budget.configure_budget_module(admin_client_factory=None)
    budget._reset_credit_state_for_tests()


@pytest.mark.asyncio
async def test_no_wallet_keeps_todays_behaviour(env):
    await budget.enforce_budget(ORG)


@pytest.mark.asyncio
async def test_prepaid_with_balance_passes(env):
    db, _ = env
    db.wallet(balance_credits=10)
    await budget.enforce_budget(ORG)


@pytest.mark.asyncio
async def test_prepaid_at_zero_is_refused_with_402(env):
    db, _ = env
    db.wallet(balance_credits=0)
    with pytest.raises(LLMCreditsExhausted) as exc:
        await budget.enforce_budget(ORG)
    assert exc.value.status_code == 402
    assert exc.value.code == "LLM_CREDITS_EXHAUSTED"


@pytest.mark.asyncio
async def test_overdraft_floor_is_respected(env):
    db, _ = env
    db.wallet(balance_credits=-50, overdraft_limit_credits=100)
    await budget.enforce_budget(ORG)  # -50 > -100
    budget._reset_credit_state_for_tests()
    budget.configure_budget_module(admin_client_factory=lambda: db)
    db.wallet(balance_credits=-100, overdraft_limit_credits=100)
    with pytest.raises(LLMCreditsExhausted):
        await budget.enforce_budget(ORG)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["byok", "postpaid_trusted"])
async def test_byok_and_trusted_are_never_refused(env, mode):
    db, _ = env
    db.wallet(mode=mode, balance_credits=-999999)
    await budget.enforce_budget(ORG)


@pytest.mark.asyncio
async def test_reads_go_through_a_short_ttl_cache(env):
    db, clock = env
    db.wallet(balance_credits=10)
    await budget.enforce_credits(ORG)
    await budget.enforce_credits(ORG)
    assert db.reads["credit_wallets"] == 1
    db.wallet(balance_credits=0)
    clock.t += 16  # past the 15 s default TTL
    with pytest.raises(LLMCreditsExhausted):
        await budget.enforce_credits(ORG)
    assert db.reads["credit_wallets"] == 2


@pytest.mark.asyncio
async def test_read_failure_for_unknown_org_refuses_and_marks(env):
    db, _ = env
    db.fail_tables["credit_wallets"] = "connection reset"
    with pytest.raises(LLMCreditsUnverifiable) as exc:
        await budget.enforce_budget(ORG)
    assert exc.value.status_code == 503
    marks = db.inserted.get("notifications", [])
    assert [m["user_id"] for m in marks] == ["admin-1"]
    assert marks[0]["metadata"]["tipo"] == "creditos_guarda_indisponivel"
    # rate-limited: a second refusal within 10 min does not spam the bell
    with pytest.raises(LLMCreditsUnverifiable):
        await budget.enforce_budget(ORG)
    assert len(db.inserted["notifications"]) == 1


@pytest.mark.asyncio
async def test_read_failure_for_a_known_prepaid_org_refuses(env):
    db, clock = env
    db.wallet(balance_credits=10)
    await budget.enforce_credits(ORG)
    clock.t += 60
    db.fail_tables["credit_wallets"] = "timeout"
    with pytest.raises(LLMCreditsUnverifiable):
        await budget.enforce_credits(ORG)


@pytest.mark.asyncio
async def test_read_failure_for_a_known_non_prepaid_org_proceeds(env):
    db, clock = env  # first read: no wallet
    await budget.enforce_credits(ORG)
    clock.t += 60
    db.fail_tables["credit_wallets"] = "timeout"
    await budget.enforce_credits(ORG)  # last seen: no wallet -> today's behaviour


@pytest.mark.asyncio
async def test_missing_table_means_no_wallet_can_exist(env):
    db, _ = env
    db.fail_tables["credit_wallets"] = "PGRST205: Could not find the table 'public.credit_wallets'"
    await budget.enforce_budget(ORG)  # migration not applied: nobody is prepaid


@pytest.mark.asyncio
async def test_unconfigured_module_is_a_no_op():
    budget.configure_budget_module(admin_client_factory=None)
    await budget.enforce_credits(ORG)
