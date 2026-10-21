# Frontend server state — family index (§1 consolidation)

> **Family-line pattern:** CLAUDE.md §1 carries ONE line for this family; the member rules live here **verbatim**. This is a lossless MOVE, not a summary — the bytes below are the bytes that were in §1. Each member keeps its own depth doc; this index is the router hop between the §1 family line and those docs. Consolidated 2026-10-21 (adding the cache-writes rule took §1 to 56 against a cap of 55). → `KB § PATTERNS/common/methodology-gc.md`

Both rules answer one question: **does what the screen shows agree with the server right now?** The first governs READS (what to render while data is pending or refetching); the second governs WRITES (what the cache holds between the click and the server's answer). A product that follows one and not the other still shows the user something false.

## Members (verbatim from §1)

- **No lying loading states — two signals, never `isLoading`: `showSkeleton = isPending && !data`, `isRefreshing = isFetching && !!data`.** `isLoading` is false mid-refetch so an empty branch lies over data; a bare `isFetching` gate unmounts content that exists (70 sites, 2026-08-31); key-change queries need `placeholderData`; keeper `check_lying_loading_state` covers the first mode only. → `KB § PATTERNS/frontend/lying-loading-state.md`
- **A write puts what it knows into the cache — never invalidate-only.** Invalidate-only throws away the server's answer: the screen contradicts the toast for write + refetch (orbity note ~2 s, 2026-10-21; 94% of fleet mutations). `useCacheWriteMutation` / `createCrudHooks`; keeper `check_mutation_invalidate_only` (ratchet). → `KB § PATTERNS/frontend/mutation-cache-writes.md` · skill `noc-cache-writes`

## Why a family line

A session writing a TanStack hook needs both: the write contract's background settle is a refetch, and rendering that refetch honestly is the loading-state rule. One router hop returns one always-on line of budget. The forcing function is the router keeper's rule-COUNT ceiling; the procedure is `/gc` step 5. → `KB § PATTERNS/common/claude-md-router-discipline.md`
