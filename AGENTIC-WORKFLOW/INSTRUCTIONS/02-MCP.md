# 02 — MCP: The Universal Integration Layer

> **MCP is the USB-C of AI agents. One protocol to connect any agent to any tool, data source, or service.**

---

## What Is MCP

The **Model Context Protocol (MCP)** is an open standard (governed by the Agentic AI Foundation under the Linux Foundation) that provides a standardized way to connect AI agents to external tools and data sources. Instead of building custom integrations for each service, you build against a single protocol.

MCP uses JSON-RPC 2.0 messages to establish communication between three actors:

- **Host** — The LLM application that initiates connections (Claude, ChatGPT, your n8n instance)
- **Client** — The connector within the host that manages the MCP session
- **Server** — The service that exposes tools, data, and prompts to the agent

---

## MCP Server Capabilities

An MCP Server can expose three types of capabilities:

### Resources
Data and context for the agent to consume. Resources return information but do not execute side effects.

```
Examples:
- Database query results (property listings, lead history)
- File contents (documents, contracts, images)
- Configuration data (business rules, pricing tables)
- Real-time data feeds (exchange rates, market data)
```

### Tools
Executable functions that the agent can invoke. Tools perform actions and may have side effects.

```
Examples:
- search_properties(filters) → matching listings
- generate_certificate(cpf, type) → PDF document
- send_whatsapp_message(to, body) → delivery confirmation
- schedule_appointment(lead_id, datetime) → booking confirmation
```

### Prompts
Reusable templates and workflows for LLM-server communication. Prompts provide structured interaction patterns.

```
Examples:
- lead_qualification_prompt(messages) → structured assessment
- property_description_prompt(property_data) → marketing copy
- follow_up_prompt(lead_history) → personalized message
```

---

## MCP Architecture in Our Stack

```
┌──────────────────────────────────────────────────┐
│                n8n (Host + Client)                 │
│                                                    │
│  ┌──────────────────────────────────────────┐     │
│  │         AI Agent Node (Host)              │     │
│  │                                           │     │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐    │     │
│  │  │MCP Cli 1│ │MCP Cli 2│ │MCP Cli 3│    │     │
│  │  └────┬────┘ └────┬────┘ └────┬────┘    │     │
│  └───────┼───────────┼───────────┼──────────┘     │
│          │           │           │                  │
└──────────┼───────────┼───────────┼──────────────────┘
           │           │           │
    ┌──────┴──────┐ ┌──┴───┐ ┌────┴─────┐
    │ WAHA Server │ │Supa  │ │InfoSimples│
    │  (WhatsApp) │ │base  │ │  (Legal)  │
    │             │ │Server│ │           │
    │ Tools:      │ │      │ │ Tools:    │
    │ send_msg    │ │Tools:│ │ cnd_fed   │
    │ read_msg    │ │query │ │ cndt_tst  │
    │ get_status  │ │insert│ │ tjsp      │
    │             │ │update│ │ cenprot   │
    └─────────────┘ └──────┘ └──────────┘
```

### Two Directions of MCP in n8n

**1. n8n as MCP Client (consuming external MCP Servers)**
Your n8n workflows consume tools from external MCP Servers using the MCP Client Tool node. The AI Agent node in n8n connects to MCP Servers and invokes their tools as part of the workflow.

**2. n8n as MCP Server (exposing workflows to external agents)**
Your n8n workflows can be exposed as MCP Servers, allowing Claude, ChatGPT, Lovable, or any MCP-compatible client to invoke your automations. This turns your property search workflow, for example, into a tool that any agent can use.

---

## Designing MCP Servers with CDD+TDD

### 1. Define Context (CDD)

For each external service, define:
- What capabilities does this service provide?
- What data does the agent need from it?
- What actions can the agent take through it?
- What are the security and rate-limit constraints?

```yaml
# MCP Server: infosimples-legal
context:
  purpose: Generate legal certificates for real estate transactions
  capabilities:
    - Federal tax clearance (CND Federal)
    - Labor court clearance (CNDT TST)
    - State court records (TJSP)
    - Protest registry (CENPROT)
  constraints:
    - Rate limited: 10 req/min per endpoint
    - Requires CPF/CNPJ as input
    - Response time: 5-30 seconds per certificate
    - May return "processing" status requiring retry
  auth: API key via environment variable
```

### 2. Write the Eval (TDD)

Define test contracts for each tool:

```python
# tests/mcp/test_infosimples_server.py

class TestCNDFederalTool:
    """Test contract for the cnd_federal tool."""

    async def test_valid_cpf_returns_certificate(self):
        """Given a valid CPF, when requesting CND Federal,
        then return certificate data with status and PDF URL."""
        result = await mcp_call("cnd_federal", {"cpf": "123.456.789-00"})
        assert result["status"] in ["regular", "irregular", "processing"]
        assert "pdf_url" in result or result["status"] == "processing"

    async def test_invalid_cpf_returns_error(self):
        """Given an invalid CPF, when requesting CND Federal,
        then return validation error."""
        result = await mcp_call("cnd_federal", {"cpf": "000.000.000-00"})
        assert result["error"] == "invalid_cpf"

    async def test_rate_limit_returns_retry_after(self):
        """Given rate limit exceeded, when requesting CND Federal,
        then return 429 with retry_after header."""
        # Exhaust rate limit
        for _ in range(11):
            await mcp_call("cnd_federal", {"cpf": "123.456.789-00"})
        result = await mcp_call("cnd_federal", {"cpf": "123.456.789-00"})
        assert result["error"] == "rate_limited"
        assert "retry_after" in result
```

### 3. Design the Server

Define each tool with its schema:

```json
{
  "name": "cnd_federal",
  "description": "Generate Federal Tax Clearance Certificate (CND) for a given CPF or CNPJ. Returns certificate status and PDF download URL. May return 'processing' status requiring a retry after 10 seconds.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "document": {
        "type": "string",
        "description": "CPF (xxx.xxx.xxx-xx) or CNPJ (xx.xxx.xxx/xxxx-xx)"
      },
      "document_type": {
        "type": "string",
        "enum": ["cpf", "cnpj"],
        "description": "Type of document"
      }
    },
    "required": ["document", "document_type"]
  },
  "annotations": {
    "rate_limit": "10/min",
    "avg_response_time": "15s",
    "may_require_retry": true
  }
}
```

---

## MCP Server Design Patterns

### Pattern 1: Direct Proxy
The MCP Server is a thin wrapper around an existing API. Translates MCP protocol to the API's native format.

```
Agent → MCP Client → MCP Server (proxy) → InfoSimples API
```

Best for: Existing APIs with stable contracts. Minimal logic on the MCP layer.

### Pattern 2: Aggregator
The MCP Server combines multiple underlying services into a single logical tool.

```
Agent → MCP Client → MCP Server (aggregator) → [API 1, API 2, API 3]
```

Best for: Operations that require data from multiple sources. Example: "full legal check" that calls CND + CNDT + TJSP + CENPROT in parallel.

### Pattern 3: Stateful Workflow
The MCP Server manages multi-step operations with state, using the Tasks primitive (MCP 2025-11-25).

```
Agent → MCP Client → MCP Server → [Step 1 → Step 2 → ... → Result]
                         ↑ Task status polling
```

Best for: Long-running operations like certificate generation with retry logic, document processing, or batch operations.

### Pattern 4: Context Reducer
An AI agent sits inside the MCP Server, reducing complex tool outputs to only the relevant information before returning to the calling agent.

```
Agent → MCP Client → MCP Server (with internal agent) → Complex API
                         ↓ Internal agent summarizes/filters
                     Reduced response → Agent
```

Best for: APIs that return too much data (e.g., GitHub API with dozens of tools). The internal agent understands which data is relevant to the request.

---

## MCP Security Checklist

- [ ] **API keys** stored as environment variables, never hardcoded
- [ ] **Rate limiting** implemented and documented per tool
- [ ] **Input validation** on all tool parameters before forwarding to APIs
- [ ] **Error handling** returns structured errors, never raw API responses
- [ ] **Timeout handling** with configurable timeouts per tool
- [ ] **Logging** of all tool invocations for audit (without sensitive data)
- [ ] **Auth scope** — each MCP Server only has access to the APIs it needs
- [ ] **User consent** — document which data each tool accesses
- [ ] **Transport security** — HTTPS for all remote MCP Servers

---

## MCP in n8n: Implementation Guide

### Consuming an MCP Server in n8n

```
1. Add the MCP Client Tool node to your AI Agent node
2. Configure the MCP Server URL (e.g., http://localhost:3001/mcp)
3. The agent automatically discovers available tools
4. System prompt should instruct the agent on WHEN to use each tool
```

### Exposing an n8n Workflow as MCP Server

```
1. Use the MCP Trigger node as the workflow entry point
2. Define tool operations as branches in the workflow
3. Each branch processes the tool call and returns structured results
4. Deploy and share the MCP Server URL with clients
```

### Rate Limit Handling Pattern (n8n)

For APIs with rate limits (like InfoSimples), implement a retry queue:

```
AI Agent → MCP Tool Call → API Request
                              ↓
                     IF 429 (rate limited):
                        → Wait node (retry_after seconds)
                        → Retry API Request
                        → Return result

                     IF 202 (processing):
                        → Wait node (10 seconds)
                        → Poll for status
                        → Return result when complete
```

---

## MCP Tool Documentation Best Practices

The tool `description` is critical — it's what the agent reads to decide whether and how to use the tool. Write descriptions that include:

1. **What it does** — clear, one-sentence summary
2. **When to use it** — trigger conditions
3. **What it needs** — required and optional parameters
4. **What it returns** — response structure
5. **Limitations** — rate limits, async behavior, known constraints

```
Good: "Search for real estate properties by region, price range, and
bedroom count. Use when a client expresses interest in finding a property.
Returns a list of matching properties with photos, prices, and links.
Rate limited to 30 requests per minute. May return empty results if no
properties match — in that case, suggest broadening the search."

Bad: "Search properties."
```
