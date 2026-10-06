// Pure functions over what the platform answered: formatting and matching
// only, no platform state of their own. Unit-tested in derive.test.ts.
import type { HarnessStatus } from '../types'

/** The status line: where this session writes, and what the platform owes. */
export function statusLine(fast: HarnessStatus, full: HarnessStatus | null): string {
  const s = fast.session
  const parts: string[] = []
  if (s.tree === 'worktree') {
    parts.push(`⎇ ${s.branch ?? '?'} · wt:${s.worktree_slug ?? '?'}`)
  } else if (s.tree === 'primary' && s.is_shared_branch) {
    parts.push(`⎇ primary@${s.branch ?? '?'} (reads only — branch before writing)`)
  } else {
    parts.push(`⎇ ${s.tree}@${s.branch ?? 'detached'}`)
  }
  if (s.dirty > 0) parts.push(`✎${s.dirty}`)
  const d = fast.dev
  if (d.local_ahead > 0 || d.local_behind > 0) parts.push(`dev ↑${d.local_ahead}↓${d.local_behind} vs origin`)
  if (d.dev_ahead_of_main > 0) parts.push(`main+${d.dev_ahead_of_main}`)
  if (full?.caches && full.caches.stale.length > 0) parts.push(`caches ${full.caches.stale.length}/${full.caches.total} stale`)
  if (full?.auto_improvement) {
    const ai = full.auto_improvement
    if (ai.open_s1 + ai.open_s2 > 0) parts.push(`s1 ${ai.open_s1}·s2 ${ai.open_s2}`)
  }
  if (full?.dispatcher_pending) parts.push(`inbox ${full.dispatcher_pending}`)
  const errors = fast.errors.length + (full?.errors.length ?? 0)
  if (errors > 0) parts.push(`⚠ ${errors} section error${errors === 1 ? '' : 's'}`)
  return `noc · ${parts.join(' · ')}`
}

const GUARD_MARK = /\[noc-guard:([a-z0-9-]+)\]/

/** Which guard refused, read off the refusal text the guard wrote. */
export function refusingGuard(text: string): string | null {
  const marked = GUARD_MARK.exec(text)
  if (marked) return marked[1] ?? null
  // Guards that predate the `[noc-guard:<name>]` marker open with REFUSED.
  if (/^\s*REFUSED\b/.test(text) || /PreToolUse:[^\n]*\bREFUSED\b/.test(text)) return 'unmarked'
  return null
}

/** A shell command that makes a git commit (not amend-free inspection). */
export function isGitCommit(command: string): boolean {
  return /(^|[;&|(]\s*|\s)git(\s+-C\s+\S+)?(\s+-c\s+\S+)*\s+commit\b/.test(command)
}

export type Topic = { title: string; file: string; keywords: string[] }

const STOP = new Set([
  'what', 'when', 'with', 'your', 'task', 'touches', 'their', 'them', 'they', 'this', 'that',
  'into', 'from', 'over', 'rules', 'state', 'how', 'and', 'the', 'who', 'until', 'told', 'done',
  'always', 'session', 'start', 'open', 'owner', 'want', 'worked', 'decisions', 'cross', 'cutting',
])

function words(text: string): string[] {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9/\- ]+/g, ' ')
    .split(/[\s/]+/)
    .map(w => w.replace(/^-+|-+$/g, ''))
    .filter(w => w.length >= 3 && !STOP.has(w))
}

/** The topic table of MEMORY.md (the router), as matchable topics. */
export function parseTopics(memoryIndex: string): Topic[] {
  const topics: Topic[] = []
  for (const line of memoryIndex.split('\n')) {
    const row = /^\|\s*\[([^\]]+)\]\((MEMORY-[a-z0-9-]+\.md)\)\s*\|\s*\d+\s*\|\s*(.+?)\s*\|\s*$/.exec(line)
    if (!row) continue
    const [, title = '', file = '', when = ''] = row
    if (file === 'MEMORY-reminders.md') continue // the band shows these
    topics.push({ title, file, keywords: [...new Set(words(`${title} ${when}`))] })
  }
  return topics
}

/** Topics a prompt touches: at least two distinct keywords, best first. */
export function matchTopics(prompt: string, topics: Topic[], limit = 2): Topic[] {
  const said = new Set(words(prompt))
  return topics
    .map(t => ({ t, score: t.keywords.filter(k => said.has(k)).length }))
    .filter(x => x.score >= 2)
    .sort((a, b) => b.score - a.score)
    .slice(0, limit)
    .map(x => x.t)
}

/** Claude Code's per-project memory folder for a repository root. */
export function memoryDir(home: string, root: string): string {
  return `${home}/.claude/projects/${root.replace(/[^A-Za-z0-9]/g, '-')}/memory`
}

export const COMPACTION_KEEP =
  'NoctusAI harness: keep verbatim, with their targets — every drift-found / scoped-improvement line, ' +
  'every NOC-REMEDIATE marker added, every gate that refused and why, every decision the user made, ' +
  'every commit SHA and branch/worktree in flight, and every open TODO with its named destination.'

const SIGNATURE = /HARNESS SIGNATURE MATCHED: `([^`]+)`/

/** The harness-failure signature claude-guard-harness-signature.py flagged, if any. */
export function harnessSignature(context: string): string | null {
  return SIGNATURE.exec(context)?.[1] ?? null
}

/** An agent type the agents' own frontmatter marks EXECUTOR (derived, never listed). */
export function isExecutorOffer(description: string): boolean {
  return /\bEXECUTOR\b/.test(description)
}

/** A tool call that starts a task branch (MCP tool or the CLI flag). */
export function isTaskBranchStart(tool: string, input: string): boolean {
  if (/task_branch/.test(tool)) return /"action"\s*:\s*"start"/.test(input)
  return tool === 'Bash' && /--task-branch\s+start\b/.test(input)
}
