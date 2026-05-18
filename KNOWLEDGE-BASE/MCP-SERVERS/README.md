# MCP Servers

> Reference: [02-MCP.md](../INSTRUCTIONS/02-MCP.md) for design patterns and tool documentation best practices.

---

## Built MCP Servers

### github — GitHub connector MCP

**Type**: Connector (composes `mcp/_kit`; wraps the authenticated `gh` CLI)

The **GitHub side of the team methodology** — PR lifecycle + CI-check
visibility + repo introspection — as `github.<service>.<action>` tools.
Raw `git commit`/`git push` are deliberately NOT exposed (they stay in
the commit-only-your-own-work git workflow). Registration is **user-gated**
(MCP keep-list rule). Full reference: [github.md](github.md).

Tools: `github.pr.{list,view,diff,checks,create,ready}` ·
`github.repo.view` · `github.diagnostics.connection_status`. Writes are
confirm-gated (412); `gh` absent/logged-out is a typed never-faked signal.

---

## Planned MCP Servers

### supabase-properties

**Type**: Direct Proxy + Aggregator

Exposes the Supabase ativos (properties) database as MCP tools for AI agents. Enables property search, filtering, and retrieval without direct database access.

**Planned tools:**
- `search_properties` — Filter ativos by type, region, price, specs
- `get_property` — Fetch single ativo by ID with full details
- `list_matches` — Retrieve match results for an ativo

### waha-whatsapp

**Type**: Direct Proxy

Wraps the WAHA WhatsApp HTTP API as MCP tools. Enables agents to send messages and retrieve conversation history.

**Planned tools:**
- `send_message` — Send text message to a phone number
- `send_property_card` — Send formatted property listing
- `get_conversation` — Retrieve message history for a contact

---

## Adding a New MCP Server

1. Create a directory: `MCP-SERVERS/{server-name}/`
2. Add `server.py` — MCP server implementation
3. Add `tools.json` — Tool definitions following the template in [07-TEMPLATES.md](../INSTRUCTIONS/07-TEMPLATES.md)
4. Document in this README
5. Add eval cases in `EVALS/cases/`

## Security Checklist

Per [02-MCP.md](../INSTRUCTIONS/02-MCP.md):

- [ ] API keys in environment variables, never hardcoded
- [ ] Rate limiting implemented and documented
- [ ] Input validation on all tool parameters
- [ ] Error handling returns structured errors
- [ ] Timeout handling with configurable timeouts
- [ ] Logging of all invocations (without sensitive data)
- [ ] Auth scope: each server only has access needed
