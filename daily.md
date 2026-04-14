# Daily Life — Implementation Prompt

> Send this entire file as a single prompt to the agent that will build the system.
> This document was produced through an architecture design session. Every decision below was deliberated and intentional.

---

You are building a personal daily life automation system. This is a **code project** — you will write real Python code, not just plan or describe. The system is a custom Python CLI that runs in the terminal, powered by AI agents that execute tasks automatically on my behalf.

## Architecture context

This system was designed through a deliberate architecture session. Here are the key decisions and why:

1. **Two-tier processing**: Direct commands (free, instant, no LLM) for routine operations + agno-based AI reasoning (LLM call, costs tokens) for complex requests. ~90% of daily interactions should be Tier 1.
2. **agno for AI reasoning**: We chose the `agno` library specifically for agent teams. No substitutes.
3. **No MCP servers as tools**: We evaluated MCP-first vs code-first and chose code. MCPs are dumb pipes — they can't do business logic, workflows, or custom orchestration. Our tools need to compose actions, not just forward API calls.
4. **Own Python CLI, not Claude Code**: The terminal interface is our own Python program. Claude (or any LLM) is only consumed when agno agents need to reason. The CLI itself is free to run.
5. **Command knowledge in database**: Known commands, patterns, and context rules are stored in Supabase so the system gets smarter over time and the knowledge persists across sessions.
6. **Future product**: This system may become a commercial SaaS platform. A parallel web version already exists as a NoctusAI product (`products/daily-life/`). Both share the same database schema. Architecture must stay modular — agents decoupled from CLI, tools decoupled from agents.

## What you're building

A terminal-based productivity system at `/Users/rapha/Documents/Daily Life/` with three processing layers:

**Layer 1 — Direct commands** (dictionary lookup, instant, free):
```
> list tasks
> complete task 3
> show today
```

**Layer 2 — Pattern matching** (regex/keyword extraction, instant, free):
```
> add task review PR by friday high priority
> schedule meeting with John tomorrow at 3pm
> check in gym
```

**Layer 3 — AI reasoning** (agno + LLM, slower, costs tokens):
```
> what should I prioritize today based on my deadlines?
> draft an email to the team summarizing this week's progress
> I'm overwhelmed, help me reorganize my tasks
```

The system tries Layer 1 first, then Layer 2, then Layer 3. The goal is to handle as much as possible without an LLM call.

## Tech stack

- **Python 3.11+**
- **agno** (https://github.com/agno-agi/agno) — agent framework for AI reasoning (Layer 3)
- **supabase-py** — database client
- **Resend or Gmail API** — email sending
- **Google Calendar API** — calendar management
- **WAHA or Twilio** — WhatsApp messaging
- **python-dotenv** — environment config
- **rich** — terminal UI formatting (tables, colors, panels)

## Project structure

```
/Users/rapha/Documents/Daily Life/
├── README.md
├── MASTER-PROMPT.md              # This file's content, persisted
├── COMMANDS.md                   # Command reference (see companion doc)
├── requirements.txt
├── .env                          # Supabase URL, keys, API keys
├── .env.example                  # Template without secrets
├── cli/
│   ├── __init__.py
│   ├── app.py                    # Main loop: input → resolve → execute → display
│   ├── resolver.py               # Three-tier resolution: direct → pattern → agno
│   ├── display.py                # Rich terminal formatting (tables, panels, colors)
│   └── history.py                # Logs every command to command_history table
├── commands/
│   ├── __init__.py
│   ├── registry.py               # Loads commands from DB + code, builds lookup maps
│   ├── tasks_cmd.py              # Direct handlers for task operations
│   ├── habits_cmd.py             # Direct handlers for habit/goal operations
│   ├── schedule_cmd.py           # Direct handlers for calendar operations
│   ├── notes_cmd.py              # Direct handlers for notes operations
│   ├── briefing_cmd.py           # Daily/weekly briefing composers
│   └── system_cmd.py             # Meta commands: help, stats, history, config
├── patterns/
│   ├── __init__.py
│   ├── parser.py                 # Regex + keyword extraction engine
│   └── definitions.py            # Pattern definitions loaded from DB + code
├── agents/
│   ├── __init__.py
│   ├── orchestrator.py           # Main agno Team — routes to the right agent
│   ├── task_agent.py             # Complex task reasoning (prioritize, reorganize)
│   ├── habit_agent.py            # Habit analysis, streak insights, suggestions
│   ├── calendar_agent.py         # Schedule optimization, conflict resolution
│   ├── email_agent.py            # Draft and send emails
│   ├── message_agent.py          # WhatsApp/SMS messaging
│   ├── briefing_agent.py         # Intelligent daily summaries with recommendations
│   └── notes_agent.py            # Note search, summarization, linking
├── tools/
│   ├── __init__.py
│   ├── supabase_tools.py         # All Supabase CRUD operations
│   ├── email_tools.py            # Email sending via Resend or Gmail
│   ├── calendar_tools.py         # Google Calendar API wrapper
│   └── whatsapp_tools.py         # WAHA/Twilio wrapper
├── knowledge/
│   ├── __init__.py
│   ├── loader.py                 # Loads commands, patterns, context from Supabase
│   ├── context.py                # Contact resolution, defaults, user preferences
│   └── learner.py                # Promotes successful LLM interactions to patterns
├── config/
│   ├── __init__.py
│   └── settings.py               # Pydantic settings from .env
├── db/
│   └── migration.sql             # Full database schema
└── main.py                       # Entry point: python main.py
```

## Database schema

### Supabase project setup

Create a **separate Supabase project** named "daily life" for this project using the Supabase MCP. Region: `sa-east-1`, organization: `madwjzirwrnqjqvwwqat`. After creation, apply the migration SQL below.

This DB holds personal information, financial data, appointments, tasks, notes, and the command knowledge base. The schema mirrors the NoctusAI platform's `daily_life` schema (for data tables) plus additional tables for the command knowledge system.

### Data tables (shared with NoctusAI platform)

```sql
CREATE SCHEMA IF NOT EXISTS daily_life;

GRANT USAGE ON SCHEMA daily_life TO anon, authenticated, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA daily_life TO anon, authenticated, service_role;
GRANT ALL ON ALL SEQUENCES IN SCHEMA daily_life TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA daily_life GRANT ALL ON TABLES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES IN SCHEMA daily_life GRANT ALL ON SEQUENCES TO anon, authenticated, service_role;

-- Tasks
CREATE TABLE daily_life.tarefas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    org_id UUID NOT NULL,
    titulo TEXT NOT NULL,
    descricao TEXT,
    prioridade TEXT NOT NULL DEFAULT 'media' CHECK (prioridade IN ('alta', 'media', 'baixa')),
    prioridade_ordem INT NOT NULL DEFAULT 2,
    categoria TEXT,
    data_vencimento DATE,
    status TEXT NOT NULL DEFAULT 'pendente' CHECK (status IN ('pendente', 'em_progresso', 'concluida', 'cancelada')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE daily_life.tarefas ENABLE ROW LEVEL SECURITY;
CREATE POLICY "tarefas_all" ON daily_life.tarefas FOR ALL TO authenticated USING (user_id = (SELECT auth.uid())) WITH CHECK (user_id = (SELECT auth.uid()));
CREATE INDEX idx_dl_tarefas_user ON daily_life.tarefas(user_id);
CREATE INDEX idx_dl_tarefas_user_status ON daily_life.tarefas(user_id, status);

-- Goals & Habits
CREATE TABLE daily_life.metas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    org_id UUID NOT NULL,
    titulo TEXT NOT NULL,
    descricao TEXT,
    tipo TEXT NOT NULL DEFAULT 'meta' CHECK (tipo IN ('meta', 'habito')),
    categoria TEXT,
    meta_valor NUMERIC,
    valor_atual NUMERIC DEFAULT 0,
    unidade TEXT,
    frequencia TEXT CHECK (frequencia IS NULL OR frequencia IN ('diario', 'semanal', 'mensal')),
    data_limite DATE,
    status TEXT NOT NULL DEFAULT 'ativa' CHECK (status IN ('ativa', 'concluida', 'pausada', 'cancelada')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE daily_life.metas ENABLE ROW LEVEL SECURITY;
CREATE POLICY "metas_all" ON daily_life.metas FOR ALL TO authenticated USING (user_id = (SELECT auth.uid())) WITH CHECK (user_id = (SELECT auth.uid()));

-- Habit Check-ins
CREATE TABLE daily_life.checkins (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    meta_id UUID NOT NULL REFERENCES daily_life.metas(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    data DATE NOT NULL,
    valor NUMERIC DEFAULT 1,
    nota TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(meta_id, data)
);
ALTER TABLE daily_life.checkins ENABLE ROW LEVEL SECURITY;
CREATE POLICY "checkins_all" ON daily_life.checkins FOR ALL TO authenticated USING (user_id = (SELECT auth.uid())) WITH CHECK (user_id = (SELECT auth.uid()));

-- Calendar Events
CREATE TABLE daily_life.eventos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    org_id UUID NOT NULL,
    titulo TEXT NOT NULL,
    descricao TEXT,
    categoria TEXT,
    data_inicio TIMESTAMPTZ NOT NULL,
    data_fim TIMESTAMPTZ,
    dia_inteiro BOOLEAN DEFAULT FALSE,
    local TEXT,
    lembrete_minutos INT,
    cor TEXT,
    status TEXT NOT NULL DEFAULT 'agendado' CHECK (status IN ('agendado', 'concluido', 'cancelado')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE daily_life.eventos ENABLE ROW LEVEL SECURITY;
CREATE POLICY "eventos_all" ON daily_life.eventos FOR ALL TO authenticated USING (user_id = (SELECT auth.uid())) WITH CHECK (user_id = (SELECT auth.uid()));

-- Notes
CREATE TABLE daily_life.notas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    org_id UUID NOT NULL,
    titulo TEXT NOT NULL,
    conteudo TEXT,
    categoria TEXT,
    tags TEXT[] DEFAULT '{}',
    fixada BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE daily_life.notas ENABLE ROW LEVEL SECURITY;
CREATE POLICY "notas_all" ON daily_life.notas FOR ALL TO authenticated USING (user_id = (SELECT auth.uid())) WITH CHECK (user_id = (SELECT auth.uid()));

-- Productivity Metrics
CREATE TABLE daily_life.metricas_produtividade (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    data DATE NOT NULL,
    tarefas_concluidas INT DEFAULT 0,
    tarefas_criadas INT DEFAULT 0,
    checkins_realizados INT DEFAULT 0,
    eventos_do_dia INT DEFAULT 0,
    notas_criadas INT DEFAULT 0,
    score_produtividade NUMERIC,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, data)
);
ALTER TABLE daily_life.metricas_produtividade ENABLE ROW LEVEL SECURITY;
CREATE POLICY "metricas_all" ON daily_life.metricas_produtividade FOR ALL TO authenticated USING (user_id = (SELECT auth.uid())) WITH CHECK (user_id = (SELECT auth.uid()));

-- Focus Sessions
CREATE TABLE daily_life.sessoes_foco (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    tarefa_id UUID REFERENCES daily_life.tarefas(id) ON DELETE SET NULL,
    tipo TEXT NOT NULL DEFAULT 'pomodoro' CHECK (tipo IN ('pomodoro', 'deep_work', 'livre')),
    duracao_minutos INT NOT NULL,
    inicio TIMESTAMPTZ NOT NULL,
    fim TIMESTAMPTZ,
    nota TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE daily_life.sessoes_foco ENABLE ROW LEVEL SECURITY;
CREATE POLICY "sessoes_all" ON daily_life.sessoes_foco FOR ALL TO authenticated USING (user_id = (SELECT auth.uid())) WITH CHECK (user_id = (SELECT auth.uid()));

-- Auto-update timestamps
CREATE OR REPLACE FUNCTION daily_life.set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql SET search_path = daily_life AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END; $$;

CREATE TRIGGER tarefas_updated_at BEFORE UPDATE ON daily_life.tarefas FOR EACH ROW EXECUTE FUNCTION daily_life.set_updated_at();
CREATE TRIGGER metas_updated_at BEFORE UPDATE ON daily_life.metas FOR EACH ROW EXECUTE FUNCTION daily_life.set_updated_at();
CREATE TRIGGER eventos_updated_at BEFORE UPDATE ON daily_life.eventos FOR EACH ROW EXECUTE FUNCTION daily_life.set_updated_at();
CREATE TRIGGER notas_updated_at BEFORE UPDATE ON daily_life.notas FOR EACH ROW EXECUTE FUNCTION daily_life.set_updated_at();
```

### Command knowledge tables (CLI-specific)

```sql
-- Known commands: the CLI's vocabulary
CREATE TABLE daily_life.commands (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trigger TEXT NOT NULL,
    type TEXT NOT NULL CHECK (type IN ('exact', 'pattern', 'alias')),
    handler TEXT NOT NULL,
    parameters JSONB DEFAULT '{}',
    description TEXT,
    category TEXT,
    examples TEXT[] DEFAULT '{}',
    enabled BOOLEAN DEFAULT TRUE,
    usage_count INT DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE daily_life.commands ENABLE ROW LEVEL SECURITY;
CREATE POLICY "commands_service" ON daily_life.commands FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "commands_read" ON daily_life.commands FOR SELECT TO authenticated USING (true);
CREATE INDEX idx_dl_commands_type ON daily_life.commands(type);
CREATE INDEX idx_dl_commands_trigger ON daily_life.commands(trigger);

-- Intent patterns: regex/keyword → command mapping
CREATE TABLE daily_life.intent_patterns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pattern TEXT NOT NULL,
    pattern_type TEXT NOT NULL DEFAULT 'keyword' CHECK (pattern_type IN ('regex', 'keyword', 'fuzzy')),
    mapped_command_id UUID REFERENCES daily_life.commands(id) ON DELETE CASCADE,
    handler TEXT,
    parameter_extraction JSONB DEFAULT '{}',
    confidence_threshold NUMERIC DEFAULT 0.8,
    examples TEXT[] DEFAULT '{}',
    enabled BOOLEAN DEFAULT TRUE,
    usage_count INT DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE daily_life.intent_patterns ENABLE ROW LEVEL SECURITY;
CREATE POLICY "patterns_service" ON daily_life.intent_patterns FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE POLICY "patterns_read" ON daily_life.intent_patterns FOR SELECT TO authenticated USING (true);

-- Context rules: personal knowledge (contacts, defaults, preferences)
CREATE TABLE daily_life.context_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    rule_type TEXT NOT NULL CHECK (rule_type IN ('contact', 'location', 'default', 'alias', 'preference')),
    key TEXT NOT NULL,
    value JSONB NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE daily_life.context_rules ENABLE ROW LEVEL SECURITY;
CREATE POLICY "context_all" ON daily_life.context_rules FOR ALL TO authenticated USING (user_id = (SELECT auth.uid())) WITH CHECK (user_id = (SELECT auth.uid()));
CREATE INDEX idx_dl_context_user_type ON daily_life.context_rules(user_id, rule_type);

-- Command history: every interaction logged for analytics and learning
CREATE TABLE daily_life.command_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    raw_input TEXT NOT NULL,
    resolved_command TEXT,
    resolved_handler TEXT,
    tier_used TEXT NOT NULL CHECK (tier_used IN ('direct', 'pattern', 'llm', 'failed')),
    parameters JSONB DEFAULT '{}',
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT,
    execution_time_ms INT,
    tokens_used INT DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE daily_life.command_history ENABLE ROW LEVEL SECURITY;
CREATE POLICY "history_all" ON daily_life.command_history FOR ALL TO authenticated USING (user_id = (SELECT auth.uid())) WITH CHECK (user_id = (SELECT auth.uid()));
CREATE INDEX idx_dl_history_user ON daily_life.command_history(user_id);
CREATE INDEX idx_dl_history_created ON daily_life.command_history(created_at);
CREATE INDEX idx_dl_history_tier ON daily_life.command_history(tier_used);

-- Learned promotions: LLM interactions promoted to patterns (learner.py)
CREATE TABLE daily_life.learned_promotions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    source_history_id UUID REFERENCES daily_life.command_history(id) ON DELETE SET NULL,
    raw_input TEXT NOT NULL,
    extracted_intent TEXT NOT NULL,
    extracted_handler TEXT NOT NULL,
    extracted_parameters JSONB DEFAULT '{}',
    suggested_pattern TEXT,
    suggested_pattern_type TEXT DEFAULT 'keyword' CHECK (suggested_pattern_type IN ('regex', 'keyword', 'fuzzy')),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'auto_approved')),
    occurrences INT DEFAULT 1,
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    promoted_to_pattern_id UUID REFERENCES daily_life.intent_patterns(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE daily_life.learned_promotions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "promotions_all" ON daily_life.learned_promotions FOR ALL TO authenticated USING (user_id = (SELECT auth.uid())) WITH CHECK (user_id = (SELECT auth.uid()));
CREATE INDEX idx_dl_promotions_user_status ON daily_life.learned_promotions(user_id, status);
CREATE INDEX idx_dl_promotions_intent ON daily_life.learned_promotions(extracted_intent);

CREATE TRIGGER commands_updated_at BEFORE UPDATE ON daily_life.commands FOR EACH ROW EXECUTE FUNCTION daily_life.set_updated_at();
CREATE TRIGGER context_updated_at BEFORE UPDATE ON daily_life.context_rules FOR EACH ROW EXECUTE FUNCTION daily_life.set_updated_at();
```

## Execution plan — do this in order

### Phase 1: Project scaffold + Supabase setup

1. Create the project directory at `/Users/rapha/Documents/Daily Life/`
2. Create `requirements.txt`, `.env.example`, `config/settings.py`
3. Use Supabase MCP to create a new project named "daily life" in region `sa-east-1`, org `madwjzirwrnqjqvwwqat`
4. Apply ALL migration SQL above (data tables + command knowledge tables) to the new project
5. Save the Supabase URL and keys to `.env`
6. Create `db/migration.sql` with the full schema for reference
7. Create `tools/supabase_tools.py` — CRUD functions for every table (using service_role key)
8. Test the Supabase connection works

### Phase 2: CLI framework + direct commands (Tier 1)

1. Create `cli/app.py` — main input loop with rich formatting
2. Create `cli/display.py` — rich tables, panels, colors for terminal output
3. Create `cli/resolver.py` — three-tier resolution engine (direct → pattern → agno)
4. Create `cli/history.py` — logs every command to `command_history`
5. Create `commands/registry.py` — loads commands from DB + hardcoded defaults
6. Create `commands/tasks_cmd.py` — direct handlers: list, add, complete, delete tasks
7. Create `commands/habits_cmd.py` — direct handlers: list habits, check in, show streaks
8. Create `commands/schedule_cmd.py` — direct handlers: today, add event, list events
9. Create `commands/notes_cmd.py` — direct handlers: add note, list, search, pin
10. Create `commands/briefing_cmd.py` — daily/weekly briefing from data
11. Create `commands/system_cmd.py` — help, stats, history, version
12. Seed the `commands` table with all known commands from `COMMANDS.md`
13. Seed the `intent_patterns` table with initial patterns
14. Test: type "list tasks" → get a formatted table. No LLM involved.

### Phase 3: Pattern matching (Tier 2)

1. Create `patterns/parser.py` — regex + keyword extraction engine
2. Create `patterns/definitions.py` — loads patterns from DB, matches user input
3. Wire the resolver to try pattern matching before falling back to agno
4. Test: "add task review PR by friday high" → creates task with parsed fields. No LLM.

### Phase 4: agno AI reasoning (Tier 3)

1. Read the agno docs thoroughly — understand Agent, Tool, and Team APIs
2. Create `agents/task_agent.py` — complex task reasoning (prioritize, reorganize, suggest)
3. Create `agents/briefing_agent.py` — intelligent summaries with recommendations
4. Create `agents/orchestrator.py` — agno Team that routes complex requests
5. Wire the resolver: when Tiers 1-2 fail, send to agno Team
6. Create `agents/email_agent.py` — draft and send emails
7. Create `agents/calendar_agent.py` — schedule optimization, conflict resolution
8. Create `agents/message_agent.py` — WhatsApp messaging
9. Test: "what should I prioritize today?" → agno agent reasons over your data

### Phase 5: Knowledge system + learning

1. Create `knowledge/loader.py` — loads commands, patterns, context from Supabase on startup
2. Create `knowledge/context.py` — resolves "John" to john@company.com, defaults, preferences
3. Create `knowledge/learner.py` — the automatic promotion engine (see detailed spec below)
4. Seed `context_rules` with personal contacts, locations, defaults
5. Test: the system gets smarter as you use it

#### learner.py — Automatic promotion engine (detailed spec)

This is the system's self-improvement loop. It watches `command_history` for patterns in LLM-handled interactions and promotes them to Tier 1/2 commands so the same request never needs the LLM twice.

**How it works:**

1. **After every successful LLM interaction** (tier_used='llm', success=true), the learner extracts:
   - The raw user input
   - Which agent handled it
   - What handler/tool was ultimately called
   - What parameters were extracted
   - A suggested regex/keyword pattern that would match this input

2. **It checks `learned_promotions` for similar intents.** If a matching intent already exists, it increments `occurrences` and updates `last_seen_at`. If not, it creates a new pending promotion.

3. **Auto-approval threshold:** When a promotion reaches **3 occurrences** (same intent, different raw inputs, all successful), it auto-promotes:
   - Creates a new row in `intent_patterns` with the suggested pattern
   - Updates the promotion status to `auto_approved`
   - Links `promoted_to_pattern_id` to the new pattern
   - The next time the user types something similar, Tier 2 catches it — no LLM needed

4. **Manual review via CLI:** The user can also review pending promotions:
   - `learner status` — show pending promotions with occurrence counts
   - `learner approve {id}` — manually promote to a pattern
   - `learner reject {id}` — mark as rejected (won't auto-promote)
   - `learner history` — show recent promotions and their effectiveness

5. **Similarity matching:** When comparing new LLM interactions against existing promotions, use:
   - Same `extracted_handler` (exact match)
   - Similar `extracted_intent` (normalized lowercase, stripped of specific values like dates/names)
   - Example: "add task review PR by friday" and "add task fix bug by monday" have the same intent (`create_task`) even though the specifics differ

**The feedback loop:**

```
User types something new
  → Tier 1 miss, Tier 2 miss
  → Tier 3 (LLM) handles it successfully
  → learner.py extracts the interaction pattern
  → Stores in learned_promotions (occurrences=1)
  
User types something similar again
  → Tier 1 miss, Tier 2 miss (pattern not promoted yet)
  → Tier 3 handles it again
  → learner.py finds existing promotion, increments to occurrences=2
  
User types it a third time
  → Tier 1 miss, Tier 2 miss
  → Tier 3 handles it
  → learner.py increments to occurrences=3 → AUTO-PROMOTE
  → Creates intent_pattern in database
  
User types it a fourth time
  → Tier 1 miss
  → Tier 2 MATCHES the new pattern → handled directly, no LLM
  → Free, instant, learned from experience
```

**The LLM extraction prompt** (used inside learner.py to extract structure from successful interactions):

When the LLM successfully handles a request, ask it to also return structured metadata:
```json
{
  "intent": "create_task",
  "handler": "tasks_cmd.create",
  "parameters": {"titulo": "...", "prioridade": "...", "data_vencimento": "..."},
  "suggested_pattern": "add task {title} by {date}, {priority}",
  "confidence": 0.95
}
```

This metadata is what gets stored in `learned_promotions`. The LLM does the hard work of figuring out the pattern once — then the system never needs the LLM for that pattern again.

### Phase 6: Polish + external integrations

1. Wire Resend/Gmail for actual email sending
2. Wire Google Calendar API for real calendar sync
3. Wire WAHA/Twilio for WhatsApp
4. Add error handling: missing API keys = skip that integration gracefully
5. Add `rich` progress bars for long operations
6. Write `README.md` with setup and usage guide
7. Persist this prompt as `MASTER-PROMPT.md`

## Rules for you

- **Write real code.** Every handler, agent, tool, and integration must be functional Python.
- **Use agno properly.** Read their docs. Don't mock the framework or substitute.
- **Use Supabase service_role key** for DB operations — this is a personal tool.
- **Tier 1 first.** Get direct commands working before pattern matching. Get patterns working before agno. Each tier must work independently.
- **No web server.** This is a terminal tool. No FastAPI, no Flask, no HTTP endpoints.
- **Seed the knowledge tables.** On first run, the `commands` and `intent_patterns` tables should be populated from the command catalog in `COMMANDS.md`. Structure the seed data as proper INSERT statements.
- **Log everything to command_history.** Every interaction, which tier handled it, whether it succeeded, how long it took, how many tokens (if LLM).
- **Portuguese for data fields** (titulo, descricao, prioridade) — matching the DB schema. **English for code** (function names, variables, comments).
- **Rich terminal output.** Use the `rich` library for tables, panels, colored text. The CLI should look good.
- **Handle missing credentials gracefully.** No Gmail key? Email agent says so and skips.
- **Architecture for future SaaS.** Agent logic decoupled from CLI. Tools decoupled from agents. Tomorrow these could run behind an API.
- **Save MASTER-PROMPT.md** — copy this entire prompt into the project root.

## What success looks like

After Phase 2, routine operations work instantly with no LLM:
```
$ python main.py
Daily Life v0.1 — type 'help' for commands

> list tasks
┌─────────────────────────────┬───────────┬────────────┬───────────┐
│ Titulo                      │ Prioridade│ Vencimento │ Status    │
├─────────────────────────────┼───────────┼────────────┼───────────┤
│ Review quarterly report     │ alta      │ 2026-04-20 │ pendente  │
│ Fix login bug               │ media     │ 2026-04-16 │ pendente  │
└─────────────────────────────┴───────────┴────────────┴───────────┘
[direct] 2 tasks found — 12ms

> add task prepare slides for demo, high priority, due thursday
Created: "prepare slides for demo" (alta, vencimento: 2026-04-17)
[pattern] parsed from natural language — 8ms

> today
━━━ Daily Briefing — Monday, April 14 ━━━
  Tasks: 3 pending (1 high priority, 1 due today)
  Events: Team standup 09:00, Client call 14:30
  Habits: Gym (pending), Reading (pending), Meditation (done)
[direct] compiled from 3 sources — 45ms
```

After Phase 4, complex requests use AI reasoning:
```
> I have too many tasks this week, help me reprioritize
[llm] Analyzing 12 tasks across 5 days...

Based on your deadlines and priorities, here's my recommendation:
  DROP: "reorganize shared drive" — no deadline, low impact
  DEFER: "update documentation" — move to next week
  FOCUS: "client demo prep" — Thursday deadline, high visibility
  KEEP: remaining 9 tasks are on track

Want me to apply these changes? (y/n)
[llm] 847 tokens — 2.3s
```

## Companion document

See `COMMANDS.md` (created alongside this file) for the full command catalog with triggers, expected behaviors, categories, and example inputs. That document defines the initial seed data for the `commands` and `intent_patterns` tables.

Start building now. Phase 1 first.
