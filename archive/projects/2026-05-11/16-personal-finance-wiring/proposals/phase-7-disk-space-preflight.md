# Phase 7 proposal — Disk-space pre-flight in `scripts/bootstrap-worktree.sh`

**Severity**: low | **Effort**: small (~30 min)
**Affected products**: cross-cutting (every worktree-using engineer)

## Slip surfaced

Phase 7 hit "No space left on device" mid-verification: pytest collection
errors masked as 19 import errors in seed/lib, vite build truncated, MCP
output file 0 bytes. Root cause: `~/.npm` cache at 6.8 GB + `~/Library/
Caches/Google` at 8.9 GB had pushed `/` to 124 MiB free. `npm cache clean
--force` recovered 7+ GiB instantly.

The slip wasted ≈ 5 min of engineer time and caused two passes through
the test matrix. Trivially avoidable with a pre-flight check.

## Proposal

Extend `scripts/bootstrap-worktree.sh` with a leading disk-space probe:

```bash
# Disk-space pre-flight (Phase 7 PF lesson 2026-05-11).
# Engineers' typical worktree-bootstrap consumes 2-3 GiB across
# product + seed/framework + seed/lib node_modules + pip venv + uv cache.
# Refuse to bootstrap below 5 GiB free; warn at 10 GiB.
_AVAIL_KB=$(df -k / | awk 'NR==2 {print $4}')
_AVAIL_GIB=$((_AVAIL_KB / 1024 / 1024))
if [ "${_AVAIL_GIB}" -lt 5 ]; then
  echo "ERROR: only ${_AVAIL_GIB} GiB free on / — bootstrap needs ≥ 5 GiB."
  echo "  Try: npm cache clean --force  (typically frees 5-10 GiB)"
  echo "  Then: bash scripts/bootstrap-worktree.sh"
  exit 1
elif [ "${_AVAIL_GIB}" -lt 10 ]; then
  echo "WARN: ${_AVAIL_GIB} GiB free on / — consider freeing space"
  echo "  before running long test suites (~/.npm + Library/Caches)."
fi
```

## Verification

After the patch lands:
- Bootstrap on a healthy machine still no-ops (passes through silently).
- Bootstrap on a < 5 GiB machine prints the recovery recipe + exits 1.
- A keeper-side test could pin the recovery-recipe text but is likely
  over-engineering for a one-line shell guard.

## Triage outcome

Accept-with-rationale at N=1 (Phase 7 PF only). Promote to formalize at
N=2 (next engineer hits the same slip in any other product worktree).

Filed at Phase 7 close 2026-05-11. Engineer FFF, worktree
`worktree-agent-ab5bb6977d27f6901`.
