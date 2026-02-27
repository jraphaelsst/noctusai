# 05 — Testing & Evals: Validating Agentic Systems

> **If you can't test it, you can't trust it. If you can't eval it, you can't iterate it.**

---

## Why Testing Agentic Systems Is Different

Traditional software is deterministic: same input → same output. Agentic systems are **non-deterministic**: the same input might produce different (but equally valid) outputs. This requires a different testing mindset.

The challenge isn't that agents can't be tested — it's that you need **different types of assertions**:

| Assertion Type | Traditional Software | Agentic Systems |
|---|---|---|
| Exact match | `assert result == 42` | Rarely useful |
| Structural | `assert "id" in response` | Tool call params, JSON schemas |
| Behavioral | N/A | Did it call the right tool? |
| Semantic | N/A | Is the response helpful? On-tone? |
| Negative | `assert error is raised` | Did it refuse correctly? Not hallucinate? |

---

## The Agentic Test Pyramid

```
              /\
             /  \         E2E Tests
            /    \        Full user journey through the system
           /------\       Tools: Playwright
          /        \
         /          \     Agent Evals (NEW LAYER)
        /            \    Skill behavior, routing, multi-turn conversations
       /              \   Tools: Custom eval harness, LLM-as-judge
      /----------------\
     /                  \  Integration Tests
    /                    \ API endpoints, MCP tools, database queries
   /                      \Tools: pytest + httpx, MCP test client
  /------------------------\
 /                          \ Unit Tests
/                            \Business logic, validators, formatters
                              Tools: pytest, vitest
```

### Layer 1: Unit Tests (Foundation)

Test pure functions, business logic, data transformations — anything deterministic.

```python
# tests/services/test_lead_scoring.py

def test_hot_lead_with_financing():
    """Lead with financing and urgency scores as hot."""
    lead = LeadInput(
        financing="approved",
        urgency="high",
        budget=2_000_000,
        region="Granja Viana"
    )
    score = calculate_lead_score(lead)
    assert score.classification == "hot"
    assert score.confidence >= 0.8

def test_cold_lead_no_criteria():
    """Lead with no criteria scores as cold."""
    lead = LeadInput()
    score = calculate_lead_score(lead)
    assert score.classification == "cold"
```

```typescript
// client/__tests__/components/PropertyCard.test.tsx

test('renders property with all fields', () => {
  render(<PropertyCard property={mockProperty} />);
  expect(screen.getByText('Casa em Granja Viana')).toBeInTheDocument();
  expect(screen.getByText('R$ 1.500.000')).toBeInTheDocument();
  expect(screen.getByText('3 quartos')).toBeInTheDocument();
});

test('renders placeholder when no image', () => {
  render(<PropertyCard property={{...mockProperty, image: null}} />);
  expect(screen.getByTestId('image-placeholder')).toBeInTheDocument();
});
```

### Layer 2: Integration Tests

Test API endpoints, MCP tool calls, database operations — things that cross boundaries.

```python
# tests/api/test_properties.py

@pytest.mark.asyncio
async def test_search_with_valid_filters(client: AsyncClient, seed_properties):
    response = await client.post("/api/properties/search", json={
        "region": "GV",
        "max_price": 1_500_000,
        "bedrooms": 3
    })
    assert response.status_code == 200
    data = response.json()
    assert len(data["results"]) > 0
    assert all(p["price"] <= 1_500_000 for p in data["results"])
    assert all(p["region"] == "GV" for p in data["results"])

@pytest.mark.asyncio
async def test_search_returns_empty_not_404(client: AsyncClient):
    response = await client.post("/api/properties/search", json={
        "region": "NONEXISTENT",
        "max_price": 1
    })
    assert response.status_code == 200
    assert response.json()["results"] == []
```

```python
# tests/mcp/test_infosimples_tools.py

@pytest.mark.asyncio
async def test_cnd_federal_valid_cpf(mcp_client):
    result = await mcp_client.call_tool("cnd_federal", {
        "document": "123.456.789-00",
        "document_type": "cpf"
    })
    assert result["status"] in ["regular", "irregular", "processing"]

@pytest.mark.asyncio
async def test_cnd_federal_invalid_cpf(mcp_client):
    result = await mcp_client.call_tool("cnd_federal", {
        "document": "000.000.000-00",
        "document_type": "cpf"
    })
    assert "error" in result
```

### Layer 3: Agent Evals (The New Layer)

This is where CDD+TDD shines for agentic systems. Evals test the agent's **behavior** — not just its output, but its reasoning, tool selection, and conversation flow.

#### Eval Case Structure

```yaml
# evals/cases/lead-qualification.yaml

metadata:
  skill: lead-qualification
  version: 1.0.0
  baseline_score: 0.90  # Alert if score drops below this

cases:
  - id: hot-lead-explicit
    description: Lead with clear buying intent and criteria
    input:
      message: "Preciso comprar urgente, já tenho financiamento aprovado, quero até 2M na Granja Viana"
      session_history: []
    assertions:
      - type: structural
        check: classification
        expected: "hot"
      - type: structural
        check: confidence
        operator: ">="
        expected: 0.8
      - type: behavioral
        check: tool_called
        expected: null  # Should NOT call search tools yet
      - type: behavioral
        check: next_action
        expected: "transfer_to_search"
      - type: semantic
        check: response_quality
        criteria: "Response should acknowledge urgency and confirm criteria before proceeding"

  - id: ambiguous-intent
    description: Lead asks a vague question
    input:
      message: "Quanto custa um apartamento aí?"
      session_history: []
    assertions:
      - type: structural
        check: classification
        expected: "warm"
      - type: behavioral
        check: response_type
        expected: "qualifying_question"
      - type: semantic
        check: question_quality
        criteria: "Should ask about region, budget range, and timeline in a natural conversational way"
      - type: negative
        check: should_not_contain
        patterns: ["não posso", "não sei", "error"]
```

#### Assertion Types in Detail

**Structural Assertions** — Validate data structure and values.
```python
def assert_structural(result, check, expected, operator="=="):
    value = extract_field(result, check)
    if operator == "==":
        assert value == expected
    elif operator == ">=":
        assert value >= expected
    elif operator == "in":
        assert value in expected
```

**Behavioral Assertions** — Validate what the agent DID, not just what it said.
```python
def assert_behavioral(trace, check, expected):
    if check == "tool_called":
        tools_used = [t["name"] for t in trace["tool_calls"]]
        if expected is None:
            assert len(tools_used) == 0
        else:
            assert expected in tools_used
    elif check == "skill_activated":
        assert trace["active_skill"] == expected
```

**Semantic Assertions (LLM-as-Judge)** — Use another LLM to evaluate quality.
```python
async def assert_semantic(response_text, criteria):
    judge_prompt = f"""
    Evaluate the following AI agent response against the given criteria.
    
    CRITERIA: {criteria}
    
    RESPONSE: {response_text}
    
    Score from 0 to 1. Return JSON: {{"score": float, "reasoning": string}}
    """
    judgment = await judge_llm.complete(judge_prompt)
    assert judgment["score"] >= 0.7, f"Semantic check failed: {judgment['reasoning']}"
```

**Negative Assertions** — Validate what the agent should NOT do.
```python
def assert_negative(result, check, patterns):
    if check == "should_not_contain":
        for pattern in patterns:
            assert pattern.lower() not in result["response"].lower()
    elif check == "should_not_call":
        tools_used = [t["name"] for t in result["tool_calls"]]
        for tool in patterns:
            assert tool not in tools_used
```

### Layer 4: E2E Tests

Full user journeys through the system. Use Playwright for web flows and custom scripts for WhatsApp flows.

```python
# tests/e2e/test_property_search_flow.py

async def test_complete_property_search(page):
    """Full flow: login → search → view details → contact agent."""
    await page.goto("/login")
    await page.fill("[name=email]", "test@example.com")
    await page.fill("[name=password]", "testpass")
    await page.click("button[type=submit]")
    
    await page.goto("/search")
    await page.select_option("[name=region]", "Granja Viana")
    await page.fill("[name=max_price]", "1500000")
    await page.click("button:text('Buscar')")
    
    await expect(page.locator(".property-card")).to_have_count_greater_than(0)
    
    await page.click(".property-card >> first")
    await expect(page.locator(".property-detail")).to_be_visible()
```

---

## Eval Harness Architecture

### Structure

```
evals/
├── cases/                    # Test case definitions
│   ├── lead-qualification.yaml
│   ├── property-search.yaml
│   ├── legal-certificates.yaml
│   └── multi-turn-conversation.yaml
├── runners/                  # Execution scripts
│   ├── eval_runner.py        # Main runner
│   ├── assertions.py         # Assertion implementations
│   └── judge.py              # LLM-as-judge implementation
├── reports/                  # Results and tracking
│   ├── results/              # Per-run results (JSON)
│   │   ├── 2025-01-15_14-30.json
│   │   └── 2025-01-16_09-00.json
│   └── dashboard.html        # Visual regression dashboard
└── config.yaml               # Runner configuration
```

### Runner Configuration

```yaml
# evals/config.yaml

runner:
  parallel: true
  max_concurrent: 5
  timeout_per_case: 30  # seconds
  retry_on_timeout: 1

judge:
  model: claude-sonnet-4-5-20250929
  temperature: 0
  max_tokens: 500

agent_under_test:
  endpoint: "http://localhost:5678/webhook/agent"
  auth: "${AGENT_API_KEY}"

regression:
  baseline_file: "reports/baseline.json"
  alert_threshold: 0.10  # 10% drop triggers alert
  tracking: true
```

### Running Evals

```bash
# Run all evals
python evals/runners/eval_runner.py

# Run specific Skill evals
python evals/runners/eval_runner.py --skill lead-qualification

# Run and update baseline
python evals/runners/eval_runner.py --update-baseline

# Run with regression check
python evals/runners/eval_runner.py --check-regression
```

---

## Regression Tracking

### Why It Matters
When you change a Skill's prompt, add a new tool, or update the system prompt, previously-correct behaviors might break. This is **context drift** — the agentic equivalent of software regression.

### How to Track

```json
// reports/results/2025-01-16_09-00.json
{
  "timestamp": "2025-01-16T09:00:00Z",
  "overall_score": 0.92,
  "by_skill": {
    "lead-qualification": {
      "score": 0.95,
      "cases_passed": 19,
      "cases_failed": 1,
      "failed_cases": ["edge-case-mixed-language"]
    },
    "property-search": {
      "score": 0.88,
      "cases_passed": 15,
      "cases_failed": 2,
      "failed_cases": ["no-results-broadening", "price-in-usd"]
    }
  },
  "regression_from_baseline": {
    "overall": -0.02,
    "lead-qualification": +0.05,
    "property-search": -0.08  // ⚠️ ALERT: dropped > 5%
  }
}
```

### Regression Response Protocol
When a regression is detected:
1. Identify which cases broke
2. Check what changed since the last passing run (prompt? tool? data?)
3. Fix the root cause
4. Re-run evals to confirm fix
5. Update baseline if the change was intentional

---

## Testing in n8n Workflows

### Workflow-Level Testing

n8n supports Evaluations for AI Workflows. Use this to:
- Define test inputs (webhook payloads, chat messages)
- Run the workflow against each input
- Compare outputs against expected results
- Track performance over time

### Manual Testing Checklist

For each agent workflow before deployment:

- [ ] Happy path works end-to-end
- [ ] Agent handles empty/no results gracefully
- [ ] Agent handles API errors gracefully
- [ ] Agent respects rate limits (no infinite retry loops)
- [ ] Session memory persists correctly across turns
- [ ] Agent escalates to human when confidence is low
- [ ] Response formatting is correct for the delivery channel
- [ ] No PII leakage between sessions/users
- [ ] Timeout handling works (agent doesn't hang indefinitely)
- [ ] Concurrent sessions don't interfere with each other

---

## CI Integration

### Pre-Commit / Pre-Deploy Pipeline

```yaml
# .github/workflows/test.yaml (or equivalent CI config)

stages:
  - name: Unit Tests
    run: |
      pytest tests/services/ tests/models/ -v
      cd client && npx vitest run

  - name: Integration Tests
    run: pytest tests/api/ tests/mcp/ -v

  - name: Agent Evals
    run: python evals/runners/eval_runner.py --check-regression

  - name: E2E Tests (on staging only)
    run: npx playwright test
    condition: branch == "main"
```

### Definition of Done for Any Change

A change is only complete when:
1. All existing tests still pass
2. New tests are written for new behavior
3. Evals show no regression (or regression is intentional and documented)
4. Code reviewed and approved
