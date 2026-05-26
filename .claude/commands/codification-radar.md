---
description: Run the codification radar against the live auto-improvement.ndjson; surface s1/s2 → s3 promotion candidates that are ready for codification.
---

# /codification-radar — surface promotion candidates

You are running the **codification-radar** protocol. The user invoked `/codification-radar $ARGUMENTS`.

The radar is the **sensor** of the methodology-codification-pipeline (s1-emergent → s2-memory → s3-kb → s4-keeper). It reads `project-history/auto-improvement.ndjson`, clusters open entries by cosine similarity, and surfaces "these N entries are about the same surface — they're ready to promote one level."

## Protocol

1. **Cluster live ledger** — call `noctus.dev.codification_radar(threshold=0.75, limit=50)` (MCP). Returns clusters with:
   - `cluster_id`
   - `size` (N entries clustered)
   - `avg_score` (cosine cohesion 0..1)
   - `suggested_status_next` (s2-memory / s3-kb / s4-keeper)
   - `entries` (the actual auto-improvement rows in the cluster)

2. **Read the clusters out loud** — for each, name the surface + the suggested next stage + the size. Example:
   ```
   cluster 4 (size=3, avg_score=0.88): suggested_next=s3-kb
     - [s2-memory] WAL mode on SQLite caches
     - [s2-memory] cache locking under parallel access
     - [s1-emergent] sqlite-vec rollback-journal lock blocks readers
     → CANDIDATE FOR S3-KB PROMOTION (pattern doc on cache-locking discipline)
   ```

3. **Combine with `/codify`** — the radar is the auto-detect half; `/codify <surface>` is the decide-and-apply half. Workflow:
   ```
   /codification-radar     # surfaces N=3+ clusters
   /codify <surface>       # evaluate + promote
   ```

4. **If `--promote <cluster_id> <status>` arg** — call `noctus.dev.auto_improvement_promote(matches, target_status)` to atomically update the ledger. Idempotent.

## When to use

- Start of session — see what's clustering toward promotion.
- After a feature ships — surface "this pattern appeared 3+ times this session, codify it."
- Mid-session decision: "is this rule recurrence-3? check the radar."
- Before authoring a new KB pattern doc — does the radar already show the same surface clustering? If yes, that's the evidence.

## Composes with

- `KB § CONTEXT/PATTERNS/common/methodology-codification-pipeline.md` (the 4-stage path)
- `KB § CONTEXT/PATTERNS/common/scoped-auto-improvement.md` (the ledger this reads)
- `KB § CONTEXT/PATTERNS/common/kb-recurrence-radar.md` (sister tool — semantic consult before editing)
- `/codify` (the decide-and-apply half)
- `/baselines` (ratified findings, complementary view)
