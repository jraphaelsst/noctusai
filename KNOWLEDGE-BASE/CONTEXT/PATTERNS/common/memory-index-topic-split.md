# Memory index — router + per-topic files (the DEFAULT memory shape)

> **Rule.** `MEMORY.md` is a ROUTER of TOPICS, never a catalogue of memories. One line per
> **topic**; the topic file carries one line per **memory**; the memory file carries the
> fact. Adding a memory grows a topic file — never the router.

---

## 1 · Why — a flat index has a hard ceiling, and crossing it fails SILENTLY

`MEMORY.md` is auto-loaded into every session. It is also **read-capped**: past roughly
**24.4KB the read returns nothing**. Not truncated-with-a-warning — nothing. An agent in
that state does not know it has memories, so it re-derives facts the team already paid
for, and every "why didn't you remember X?" traces back here.

The flat index hit **24,799 bytes on 2026-07-30** — over the line — with 414 pointers
across 20 sections. The index had carried a `🔴` warning about this for months and had
been trimmed repeatedly. Trimming was never going to work: **the filenames alone
exceeded the target**, so no amount of shortening labels could bring it under. The
ceiling is structural, and only a structural fix clears it.

The split took it to **4.1KB** — bounded by *topic count*, which grows only when the
domain gains a genuinely new area, rather than by *memory count*, which grows every week.

## 2 · The shape

```
memory/
  MEMORY.md                    ← auto-loaded. ROUTER: one row per topic. ~4KB, bounded.
  MEMORY-<topic>.md            ← NOT auto-loaded. One line per memory, `·`-separated.
  <type>_<slug>.md             ← the memory itself: frontmatter + the fact.
```

Three levels, each with exactly one job. This is deliberately the **same shape as
`CLAUDE.md` → `CLAUDE/<topic>.md` → `KB § …`**, for the same reason and with the same
discipline: the always-on surface stays pointer-only, and depth is pulled on demand.
An agent that already knows the router pattern needs no new concept to use this.

## 3 · Procedure

**Recall.** Open the topic file(s) your task touches. They are not auto-loaded — that is
the saving. For "is there anything about X?" when you do not know the topic, reach for
`noctus.dev.memory_search` FIRST: it is semantic, covers all memories, and does not
depend on the index at all.

**Save.** Write the memory file, then append its pointer to the matching
`MEMORY-<topic>.md`. **Never add a pointer to `MEMORY.md`.** If nothing fits, create
`MEMORY-<new-topic>.md` and add exactly ONE row to the router.

**Delete.** Remove the memory file AND its pointer in the same edit, and say so. A
pointer to a deleted file is a dangling read; a file with no pointer is unreachable.

**Split a topic** at roughly >60 pointers or >6KB — the same argument, one level down.

## 4 · Invariants (what a check should assert)

| Invariant | Failure it prevents |
|---|---|
| `MEMORY.md` contains no pointer to a `<type>_<slug>.md` | the router silently becoming a catalogue again |
| Every topic file is linked from `MEMORY.md` exactly once | an orphaned topic nobody reads |
| Every pointer resolves to a file on disk | a dangling read |
| Every memory file is reachable from exactly one topic file | a memory that exists but cannot be found |
| `MEMORY.md` < ~8KB | the ceiling, with headroom |

## 5 · Doing the split (it must be LOSSLESS, and proven so)

Mechanically, not by hand — 400+ pointers is beyond reliable manual editing:

1. Back up the index first.
2. Split on `^## `; each section becomes one topic file, body copied VERBATIM.
3. Generate the router from the section list — never hand-write the rows.
4. **Prove it**: diff the pointer SET before vs after. `LOST` must be empty, `DANGLING`
   must be empty, `UNREACHABLE` must be empty. Assert, do not eyeball.

One trap worth naming: the old header contained the literal example `` `[label](file.md)` ``,
which any link-extracting check reads as a real pointer and reports as dangling. Do not
put link-shaped examples in an index that a checker will parse — describe the format in
prose instead. (Cost 10 minutes on 2026-07-30.)

## 6 · Relation to the other memory rules

This governs the INDEX. What belongs in a memory at all, and the `user` / `feedback` /
`project` / `reference` typing, is unchanged — see the harness memory contract. The two
compose: this pattern only changes WHERE the pointer goes.

> Codified 2026-07-30, from the index crossing its own documented ceiling. Sibling of
> `claude-md-router-discipline.md` (same principle, different always-on surface).
