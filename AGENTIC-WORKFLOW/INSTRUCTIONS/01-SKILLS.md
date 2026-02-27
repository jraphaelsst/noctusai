# 01 — Skills: Composable Units of Agent Expertise

> **A Skill is a context package. It teaches an agent HOW to do something specific, loads only when needed, and can be tested independently.**

---

## What Is a Skill

A Skill is a self-contained unit of **procedural knowledge** — instructions, examples, scripts, and templates that teach an agent how to perform a specific type of task. Unlike a general system prompt that's always in context, a Skill uses **progressive disclosure**: the agent sees only the Skill's name and description at all times, and loads the full instructions only when the current task matches.

Think of Skills as the difference between:
- **Monolithic prompt** = calling every employee into a meeting room for every question
- **Skills** = maintaining a directory of experts and calling each one only when their expertise is needed

---

## Skill Anatomy

Every Skill follows the same structure:

```
skill-name/
├── SKILL.md          # Main instruction file (required)
├── scripts/          # Executable scripts (optional)
│   ├── search.py
│   └── validate.sh
├── references/       # Reference data, schemas, docs (optional)
│   ├── api-schema.json
│   └── business-rules.md
├── assets/           # Templates, images, fonts (optional)
│   └── report-template.html
└── examples/         # Few-shot examples for the agent (optional)
    ├── input-01.json
    └── output-01.json
```

### The SKILL.md File

This is the heart of every Skill. It contains:

```markdown
---
name: property-search
description: >
  Search for real estate properties based on client criteria including
  region, price range, bedrooms, and property type. Use when a lead
  provides search preferences or asks about available properties.
version: 1.0.0
triggers:
  - property search
  - find properties
  - available homes
  - looking for a house
dependencies:
  - mcp: supabase-properties
  - mcp: geolocation-api
---

# Property Search Skill

## Purpose
Execute intelligent property searches that match client criteria against
the property database, handling partial information, suggesting alternatives
when no exact matches exist, and formatting results for WhatsApp delivery.

## Instructions

### Step 1: Extract Search Criteria
From the client's message, extract:
- **Region** (required): Map informal names to database regions
  - "Granja Viana" → region_code: "GV"
  - "Cotia centro" → region_code: "CT"
- **Price range** (optional): Extract min/max, default currency BRL
- **Bedrooms** (optional): Minimum number
- **Property type** (optional): house, apartment, land, commercial

### Step 2: Execute Search
Call the `search_properties` tool with extracted filters.
If no results: broaden by removing the least important filter (property_type first, then bedrooms).

### Step 3: Format Response
For WhatsApp delivery, format each result as:
🏠 *{title}*
📍 {neighborhood}, {region}
💰 R$ {price}
🛏️ {bedrooms} quartos | 📐 {area}m²
🔗 {link}

### Edge Cases
- Client provides only region → search all properties in region, ask for preferences
- Client provides budget in USD → convert to BRL using current rate
- No results after broadening → apologize and offer to notify when new listings match

## Examples

### Example 1: Full criteria
**Input:** "Quero uma casa em Granja Viana, até 1.5M, 3 quartos"
**Expected tool call:** search_properties({region: "GV", max_price: 1500000, bedrooms: 3, type: "house"})
**Expected behavior:** Return formatted results or broaden if empty

### Example 2: Partial criteria
**Input:** "O que tem disponível na Granja?"
**Expected tool call:** search_properties({region: "GV"})
**Expected behavior:** Return top results, then ask about preferences
```

---

## Skill Design Principles

### 1. Single Responsibility
Each Skill should do **one thing well**. If a Skill starts handling both property search AND lead qualification, split it into two Skills.

Bad: `real-estate-agent` (does everything)
Good: `property-search`, `lead-qualification`, `legal-certificates`, `appointment-scheduling`

### 2. Clear Trigger Description
The `description` field is the **only thing the agent sees** before deciding to load the Skill. It must be specific enough to trigger correctly and distinct enough to avoid false activations.

Bad description: "Helps with real estate tasks"
Good description: "Search for real estate properties based on client criteria including region, price range, bedrooms, and property type. Use when a lead provides search preferences or asks about available properties."

### 3. Explicit Dependencies
Declare which MCP Servers, APIs, or other Skills this Skill depends on. This enables validation and testing.

### 4. Examples as Tests
Every Skill should include examples that double as eval cases. The examples section IS your test suite for the Skill's behavior.

### 5. Graceful Degradation
Always define edge cases and fallback behavior. What happens when the API is down? When data is incomplete? When the user's request is ambiguous?

---

## Skill Categories

### Knowledge Skills
Provide domain expertise without executing actions.
- Business rules and policies
- Regulatory compliance knowledge
- Style guides and brand guidelines

### Action Skills
Execute operations through tools and MCP Servers.
- Property search
- Certificate generation
- Appointment scheduling

### Analysis Skills
Process data and provide insights.
- Lead qualification scoring
- Market analysis
- Document review

### Communication Skills
Handle formatting, tone, and delivery.
- WhatsApp message formatting
- Email composition
- Report generation

---

## Designing Skills with CDD+TDD

Follow the methodology's core loop applied specifically to Skills:

### 1. Define Context (CDD)
What expertise does this Skill provide? What's the boundary of its knowledge? What information does it need from the conversation to function?

```
Skill: lead-qualification
Context boundary: Evaluate a real estate lead's readiness to buy/rent
Needs from conversation: Lead's messages, extracted preferences, interaction history
Does NOT handle: Property search, appointment setting, document generation
```

### 2. Write the Eval (TDD)
Before writing the Skill instructions, define the test cases:

```yaml
# eval-cases/lead-qualification.yaml
cases:
  - id: hot-lead
    input: "Preciso comprar urgente, já tenho financiamento aprovado, quero até 2M na Granja Viana"
    expected:
      classification: "hot"
      confidence: ">= 0.8"
      extracted_criteria:
        urgency: high
        financing: approved
        budget: 2000000
        region: "Granja Viana"
      next_action: "transfer_to_agent"

  - id: cold-lead
    input: "Oi, só tô dando uma olhada"
    expected:
      classification: "cold"
      confidence: ">= 0.6"
      next_action: "nurture_sequence"

  - id: ambiguous-lead
    input: "Quanto custa um apartamento aí?"
    expected:
      classification: "warm"
      next_action: "ask_qualifying_questions"
      questions_should_include: ["region", "budget", "timeline"]
```

### 3. Design the Skill
Write the SKILL.md with instructions that will make the agent pass all eval cases.

### 4. Validate Against Evals
Run the eval suite against the Skill. For each failing case, refine the instructions.

### 5. Refine & Iterate
Adjust prompt wording, add/remove examples, tighten edge case handling until all evals pass.

---

## Skill Composition

Skills can reference and depend on each other. A complex workflow might involve:

```
Lead sends message
  → [lead-qualification] classifies intent
    → IF hot lead:
      → [property-search] finds matching properties
      → [whatsapp-formatter] formats results for delivery
    → IF needs documents:
      → [legal-certificates] generates required certs
    → IF appointment request:
      → [appointment-scheduler] books viewing
```

The orchestrator (n8n workflow, Agent SDK, or manual routing) decides which Skills to activate. Skills themselves should NOT call other Skills — they provide expertise and let the orchestrator compose them.

---

## Skill Versioning

Skills evolve. Track versions and changes:

```markdown
---
version: 1.2.0
changelog:
  - 1.2.0: Added USD to BRL conversion for international leads
  - 1.1.0: Expanded region mapping to include Vargem Grande Paulista
  - 1.0.0: Initial release with core search functionality
---
```

When updating a Skill, **always re-run the eval suite** to catch regressions. This is where TDD pays off — you have confidence that changes don't break existing behavior.

---

## Skill Quality Checklist

Before deploying a Skill, verify:

- [ ] **Description** is specific and distinct from other Skills
- [ ] **Instructions** are clear, step-by-step, and unambiguous
- [ ] **Examples** cover happy path, edge cases, and error states
- [ ] **Dependencies** are explicitly declared
- [ ] **Eval cases** exist and pass
- [ ] **Edge cases** are documented with expected fallback behavior
- [ ] **Version** is set and changelog is updated
- [ ] **Single responsibility** — Skill does one thing well
