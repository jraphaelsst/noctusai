# Agentic Workflow Design Methodology

## CDD+TDD — Context-Driven Development with Test-Driven Validation

> **Context is the product. Tests are the proof. Skills are the expertise. MCP is the bridge. Workflows are the runtime.**

---

## What This Is

This is a comprehensive methodology for designing, building, and validating **Agentic AI Workflows** — systems where AI agents plan, act, verify, and iterate autonomously toward goals using specialized skills, standardized integrations, and orchestrated multi-step execution.

The methodology combines two complementary frameworks:

- **CDD (Context-Driven Development)** as the primary design framework — every architectural decision is a context decision. Data models, prompts, skills, tools, and memory are all forms of context that shape system behavior.
- **TDD (Test-Driven Development)** as the validation mechanism — every behavior gets paired with concrete, testable acceptance criteria before implementation begins.

---

## Core Principles

1. **Context is the product.** When working with LLMs, the context IS the program. System prompts, tool definitions, memory configuration, and retrieval pipelines are your primary artifacts.
2. **Define the test before the solution.** For every feature, flow, endpoint, and skill — define expected behavior (inputs → outputs) before designing the implementation.
3. **Skills over monoliths.** Break expertise into composable, independently testable units of knowledge that load on demand. Never pollute context with irrelevant information.
4. **Integrate via protocol, not custom code.** Use MCP as the standardized integration layer where available. Every external capability should be an MCP Server that any agent can consume.
5. **Orchestrate, don't hardcode.** Use agentic workflow patterns (reflection, tool use, planning, multi-agent) to create systems that adapt rather than follow rigid scripts.
6. **Test at every layer.** Unit tests for logic, integration tests for APIs, evals for agent behavior, regression tracking for context drift.
7. **Correct solutions only — no workarounds.** Always implement the proper solution using the real API, SDK, or framework behavior. Monkeypatches, shims, hacks, and "temporary" fixes are never acceptable. If the correct approach requires touching more files, adding abstractions, or refactoring existing code, that is the right path. Complexity in service of correctness and solidity is a worthwhile trade-off; fragile shortcuts are not. When a library or SDK doesn't support a pattern, adapt the application code to use the SDK's actual API rather than patching the SDK to match the desired pattern.
8. **Docs stay in sync with code.** Every commit must include documentation updates to `CLAUDE.md` and `KNOWLEDGE-BASE/` files. When code changes affect router/service/page/hook counts, new or deleted modules, patterns, test counts, migration files, or infrastructure — update the corresponding docs as part of the same commit. Documentation is part of the changeset, not a separate task.

---

## The CDD+TDD Design Loop

This loop applies at every level of abstraction — from high-level user stories to individual API endpoints to agent skill definitions:

```
1. DEFINE CONTEXT    → What behavior should exist? What inputs/outputs? What constraints?
2. WRITE THE EVAL    → Define concrete acceptance criteria: given X input, expect Y output.
3. DESIGN THE SOLUTION → Skill, tool, data model, API, component, workflow — the actual artifact.
4. VALIDATE AGAINST EVALS → Does the design satisfy all defined criteria?
5. REFINE & ITERATE  → Adjust context or solution until all evals pass.
```

---

## Document Index

This methodology is organized into specialized documents. Load only what you need for the task at hand.

| Document | Purpose | When to Load |
|---|---|---|
| **[01-SKILLS.md](./01-SKILLS.md)** | Designing, structuring, and testing Skills — composable units of agent expertise | When defining what an agent knows and how it applies that knowledge |
| **[02-MCP.md](./02-MCP.md)** | MCP protocol, integration patterns, exposing and consuming MCP Servers | When connecting agents to external tools, data sources, and services |
| **[03-AGENTIC-WORKFLOWS.md](./03-AGENTIC-WORKFLOWS.md)** | Agentic design patterns, orchestration, multi-agent coordination | When designing how agents plan, act, and coordinate across steps |
| **[04-DESIGN-PHASES.md](./04-DESIGN-PHASES.md)** | The 7-phase design process from Discovery to Technical Specification | When guiding a project through the full design lifecycle |
| **[05-TESTING-EVALS.md](./05-TESTING-EVALS.md)** | TDD strategy, test pyramid, eval harnesses, regression tracking | When defining how to validate that the system works correctly |
| **[06-TECH-STACK.md](./06-TECH-STACK.md)** | Mandatory technology stack, project structure, deployment conventions | When making architectural or implementation decisions |
| **[07-TEMPLATES.md](./07-TEMPLATES.md)** | Reusable templates for Skills, test contracts, API specs, eval cases | When you need a starting point for any artifact |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                  AGENTIC WORKFLOW                     │
│              (Orchestration Layer)                    │
│         n8n / Claude Agent SDK / Custom              │
│                                                      │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐             │
│  │ Skill A │  │ Skill B │  │ Skill C │  ← Skills   │
│  │ (Qualif)│  │ (Search)│  │ (Legal) │  (Knowledge) │
│  └────┬────┘  └────┬────┘  └────┬────┘             │
│       │            │            │                    │
│  ┌────┴────────────┴────────────┴────┐              │
│  │         MCP Integration Layer      │  ← MCP      │
│  │     (Standardized Protocol)        │  (Transport) │
│  └────┬────────────┬────────────┬────┘              │
│       │            │            │                    │
│  ┌────┴────┐  ┌────┴────┐  ┌────┴────┐             │
│  │ WAHA    │  │Supabase │  │InfoSimp │  ← External │
│  │WhatsApp │  │   DB    │  │  APIs   │  (Services)  │
│  └─────────┘  └─────────┘  └─────────┘             │
└─────────────────────────────────────────────────────┘

        ↕ Validated by ↕

┌─────────────────────────────────────────────────────┐
│              TESTING & EVAL LAYER                     │
│                                                      │
│  Unit Tests → Integration Tests → Evals → E2E       │
│  (pytest)     (httpx)            (LLM)    (Playwright)│
└─────────────────────────────────────────────────────┘
```

---

## How to Use This Methodology

**If you're starting a new project:**
Start with `04-DESIGN-PHASES.md` and follow the phases sequentially. Each phase will reference the other documents as needed.

**If you're building a new Skill:**
Start with `01-SKILLS.md` for the design framework, then `07-TEMPLATES.md` for the Skill template, then `05-TESTING-EVALS.md` for the eval strategy.

**If you're integrating a new service:**
Start with `02-MCP.md` for the integration pattern, then `06-TECH-STACK.md` for implementation details.

**If you're debugging or improving an existing agent:**
Start with `05-TESTING-EVALS.md` to define what "correct" looks like, then `01-SKILLS.md` to refine the context.

---

## Glossary

| Term | Definition |
|---|---|
| **Skill** | A composable unit of agent expertise — instructions, examples, and scripts packaged for on-demand loading |
| **MCP** | Model Context Protocol — open standard for connecting AI agents to external tools and data |
| **MCP Server** | A service that exposes tools, resources, or prompts via the MCP protocol |
| **MCP Client** | The agent-side connector that consumes MCP Servers |
| **Agentic Workflow** | A multi-step execution pattern where an AI agent plans, acts, and iterates toward a goal |
| **Eval** | A test case for non-deterministic AI behavior — validates that an agent's response meets semantic or structural criteria |
| **Context** | The sum of all information available to the agent at decision time — prompts, tools, memory, retrieved data |
| **Progressive Disclosure** | Loading only the context needed for the current task, keeping the rest as lightweight metadata |
| **Test Contract** | A pre-defined set of input/output expectations for a function, endpoint, or agent behavior |
| **Context Drift** | When changes to prompts, tools, or data cause previously-correct agent behaviors to regress |
