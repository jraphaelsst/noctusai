# 07 — Templates: Reusable Starting Points

> **Don't start from scratch. Start from a template. Customize from there.**

---

## Skill Template

### SKILL.md Template

```markdown
---
name: [skill-name]
description: >
  [1-3 sentence description of what this skill does and WHEN to use it.
  Be specific enough to trigger correctly, distinct enough to avoid false activations.]
version: 1.0.0
triggers:
  - [keyword or phrase that should activate this skill]
  - [another trigger]
dependencies:
  - mcp: [mcp-server-name]
  - skill: [other-skill-name]  # if composing skills
---

# [Skill Name]

## Purpose
[1 paragraph explaining the skill's role and value.]

## Instructions

### Step 1: [Action Name]
[Clear, step-by-step instructions for the agent.]

### Step 2: [Action Name]
[Continue with sequential steps.]

### Step 3: [Action Name]
[Final steps including output formatting.]

## Edge Cases
- [Edge case 1] → [Expected behavior]
- [Edge case 2] → [Expected behavior]
- [Failure scenario] → [Graceful degradation behavior]

## Examples

### Example 1: [Scenario Name]
**Input:** "[example user message]"
**Expected tool call:** tool_name({param: value})
**Expected behavior:** [description of correct behavior]

### Example 2: [Scenario Name]
**Input:** "[example user message]"
**Expected behavior:** [description of correct behavior]

### Example 3: [Edge Case]
**Input:** "[edge case message]"
**Expected behavior:** [description of graceful handling]
```

---

## Eval Case Template

### YAML Eval Case

```yaml
# evals/cases/[skill-name].yaml

metadata:
  skill: [skill-name]
  version: 1.0.0
  baseline_score: 0.85
  last_updated: 2025-01-15

cases:
  - id: [descriptive-id]
    description: [What this case tests]
    tags: [happy-path, edge-case, error-handling, multi-turn]
    input:
      message: "[user input text]"
      session_history: []  # or list of prior messages
      context:  # optional additional context
        user_profile: {}
        active_session: true
    assertions:
      - type: structural
        check: [field_name]
        expected: [value]
        operator: "=="  # ==, >=, <=, in, contains
      - type: behavioral
        check: tool_called
        expected: [tool_name]  # or null if no tool expected
      - type: behavioral
        check: tool_params
        expected:
          param1: value1
          param2: value2
      - type: semantic
        check: response_quality
        criteria: "[Natural language criteria for LLM judge]"
      - type: negative
        check: should_not_contain
        patterns: ["error", "cannot", "impossible"]

  - id: [another-case-id]
    description: [What this case tests]
    input:
      message: "[another input]"
    assertions:
      - type: structural
        check: [field]
        expected: [value]
```

---

## MCP Tool Definition Template

### Tool Schema (JSON)

```json
{
  "name": "[tool_name]",
  "description": "[Clear description: what it does, when to use it, what it returns, any limitations. 2-4 sentences.]",
  "inputSchema": {
    "type": "object",
    "properties": {
      "param_name": {
        "type": "string",
        "description": "[What this parameter represents and expected format]"
      },
      "optional_param": {
        "type": "number",
        "description": "[Description]",
        "default": 10
      }
    },
    "required": ["param_name"]
  },
  "annotations": {
    "rate_limit": "[X/min]",
    "avg_response_time": "[Xs]",
    "may_require_retry": false,
    "side_effects": "[none | creates_record | sends_message | etc]"
  }
}
```

---

## API Endpoint Template

### FastAPI Router (Supabase pattern)

```python
# app/routers/[resource].py

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Header, Query
from app.dependencies import get_current_user
from app.database import get_supabase_client
from app.schemas.[resource] import [Model]Create, [Model]Update
from app.utils import paginated_response, success_response, ok_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/[resources]", tags=["[Resources]"])


@router.get("/")
async def listar_[resources](
    authorization: Optional[str] = Header(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List [resources] for the authenticated user (RLS-scoped)."""
    user, token = await get_current_user(authorization)
    supabase = get_supabase_client(token)

    offset = (page - 1) * page_size
    result = supabase.table("[resources]") \
        .select("*", count="exact") \
        .range(offset, offset + page_size - 1) \
        .order("created_at", desc=True) \
        .execute()

    return paginated_response(result.data, result.count, page, page_size)


@router.get("/{id}")
async def obter_[resource](
    id: str,
    authorization: Optional[str] = Header(None),
):
    """Get a single [resource] by ID."""
    user, token = await get_current_user(authorization)
    supabase = get_supabase_client(token)

    result = supabase.table("[resources]").select("*").eq("id", id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="[Resource] não encontrado")

    return success_response(result.data[0])


@router.post("/", status_code=201)
async def criar_[resource](
    data: [Model]Create,
    authorization: Optional[str] = Header(None),
):
    """Create a new [resource]."""
    user, token = await get_current_user(authorization)
    supabase = get_supabase_client(token)

    payload = data.model_dump(exclude_none=True)
    payload["org_id"] = user.user_metadata.get("org_id")
    result = supabase.table("[resources]").insert(payload).execute()

    return success_response(result.data[0])


@router.patch("/{id}")
async def atualizar_[resource](
    id: str,
    data: [Model]Update,
    authorization: Optional[str] = Header(None),
):
    """Update an existing [resource]."""
    user, token = await get_current_user(authorization)
    supabase = get_supabase_client(token)

    payload = data.model_dump(exclude_none=True)
    result = supabase.table("[resources]").update(payload).eq("id", id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="[Resource] não encontrado")

    return success_response(result.data[0])


@router.delete("/{id}")
async def deletar_[resource](
    id: str,
    authorization: Optional[str] = Header(None),
):
    """Delete a [resource]."""
    user, token = await get_current_user(authorization)
    supabase = get_supabase_client(token)

    supabase.table("[resources]").delete().eq("id", id).execute()
    return ok_response("[Resource] removido com sucesso")
```

### Test Contract for Endpoint

```python
# tests/routers/test_[resources]_router.py

import pytest


class TestListar[Resources]:
    def test_lista_com_sucesso(self, client):
        response = client.get("/api/[resources]/")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "total" in data

    def test_sem_autorizacao_retorna_401(self, client_sem_auth):
        response = client_sem_auth.get("/api/[resources]/")
        assert response.status_code == 401


class TestObter[Resource]:
    def test_obter_por_id(self, client, mock_[resource]):
        response = client.get(f"/api/[resources]/{mock_[resource]['id']}")
        assert response.status_code == 200
        assert response.json()["data"]["id"] == mock_[resource]["id"]

    def test_nao_encontrado_retorna_404(self, client):
        response = client.get("/api/[resources]/uuid-inexistente")
        assert response.status_code == 404


class TestCriar[Resource]:
    def test_criar_com_sucesso(self, client):
        payload = {"campo1": "valor1", "campo2": "valor2"}
        response = client.post("/api/[resources]/", json=payload)
        assert response.status_code == 201

    def test_payload_invalido_retorna_422(self, client):
        response = client.post("/api/[resources]/", json={})
        assert response.status_code == 422
```

---

## Pydantic Schema Template

```python
# app/schemas/[resource].py

from typing import Optional
from pydantic import BaseModel, Field


class [Model]Create(BaseModel):
    """Schema for creating a new [resource]."""
    titulo: str = Field(..., max_length=200)
    descricao: Optional[str] = None
    regiao: str = Field(..., max_length=100)
    valor: float = Field(..., ge=0)
    ativo: bool = True


class [Model]Update(BaseModel):
    """Schema for updating a [resource]. All fields optional."""
    titulo: Optional[str] = Field(None, max_length=200)
    descricao: Optional[str] = None
    regiao: Optional[str] = Field(None, max_length=100)
    valor: Optional[float] = Field(None, ge=0)
    ativo: Optional[bool] = None
```

### SQL Migration Template

```sql
-- migrations/001_create_[resources].sql

CREATE TABLE IF NOT EXISTS [resources] (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES organizations(id),
    titulo TEXT NOT NULL,
    descricao TEXT,
    regiao TEXT NOT NULL,
    valor NUMERIC(15,2) NOT NULL DEFAULT 0,
    ativo BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- RLS: tenant isolation
ALTER TABLE [resources] ENABLE ROW LEVEL SECURITY;

CREATE POLICY "[resources]_org_isolation" ON [resources]
    FOR ALL USING (org_id = auth.jwt() ->> 'org_id');

-- Index for common queries
CREATE INDEX idx_[resources]_org_id ON [resources](org_id);
CREATE INDEX idx_[resources]_regiao ON [resources](regiao);
```

---

## pytest conftest.py Template

```python
# tests/conftest.py

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from app.main import app


class MockQueryBuilder:
    """Chainable mock that simulates Supabase PostgREST query builder."""

    def __init__(self, data=None, count=None):
        self._data = data or []
        self._count = count or len(self._data)

    def select(self, *args, **kwargs):
        return self

    def insert(self, data):
        self._data = [data] if isinstance(data, dict) else data
        return self

    def update(self, data):
        return self

    def delete(self):
        return self

    def eq(self, field, value):
        return self

    def range(self, start, end):
        return self

    def order(self, field, **kwargs):
        return self

    def execute(self):
        result = MagicMock()
        result.data = self._data
        result.count = self._count
        return result


class MockSupabaseClient:
    """Mock Supabase client for testing without a real database."""

    def __init__(self, data=None):
        self._data = data or []

    def table(self, name):
        return MockQueryBuilder(self._data)


class AuthClient:
    """Wrapper around TestClient that auto-injects auth headers."""

    def __init__(self, test_client):
        self._client = test_client
        self._headers = {"Authorization": "Bearer test-token"}

    def get(self, url, **kwargs):
        kwargs.setdefault("headers", {}).update(self._headers)
        return self._client.get(url, **kwargs)

    def post(self, url, **kwargs):
        kwargs.setdefault("headers", {}).update(self._headers)
        return self._client.post(url, **kwargs)

    def patch(self, url, **kwargs):
        kwargs.setdefault("headers", {}).update(self._headers)
        return self._client.patch(url, **kwargs)

    def delete(self, url, **kwargs):
        kwargs.setdefault("headers", {}).update(self._headers)
        return self._client.delete(url, **kwargs)


MOCK_USER = MagicMock()
MOCK_USER.id = "test-user-id"
MOCK_USER.user_metadata = {"org_id": "test-org-id", "nome": "Test User"}


@pytest.fixture
def client():
    """Fully wired test client with mocked auth and Supabase."""
    with patch("app.dependencies.get_current_user", return_value=(MOCK_USER, "test-token")):
        with patch("app.database.get_supabase_client", return_value=MockSupabaseClient()):
            yield AuthClient(TestClient(app))
```

---

## n8n Workflow System Prompt Template

For the AI Agent node in n8n:

```
You are a real estate assistant for One Consultoria Imobiliária, specializing in 
medium-to-high-end properties in Granja Viana/Cotia, São Paulo.

## Your Active Skills
[Skills are loaded dynamically based on conversation context]

## Your Available Tools
- search_properties: Search the property database by region, price, bedrooms, type
- send_whatsapp: Send a message via WhatsApp
- get_lead_profile: Retrieve lead information from CRM
- generate_matches: Find matching permutas for a property

## Rules
1. Always be professional and friendly. Use Portuguese (Brazilian).
2. Never invent property data — only share what the search tool returns.
3. If unsure about any claim, say so honestly.
4. For hot leads (financing approved, urgent timeline), prioritize immediate property matches.
5. For cold leads, nurture with relevant content and gentle qualifying questions.
6. Never share one client's data with another.
7. If you can't help with something, offer to connect them with a human agent.

## Response Format
For WhatsApp delivery, keep messages concise (< 500 chars per message).
Use emojis sparingly for visual organization: 🏠 📍 💰 🛏️
```

---

## Feature Acceptance Criteria Template

```
Feature: [Feature Name]
  Context: [Where/when this feature is used]
  Type: [Agent-powered | Traditional automation | UI feature]
  Skills: [Required skills, if agent-powered]
  MCP Dependencies: [Required MCP servers]

  AC-1: Given [precondition],
        when [action],
        then [expected result].

  AC-2: Given [precondition],
        when [action],
        then [expected result].

  AC-ERR-1: Given [error condition],
            when [action],
            then [graceful handling].

  AC-EDGE-1: Given [edge case],
             when [action],
             then [expected behavior].
```

---

## Eval Runner Template

```python
# evals/runners/eval_runner.py

import asyncio
import yaml
import json
from datetime import datetime
from pathlib import Path
from typing import Optional
import httpx


class EvalRunner:
    def __init__(self, config_path: str = "evals/config.yaml"):
        with open(config_path) as f:
            self.config = yaml.safe_load(f)
        self.results = []

    async def run_case(self, case: dict) -> dict:
        """Run a single eval case and return results."""
        try:
            # Send input to agent
            response = await self.call_agent(case["input"])
            
            # Run assertions
            assertion_results = []
            for assertion in case["assertions"]:
                result = await self.check_assertion(response, assertion)
                assertion_results.append(result)
            
            passed = all(r["passed"] for r in assertion_results)
            return {
                "case_id": case["id"],
                "passed": passed,
                "assertions": assertion_results,
                "response": response,
            }
        except Exception as e:
            return {
                "case_id": case["id"],
                "passed": False,
                "error": str(e),
            }

    async def call_agent(self, input_data: dict) -> dict:
        """Send input to the agent and return response."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.config["agent_under_test"]["endpoint"],
                json=input_data,
                timeout=self.config["runner"]["timeout_per_case"],
            )
            return response.json()

    async def check_assertion(self, response: dict, assertion: dict) -> dict:
        """Check a single assertion against the response."""
        assertion_type = assertion["type"]
        
        if assertion_type == "structural":
            return self._check_structural(response, assertion)
        elif assertion_type == "behavioral":
            return self._check_behavioral(response, assertion)
        elif assertion_type == "semantic":
            return await self._check_semantic(response, assertion)
        elif assertion_type == "negative":
            return self._check_negative(response, assertion)
        else:
            return {"passed": False, "error": f"Unknown assertion type: {assertion_type}"}

    async def run_skill(self, skill_name: str) -> dict:
        """Run all eval cases for a skill."""
        cases_path = Path(f"evals/cases/{skill_name}.yaml")
        with open(cases_path) as f:
            data = yaml.safe_load(f)
        
        results = []
        for case in data["cases"]:
            result = await self.run_case(case)
            results.append(result)
        
        passed = sum(1 for r in results if r["passed"])
        total = len(results)
        score = passed / total if total > 0 else 0
        
        return {
            "skill": skill_name,
            "score": score,
            "cases_passed": passed,
            "cases_total": total,
            "cases_failed": [r["case_id"] for r in results if not r["passed"]],
            "details": results,
        }

    def save_report(self, results: dict):
        """Save eval results to reports directory."""
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        report_path = Path(f"evals/reports/results/{timestamp}.json")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w") as f:
            json.dump(results, f, indent=2, default=str)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--skill", help="Run evals for specific skill")
    parser.add_argument("--check-regression", action="store_true")
    parser.add_argument("--update-baseline", action="store_true")
    args = parser.parse_args()
    
    runner = EvalRunner()
    # Implementation continues based on args...
```
