# 03 — Agentic Workflows: Orchestration & Design Patterns

> **An agentic workflow doesn't just respond — it plans, acts, verifies, and iterates toward a goal.**

---

## What Is an Agentic Workflow

An Agentic Workflow is a multi-step execution pattern where an AI agent operates with **goal-directed autonomy**: it perceives its environment, makes decisions, takes actions through tools, evaluates results, and adjusts its approach — all within defined guardrails.

The difference from traditional automation:

| Aspect | Traditional Automation | Agentic Workflow |
|---|---|---|
| Flow | Predefined, static | Dynamic, adapts to context |
| Decisions | IF/ELSE hardcoded | LLM reasons over options |
| Errors | Fail or retry blindly | Diagnose and adjust approach |
| Input handling | Structured, validated | Natural language, ambiguous |
| Output | Deterministic | Non-deterministic, needs validation |

---

## The Four Fundamental Patterns

### 1. Reflection
The agent critiques its own output and iterates to improve quality.

```
Input → Agent generates output → Agent evaluates output → Passes quality? 
    YES → Return final output
    NO  → Agent refines based on self-critique → Re-evaluate (loop)
```

**When to use:** Content generation, code writing, analysis tasks where quality matters more than speed.

**Example in real estate:**
```
Lead asks complex question about financing options
  → Agent generates initial response
  → Agent evaluates: "Is this accurate? Complete? Appropriate tone?"
  → Agent refines if needed
  → Final response sent via WhatsApp
```

**CDD lens:** The reflection prompt IS the quality context. It defines what "good enough" looks like.

**TDD lens:** Eval cases should test both the final output AND whether the agent correctly identifies issues in intermediate outputs.

### 2. Tool Use
The agent connects to external systems to perform real actions, not just generate text.

```
Input → Agent reasons about what tools to use → Calls tool(s) → 
  Processes results → Generates response incorporating tool results
```

**When to use:** Any task requiring real-world data or side effects — database queries, API calls, document generation, message sending.

**Example in real estate:**
```
Lead: "Quero ver casas em Granja Viana até 1.5M"
  → Agent activates property-search Skill
  → Calls search_properties tool via MCP
  → Receives results from Supabase
  → Formats with whatsapp-formatter Skill
  → Returns formatted property list
```

**CDD lens:** Tool definitions shape the agent's action space — what it CAN do. Tool descriptions shape what it WILL do.

**TDD lens:** Test both the tool invocation (correct parameters?) and the result handling (correct formatting? graceful empty results?).

### 3. Planning
The agent breaks complex tasks into executable steps, creating and following a plan.

```
Complex goal → Agent creates step-by-step plan → Executes step 1 → 
  Evaluates result → Adjusts plan if needed → Executes step 2 → ... → Done
```

**When to use:** Multi-step operations, tasks requiring coordination, complex research tasks.

**Example in real estate:**
```
Request: "Gere o dossiê completo de certidões para o CPF 123.456.789-00"
  → Agent plans:
    1. Validate CPF format
    2. Request CND Federal (async)
    3. Request CNDT TST (async)
    4. Request TJSP (async)
    5. Request CENPROT (async)
    6. Wait for all responses (handle retries)
    7. Compile results into unified report
    8. Generate PDF
    9. Send via WhatsApp
  → Executes steps, adjusting for failures/retries
```

**CDD lens:** The plan is a dynamic context artifact. Each step changes the available context for the next step.

**TDD lens:** Test the plan generation itself (does the agent create a reasonable plan?) AND each step's execution.

### 4. Multi-Agent
Multiple specialized agents collaborate, each handling a different aspect of the task.

```
Orchestrator receives complex task
  → Delegates to Agent A (research)
  → Delegates to Agent B (analysis)
  → Delegates to Agent C (formatting)
  → Orchestrator synthesizes results
  → Final output
```

**When to use:** Tasks requiring different types of expertise, parallel processing, separation of concerns.

**Example in real estate:**
```
New lead enters through WhatsApp
  → Qualifier Agent: Evaluates lead quality and intent
  → Search Agent: Finds matching properties (if qualified)
  → Legal Agent: Checks document requirements (if interested)
  → Communication Agent: Composes and sends response
  → Orchestrator (n8n): Coordinates handoffs and tracks state
```

**CDD lens:** Each sub-agent has its own isolated context. The orchestrator manages context boundaries.

**TDD lens:** Test each agent independently AND test the orchestration (correct handoffs? state preserved?).

---

## Orchestration in n8n

n8n is your orchestration engine. Here's how the patterns map to n8n nodes:

### Basic Agent Workflow (n8n)

```
[Chat Trigger / Webhook] 
    → [AI Agent Node]
        ├── LLM: Claude/GPT (the brain)
        ├── Memory: Window Buffer / Postgres (the state)
        └── Tools:
            ├── MCP Client: WAHA (WhatsApp)
            ├── MCP Client: Supabase (database)
            ├── MCP Client: InfoSimples (legal APIs)
            └── Custom Tool: n8n Sub-workflow
    → [Response / Webhook Response]
```

### Multi-Agent Workflow (n8n)

```
[Chat Trigger]
    → [Router Agent] (classifies intent)
        ├── IF "property_search":
        │   → [Search Agent Sub-workflow]
        │       ├── LLM + property-search Skill
        │       └── MCP: Supabase
        ├── IF "qualification":
        │   → [Qualifier Agent Sub-workflow]
        │       ├── LLM + lead-qualification Skill
        │       └── MCP: CRM
        ├── IF "legal":
        │   → [Legal Agent Sub-workflow]
        │       ├── LLM + legal-certificates Skill
        │       └── MCP: InfoSimples
        └── IF "general":
            → [General Agent Sub-workflow]
                └── LLM + FAQ knowledge
    → [Formatter Agent] (formats for delivery channel)
    → [WAHA: Send Response]
```

### Stateful Conversation Flow (n8n)

```
[WAHA Webhook: Incoming Message]
    → [Load Session Memory] (from Supabase/Redis)
    → [AI Agent Node]
        ├── System prompt includes active Skill(s) based on conversation state
        ├── Memory: Session-specific context
        └── Tools: Context-appropriate tools only
    → [Save Session Memory]
    → [WAHA: Send Response]
```

---

## Guardrails & Safety

Agentic workflows need boundaries. Define them explicitly:

### Input Guardrails
Validate and sanitize before the agent processes:
```
- Message length limits
- Content filtering (spam, inappropriate content)
- Rate limiting per user/session
- Input format validation
```

### Execution Guardrails
Constrain what the agent can do:
```
- Maximum number of tool calls per turn
- Timeout per operation
- Budget limits (API costs per session)
- Allowed tools per context (don't expose legal tools to unqualified leads)
```

### Output Guardrails
Validate before delivering to the user:
```
- Response length limits
- Tone verification (professional, friendly, not aggressive)
- Factual accuracy checks (prices, availability)
- PII filtering (don't leak other clients' data)
```

### Human-in-the-Loop Checkpoints
Define when to escalate to a human:
```
- Agent confidence below threshold
- High-value transactions (> X amount)
- Negative sentiment detected
- Legal or compliance questions
- Agent loop detected (3+ retries without progress)
```

---

## Designing Agentic Workflows with CDD+TDD

### 1. Define Context (CDD)

Map the full context landscape of the workflow:

```yaml
workflow: lead-to-property-match
context_inputs:
  - Lead message (natural language, WhatsApp)
  - Conversation history (session memory)
  - Property database (Supabase)
  - Lead profile (CRM data, if returning lead)
context_outputs:
  - Formatted property recommendations
  - Updated lead profile
  - Conversation state for next interaction
context_transitions:
  - "unknown_intent" → qualifier asks questions → "qualified"
  - "qualified" → search executed → "results_presented"
  - "results_presented" → lead reacts → "interested" or "refine_search"
  - "interested" → schedule viewing or request documents
state_management:
  - Session memory: last 10 messages + extracted preferences
  - Persistent memory: lead profile, search history, interactions
```

### 2. Write the Eval (TDD)

Define end-to-end test scenarios:

```yaml
# eval-cases/lead-to-property-match.yaml
scenarios:
  - id: happy-path-full-criteria
    description: Lead with clear criteria gets immediate results
    steps:
      - input: "Oi, quero comprar uma casa em Granja Viana, até 2M, 3 quartos"
        expect:
          skill_activated: lead-qualification
          classification: hot
          next: property-search
      - input: null  # Agent responds with properties
        expect:
          skill_activated: property-search
          tool_called: search_properties
          tool_params: {region: "GV", max_price: 2000000, bedrooms: 3}
          response_contains: ["🏠", "R$", "quartos"]
          response_count: ">= 1"

  - id: vague-lead-qualification
    description: Lead with no criteria gets qualifying questions
    steps:
      - input: "Oi, tudo bem?"
        expect:
          response_type: greeting + qualifying_question
          should_not: call any search tool
      - input: "Quero ver imóveis"
        expect:
          skill_activated: lead-qualification
          response_asks_about: [region, budget, type]

  - id: no-results-graceful
    description: Search with no matches suggests alternatives
    steps:
      - input: "Quero um apartamento em Granja Viana até 300k"
        expect:
          tool_called: search_properties
          results_count: 0
          response_suggests: broaden_search
          response_tone: empathetic
```

### 3. Design the Workflow

Build the n8n workflow based on the context map and eval cases.

### 4. Validate Against Evals

Run all scenarios. Compare actual behavior against expected.

### 5. Refine & Iterate

Adjust Skills, system prompts, routing logic, and tool configurations until all evals pass.

---

## Anti-Patterns to Avoid

### The God Agent
One agent with a massive prompt that handles everything. Fragile, untestable, slow.
**Fix:** Break into specialized agents with clear responsibilities.

### The Infinite Loop
Agent retries the same failing action without changing approach.
**Fix:** Max retry limits + approach variation logic + human escalation.

### The Context Bomb
Loading all possible context into every interaction, wasting tokens and confusing the agent.
**Fix:** Progressive disclosure via Skills + context-appropriate tool loading.

### The Silent Failure
Agent encounters an error but doesn't report it, returning a vague or incorrect response.
**Fix:** Explicit error handling in every tool + validation of tool responses before using them.

### The Hallucination Pass-Through
Agent generates plausible but incorrect information (prices, availability, legal claims) without verification.
**Fix:** Ground all factual claims in tool results + output validation guardrails.
