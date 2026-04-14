# Daily Life — Command Catalog

> This document defines the initial seed data for the `commands` and `intent_patterns` tables.
> The other agent should parse this into INSERT statements during Phase 2.

---

## Command format

Each command has:
- **Trigger**: what the user types (exact match or pattern)
- **Type**: `exact` (literal match), `pattern` (regex/keyword), `alias` (shortcut to another command)
- **Handler**: Python function to call
- **Category**: grouping for help/organization
- **Examples**: natural language variations the pattern should catch

---

## Tasks

### Direct commands (exact)

| Trigger | Handler | Description |
|---------|---------|-------------|
| `list tasks` | `tasks_cmd.list_all` | Show all pending tasks |
| `list all tasks` | `tasks_cmd.list_all_statuses` | Show tasks including completed/canceled |
| `tasks today` | `tasks_cmd.due_today` | Tasks due today |
| `tasks overdue` | `tasks_cmd.overdue` | Tasks past their due date |
| `tasks high` | `tasks_cmd.by_priority("alta")` | High priority tasks only |
| `task stats` | `tasks_cmd.stats` | Task count by status |

### Pattern commands

| Pattern | Handler | Parameter extraction | Examples |
|---------|---------|---------------------|----------|
| `add task {title}` | `tasks_cmd.create` | title from remainder | "add task review PR" |
| `add task {title}, {priority} priority` | `tasks_cmd.create` | title, priority | "add task fix bug, high priority" |
| `add task {title} by {date}` | `tasks_cmd.create` | title, data_vencimento | "add task send report by friday" |
| `add task {title} by {date}, {priority}` | `tasks_cmd.create` | title, date, priority | "add task demo prep by thursday, high" |
| `add task {title} [{category}]` | `tasks_cmd.create` | title, categoria | "add task review PR [work]" |
| `complete task {id_or_title}` | `tasks_cmd.complete` | task identifier | "complete task 3", "complete task review PR" |
| `delete task {id_or_title}` | `tasks_cmd.delete` | task identifier | "delete task 5" |
| `start task {id_or_title}` | `tasks_cmd.start` | sets status=em_progresso | "start task demo prep" |
| `cancel task {id_or_title}` | `tasks_cmd.cancel` | sets status=cancelada | "cancel task old report" |

### Aliases

| Trigger | Maps to |
|---------|---------|
| `lt` | `list tasks` |
| `at` | `add task` |
| `ct` | `complete task` |
| `dt` | `delete task` |

---

## Goals & Habits

### Direct commands

| Trigger | Handler | Description |
|---------|---------|-------------|
| `list goals` | `habits_cmd.list_goals` | Show active goals |
| `list habits` | `habits_cmd.list_habits` | Show active habits |
| `habit streaks` | `habits_cmd.streaks` | Show current streaks for all habits |
| `habits today` | `habits_cmd.today_status` | Which habits are done/pending today |

### Pattern commands

| Pattern | Handler | Parameter extraction | Examples |
|---------|---------|---------------------|----------|
| `add goal {title}` | `habits_cmd.create_goal` | title | "add goal run a marathon" |
| `add goal {title} by {date}` | `habits_cmd.create_goal` | title, data_limite | "add goal lose 5kg by june" |
| `add habit {title}` | `habits_cmd.create_habit` | title, frequencia=diario | "add habit meditate" |
| `add habit {title} {frequency}` | `habits_cmd.create_habit` | title, frequencia | "add habit gym weekly" |
| `check in {habit_name}` | `habits_cmd.checkin` | habit identifier | "check in gym", "check in reading" |
| `done with {habit_name}` | `habits_cmd.checkin` | habit identifier | "done with meditation" |
| `complete goal {id_or_title}` | `habits_cmd.complete_goal` | goal identifier | "complete goal marathon" |

### Aliases

| Trigger | Maps to |
|---------|---------|
| `lh` | `list habits` |
| `lg` | `list goals` |
| `ci` | `check in` |

---

## Schedule / Calendar

### Direct commands

| Trigger | Handler | Description |
|---------|---------|-------------|
| `show today` | `schedule_cmd.today` | Today's events |
| `show tomorrow` | `schedule_cmd.tomorrow` | Tomorrow's events |
| `show week` | `schedule_cmd.this_week` | This week's events |
| `show next week` | `schedule_cmd.next_week` | Next week's events |
| `list events` | `schedule_cmd.list_all` | All upcoming events |

### Pattern commands

| Pattern | Handler | Parameter extraction | Examples |
|---------|---------|---------------------|----------|
| `schedule {title} {date} at {time}` | `schedule_cmd.create` | title, date, time | "schedule dentist friday at 3pm" |
| `schedule {title} tomorrow at {time}` | `schedule_cmd.create` | title, date=tomorrow, time | "schedule call tomorrow at 10am" |
| `schedule {title} {date}` | `schedule_cmd.create` | title, date (all-day) | "schedule vacation monday" |
| `cancel event {id_or_title}` | `schedule_cmd.cancel` | event identifier | "cancel event dentist" |
| `move event {id_or_title} to {date}` | `schedule_cmd.reschedule` | event identifier, new date | "move dentist to next monday" |

### Aliases

| Trigger | Maps to |
|---------|---------|
| `today` | `show today` |
| `tomorrow` | `show tomorrow` |
| `week` | `show week` |
| `cal` | `list events` |

---

## Notes

### Direct commands

| Trigger | Handler | Description |
|---------|---------|-------------|
| `list notes` | `notes_cmd.list_recent` | Show recent notes |
| `pinned notes` | `notes_cmd.list_pinned` | Show pinned notes |

### Pattern commands

| Pattern | Handler | Parameter extraction | Examples |
|---------|---------|---------------------|----------|
| `note {title}: {content}` | `notes_cmd.create` | title, content | "note meeting: discussed Q3 roadmap" |
| `note {content}` | `notes_cmd.quick_create` | auto-title from content | "note remember to call dentist" |
| `search notes {query}` | `notes_cmd.search` | search term | "search notes roadmap" |
| `pin note {id_or_title}` | `notes_cmd.pin` | note identifier | "pin note meeting" |
| `delete note {id_or_title}` | `notes_cmd.delete` | note identifier | "delete note 3" |

### Aliases

| Trigger | Maps to |
|---------|---------|
| `ln` | `list notes` |
| `n` | `note` |

---

## Briefings

### Direct commands

| Trigger | Handler | Description |
|---------|---------|-------------|
| `briefing` | `briefing_cmd.daily` | Full daily briefing (tasks + events + habits) |
| `daily` | `briefing_cmd.daily` | Same as briefing |
| `weekly` | `briefing_cmd.weekly` | Weekly summary with metrics |
| `score` | `briefing_cmd.productivity_score` | Today's productivity score |
| `stats` | `briefing_cmd.all_stats` | Full productivity metrics |

---

## Email (requires API key)

### Pattern commands (Tier 2 for simple, Tier 3 for drafting)

| Pattern | Handler | Tier | Examples |
|---------|---------|------|----------|
| `send email to {contact} about {subject}` | `email_agent.compose_and_send` | 3 (LLM) | "send email to john about tomorrow's meeting" |
| `draft email to {contact} about {subject}` | `email_agent.draft` | 3 (LLM) | "draft email to team about Q3 results" |
| `send meeting invite to {contact} {date} {time}` | `email_agent.meeting_invite` | 2/3 | "send meeting invite to john friday 2pm" |

---

## WhatsApp (requires WAHA/Twilio)

### Pattern commands

| Pattern | Handler | Tier | Examples |
|---------|---------|------|----------|
| `whatsapp {contact}: {message}` | `message_agent.send_whatsapp` | 2 | "whatsapp john: running 10 min late" |
| `message {contact}: {message}` | `message_agent.send_whatsapp` | 2 | "message maria: can we reschedule?" |

---

## System / Meta

### Direct commands

| Trigger | Handler | Description |
|---------|---------|-------------|
| `help` | `system_cmd.help` | Show all available commands |
| `help {category}` | `system_cmd.help_category` | Show commands in a category |
| `history` | `system_cmd.recent_history` | Last 20 commands |
| `history stats` | `system_cmd.history_stats` | Command usage analytics |
| `version` | `system_cmd.version` | System version |
| `config` | `system_cmd.show_config` | Show current configuration |
| `integrations` | `system_cmd.integration_status` | Which APIs are connected |
| `clear` | `system_cmd.clear_screen` | Clear terminal |
| `exit` | `system_cmd.exit` | Exit the CLI |
| `quit` | `system_cmd.exit` | Same as exit |

---

## Context rules (seed data)

These go into the `context_rules` table. The user should customize after initial setup.

| Rule type | Key | Value | Description |
|-----------|-----|-------|-------------|
| `default` | `priority` | `"media"` | Default task priority |
| `default` | `habit_frequency` | `"diario"` | Default habit frequency |
| `default` | `event_duration` | `60` | Default event duration in minutes |
| `default` | `reminder_minutes` | `30` | Default event reminder |
| `preference` | `date_format` | `"pt-BR"` | Date display format |
| `preference` | `week_start` | `"monday"` | First day of week |
| `preference` | `briefing_time` | `"08:00"` | When daily briefing auto-generates |

---

## AI-only commands (always Tier 3 / LLM)

These have no direct handler — they always go to agno agents:

| Intent | Agent | Description |
|--------|-------|-------------|
| "what should I prioritize today?" | task_agent | Analyzes deadlines, priorities, workload |
| "help me reorganize my tasks" | task_agent | Suggests reordering, dropping, deferring |
| "summarize my week" | briefing_agent | Narrative weekly review with insights |
| "am I on track with my goals?" | habit_agent | Progress analysis with recommendations |
| "find a time for a 1-hour meeting this week" | calendar_agent | Scans schedule for open slots |
| "draft an email to {person} about {topic}" | email_agent | Composes email with context |
| "what patterns do you see in my productivity?" | briefing_agent | Analyzes metrics over time |

---

## Date parsing rules

The pattern parser should understand these date formats:

| Input | Resolves to |
|-------|-------------|
| `today` | current date |
| `tomorrow` | current date + 1 |
| `monday`, `tuesday`, etc. | next occurrence of that weekday |
| `next monday` | next week's monday |
| `friday` | this week's friday (or next if already passed) |
| `april 20` | 2026-04-20 |
| `20/04` | 2026-04-20 (pt-BR format) |
| `in 3 days` | current date + 3 |
| `next week` | next monday |
| `end of month` | last day of current month |

## Priority parsing rules

| Input | Resolves to |
|-------|-------------|
| `high`, `alta`, `urgent`, `!` | alta |
| `medium`, `media`, `normal` | media |
| `low`, `baixa`, `minor` | baixa |
