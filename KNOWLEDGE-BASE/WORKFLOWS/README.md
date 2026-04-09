# Workflows

> Reference: [03-AGENTIC-WORKFLOWS.md](../INSTRUCTIONS/03-AGENTIC-WORKFLOWS.md) for orchestration patterns and design guidelines.

---

## Orchestration Engine

**n8n** self-hosted at `n8n.noctusai.com` on VPS (Hostinger, 72.61.28.36).

---

## Active Workflows

> Add n8n workflow JSON exports here as they are created. Each workflow should have a corresponding entry below.

_No workflows exported yet._

---

## Planned Workflows

### Lead Qualification

**Pattern**: Reflection + Tool Use
**Trigger**: Webhook (new lead from WhatsApp or web form)
**Flow**: Receive lead → Enrich profile → Score lead (AI) → Route to appropriate funnel stage → Notify assigned agent

### Property Matching Notification

**Pattern**: Tool Use
**Trigger**: Scheduled (daily) or webhook (new ativo created)
**Flow**: Detect new/updated ativos → Generate matches → Notify agents with high-score matches via WhatsApp

### Client Follow-Up

**Pattern**: Planning + Multi-Agent
**Trigger**: Scheduled (daily check for stale leads)
**Flow**: Query leads without recent activity → Generate personalized follow-up message → Send via WhatsApp → Log activity

---

## Adding a New Workflow

1. Design the workflow in n8n following patterns from [03-AGENTIC-WORKFLOWS.md](../INSTRUCTIONS/03-AGENTIC-WORKFLOWS.md)
2. Export the workflow JSON from n8n
3. Save as `WORKFLOWS/{workflow-name}.json`
4. Document in this README (pattern, trigger, flow)
5. Add eval cases if the workflow involves AI agent behavior

## Guardrails Checklist

Per [03-AGENTIC-WORKFLOWS.md](../INSTRUCTIONS/03-AGENTIC-WORKFLOWS.md):

- [ ] Max tool calls per execution defined
- [ ] Timeout configured
- [ ] Error handling with fallback behavior
- [ ] Human-in-the-loop for high-value actions
- [ ] Rate limiting on external API calls
- [ ] Input/output guardrails documented
