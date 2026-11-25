# agent-architecture-audit — evaluation scenarios

Desk-checked on 2026-11-25 by skill-scout, not model-run.

| # | Scenario | Expected | Result |
|---|---|---|---|
| 1 | "Agent quotes a price from an old conversation" | Layers 2-4 memory contamination; trace admission path; fix = memory admission priority, not a prompt line | covered |
| 2 | "Prompt says always call the CRM tool; agent sometimes answers without it" | Layer 6/7 tool discipline; gate in code | covered |
| 3 | "Logs show a correct answer but the WhatsApp message is cut/garbled" | Layer 10 transport/rendering; compare generated vs delivered | covered |
| 4 | "Answers changed after a retry wrapper was added" | Layer 11 hidden repair loop; run bare vs wrapped | covered |
| 5 | "Prompt-injection from a lead message" | Out of scope; hand to agent `agents-security` | covered (refuses) |
