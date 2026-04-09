# 04 — Design Phases: From Discovery to Deployment

> **Seven phases, each with clear deliverables and acceptance criteria. Never skip a phase. Never proceed without validation.**

---

## Overview

The design process has 7 phases. Each phase produces artifacts that feed the next phase AND includes acceptance criteria that validate those artifacts. This is the CDD+TDD loop applied at the project level.

```
Phase 1: Discovery & Problem Definition
Phase 2: Core Features & Scope Definition
Phase 3: User Flows & Information Architecture
Phase 4: Data Model & API Design
Phase 5: UI/UX & Component Architecture
Phase 6: Test Strategy & Eval Architecture
Phase 7: Technical Specification & Implementation Plan
```

**Rules:**
1. Complete each phase before moving on.
2. Summarize and get explicit approval at each phase boundary.
3. Each phase references the appropriate specialized documents (Skills, MCP, Testing).
4. The eval/acceptance criteria defined in earlier phases accumulate and feed Phase 6.

---

## Phase 1: Discovery & Problem Definition

**Goal:** Understand the "why" before the "what."

### Ask About
- What problem does this software solve? Who has this problem?
- Who are the target users? (personas, technical level, context of use)
- What do users currently do to solve this problem? (existing alternatives)
- What does success look like? (key metrics, outcomes)
- Are there business constraints? (timeline, budget, scale expectations)
- **Does this system involve AI agents?** If yes, what decisions should agents make vs. humans?

### CDD Lens
The problem definition IS the root context. Everything downstream inherits from it. Identify the **context boundaries** early: what data exists, who interacts with it, and through which channels.

### TDD Lens
Define what "success" looks like in measurable terms. These become the highest-level acceptance criteria for the entire project.

### Deliverables
- **Problem Statement** (2-3 paragraphs)
- **User Personas** (1-3 personas with goals and pain points)
- **Success Criteria** — 3-5 measurable outcomes
- **Agent vs. Human Decision Map** — which decisions are automated, which require human oversight

---

## Phase 2: Core Features & Scope Definition

**Goal:** Define the MVP — what to build first and what to defer.

### Ask About
- What are the must-have features for launch? (MoSCoW prioritization)
- What are nice-to-haves for later versions?
- Are there hard constraints? (compliance, integrations, accessibility)
- What is the expected data model at a high level?
- **Which features are agent-powered vs. traditional automation?**
- **What Skills does the system need?** (reference `01-SKILLS.md`)
- **What external integrations are required?** (reference `02-MCP.md`)

### CDD Lens
Each feature is a context boundary. Define what data, state, and interactions each feature owns. Identify which features are **Skill candidates** — discrete units of expertise the agent needs.

### TDD Lens
For each MVP feature, write acceptance criteria in Given/When/Then format.

### Deliverables
- **Feature Map** (MVP / v1.1 / Future) with acceptance criteria per feature
- **Skill Inventory** — list of Skills the system needs with one-line descriptions
- **Integration Map** — list of MCP Servers needed with capabilities
- **Agent Architecture Decision** — single agent vs. multi-agent, orchestration strategy

Example:
```
Feature: Lead Qualification
  Type: Agent-powered (Skill: lead-qualification)
  MCP Dependencies: waha-whatsapp (messaging), supabase (lead data)
  AC-1: Given a new WhatsApp message from an unknown number,
        when the agent processes it,
        then it classifies the lead as hot/warm/cold with confidence > 0.7
  AC-2: Given a hot lead,
        when classified,
        then the agent transfers to property search within the same session
```

---

## Phase 3: User Flows & Information Architecture

**Goal:** Map how users (and agents) move through the system.

### Design
For each core feature:
- User flow step-by-step (entry point → actions → outcome)
- **Agent flow step-by-step** (trigger → skill activation → tool use → response)
- Key screens/pages needed
- Navigation structure
- Edge cases and error states
- **Context transitions** — how the agent's context changes at each step

### CDD Lens
User flows define runtime context transitions. Each step changes what the user sees AND what context the agent holds. Map these as context state changes.

### TDD Lens
Each flow step becomes a testable assertion. Edge cases are test cases, not afterthoughts.

### Deliverables
- **User Flow Diagrams** with expected behavior at each step
- **Agent Flow Diagrams** showing skill activations and tool calls
- **Sitemap / Page Map** with route definitions
- **Edge Case Matrix** per flow
- **Context State Diagram** — how agent memory/state evolves through the flow

---

## Phase 4: Data Model & API Design

**Goal:** Define what data exists and how it is accessed.

### Design
- Database schema (SQLModel class definitions)
- RESTful API endpoints (FastAPI routers + Pydantic models)
- **MCP Server tool definitions** (reference `02-MCP.md`)
- Auth/authorization model
- Data validation rules

### CDD Lens
The data model is the structural context of the entire system. Every relationship and constraint shapes what agents can and cannot do. MCP tool schemas define the agent's action space.

### TDD Lens
Every endpoint AND every MCP tool gets a test contract defined before implementation.

### Deliverables
- **Database Schema** as SQLModel Python code
- **API Specification** table with test contracts
- **MCP Tool Specifications** with input/output schemas and test contracts
- **Pydantic Schemas** for the frontend-backend-agent contract

---

## Phase 5: UI/UX & Component Architecture

**Goal:** Define the visual structure and component hierarchy.

### Design
- Layout system
- Component breakdown per page
- Responsive behavior
- State management approach
- Loading, empty, and error states
- **Chat/conversational UI patterns** (if the system includes a chat interface)
- **Agent response rendering** (how agent outputs display in the UI)

### CDD Lens
Components are visual context containers. Each component owns a slice of context. The component tree IS the context tree.

### TDD Lens
For each component, define render states: loading, success, empty, error.

### Deliverables
- **Component Tree** per page
- **State Management Plan**
- **UI Notes** with Tailwind CSS and shadcn/ui references
- **Component Test Contracts** (render states + interactions)

---

## Phase 6: Test Strategy & Eval Architecture

**Goal:** Consolidate all test contracts into a unified testing plan. This is where TDD meets CDD comprehensively.

### Design

#### Test Pyramid for Agentic Systems
The traditional test pyramid needs adaptation for agentic workflows:

```
         /\
        /  \       E2E Tests (Playwright)
       /    \      Critical user flows end-to-end
      /------\
     /        \    Agent Evals (LLM-as-judge)
    /          \   Skill behavior, routing, multi-agent coordination
   /------------\
  /              \  Integration Tests (pytest + httpx)
 /                \ API endpoints, MCP tool calls, database ops
/------------------\
                     Unit Tests (pytest + vitest)
                     Business logic, validators, formatters, components
```

#### Agent-Specific Testing
For each Skill, define an eval harness:

```yaml
eval_harness:
  skill: lead-qualification
  runner: eval_runner.py
  cases: eval-cases/lead-qualification.yaml
  assertion_types:
    - structural: JSON schema validation of extracted criteria
    - semantic: LLM-as-judge for response quality and tone
    - behavioral: Did the agent call the right tool with right params?
  regression_tracking:
    - Store eval results per run with timestamp
    - Alert on score drop > 10% from baseline
    - Track per-case pass/fail over time
```

### Deliverables
- **Test Pyramid Breakdown** for this project
- **Backend Test Structure** (pytest + fixtures)
- **Frontend Test Structure** (Vitest + MSW)
- **Eval Harness Specs** per Skill
- **E2E Critical Paths** (Playwright scripts)
- **Regression Tracking Plan**
- **CI Integration Notes**

---

## Phase 7: Technical Specification & Implementation Plan

**Goal:** Produce the final document for implementation.

### Compile
1. Project overview and goals (from Phase 1)
2. Tech stack summary (reference `06-TECH-STACK.md`)
3. Skill inventory with SKILL.md structures (reference `01-SKILLS.md`)
4. MCP Server specifications (reference `02-MCP.md`)
5. Database schema
6. API endpoints + MCP tools (with test contracts)
7. Frontend pages and components
8. Agent architecture and workflow design (reference `03-AGENTIC-WORKFLOWS.md`)
9. Test strategy summary (from Phase 6)
10. **Build order with Definition of Done:**

```
Phase 1: Foundation
  Build: Database, auth, project structure, test infrastructure
  Done when: pytest conftest + basic model tests pass

Phase 2: MCP Servers
  Build: MCP Server wrappers for each external service
  Done when: MCP tool test contracts pass

Phase 3: Skills
  Build: SKILL.md files for each identified skill
  Done when: Eval harness passes for each Skill (>85% of cases)

Phase 4: Core API
  Build: FastAPI endpoints, Pydantic schemas
  Done when: API integration tests pass

Phase 5: Agent Orchestration
  Build: n8n workflows, routing, memory, multi-agent coordination
  Done when: End-to-end agent eval scenarios pass

Phase 6: Frontend
  Build: React pages, components, chat UI
  Done when: Component tests + visual regression pass

Phase 7: Integration & Polish
  Build: Connect all layers, error handling, guardrails
  Done when: E2E Playwright critical paths pass
```

11. **Implementation prompt** — ready-to-use prompt for the builder agent (Replit Agent, Claude Code, etc.) that includes the test-first workflow.

### Deliverables
- **Technical Specification Document** (comprehensive, implementation-ready)
- **Build Order** with Definition of Done per phase
- **Implementation Prompt** for builder agent
