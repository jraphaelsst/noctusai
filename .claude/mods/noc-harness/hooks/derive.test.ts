import { expect, test } from 'claude-code/testing'

import type { HarnessStatus } from '../types'
import {
  harnessSignature,
  isExecutorOffer,
  isGitCommit,
  isTaskBranchStart,
  matchTopics,
  memoryDir,
  parseTopics,
  refusingGuard,
  statusLine,
  stripBell,
  taskBranchSlug,
} from './derive'

const snap = (over: Partial<HarnessStatus> = {}): HarnessStatus => ({
  schema: 'noc.harness_status/v1',
  generated_at: '2026-10-06T01:00:00Z',
  mode: 'fast',
  repo_root: '/r',
  session: { cwd: '/r', tree: 'primary', worktree_slug: null, branch: 'dev', is_shared_branch: true, dirty: 0 },
  dev: { local_ahead: 0, local_behind: 0, dev_ahead_of_main: 0 },
  reminders: [],
  caches: null,
  auto_improvement: null,
  branch_pointers: null,
  worktrees: null,
  dispatcher_pending: null,
  errors: [],
  ...over,
})

test('status line warns that the primary on a shared branch is reads-only', async () => {
  expect(statusLine(snap(), null)).toContain('primary@dev (reads only')
})

test('status line names the worktree and what the platform owes', async () => {
  const fast = snap({
    session: { cwd: '/r/.claude/worktrees/x', tree: 'worktree', worktree_slug: 'x', branch: 'feat/x', is_shared_branch: false, dirty: 2 },
    dev: { local_ahead: 0, local_behind: 3, dev_ahead_of_main: 5 },
  })
  const full = snap({
    caches: { stale: ['kb-embeddings'], total: 8 },
    auto_improvement: { open_s1: 4, open_s2: 1, top: [] },
    dispatcher_pending: 2,
    errors: [{ section: 'caches', error: 'boom' }],
  })
  const line = statusLine(fast, full)
  for (const part of ['feat/x · wt:x', '✎2', 'dev ↑0↓3', 'main+5', 'caches 1/8 stale', 's1 4·s2 1', 'inbox 2', '⚠ 1 section error']) {
    expect(line).toContain(part)
  }
})

test('refusals are attributed by marker, legacy REFUSED reads as unmarked', async () => {
  expect(refusingGuard('[noc-guard:primary-write] REFUSED — this would write')).toBe('primary-write')
  expect(refusingGuard('REFUSED — this would write the PRIMARY')).toBe('unmarked')
  expect(refusingGuard('command not found')).toBe(null)
})

test('git commit detection', async () => {
  expect(isGitCommit('git commit -m "x"')).toBe(true)
  expect(isGitCommit('git -C /a/b commit -m x')).toBe(true)
  expect(isGitCommit('cd x && git commit -am y')).toBe(true)
  expect(isGitCommit('git log --oneline')).toBe(false)
  expect(isGitCommit('echo commit')).toBe(false)
})

const INDEX = [
  '| Topic | Memories | Read it when your task touches |',
  '|---|---:|---|',
  '| [🔔 Owner reminders — OPEN](MEMORY-reminders.md) | 2 | **ALWAYS at session start** |',
  '| [WAHA / integrations](MEMORY-integrations.md) | 21 | WhatsApp/WAHA, Meta, Google, phone format, OAuth |',
  '| [Deployment / infra](MEMORY-deployment.md) | 36 | prod shape, VPS fleet, deploy gates, containers, config parity |',
].join('\n')

test('topics derive from the MEMORY.md table, reminders excluded', async () => {
  const topics = parseTopics(INDEX)
  expect(topics.map(t => t.file)).toEqual(['MEMORY-integrations.md', 'MEMORY-deployment.md'])
})

test('a prompt needs two keywords of a topic to be routed', async () => {
  const topics = parseTopics(INDEX)
  expect(matchTopics('the waha whatsapp session keeps dropping', topics).map(t => t.file)).toEqual(['MEMORY-integrations.md'])
  expect(matchTopics('fix the waha typo', topics)).toEqual([])
  expect(matchTopics('deploy the containers to the vps fleet', topics)[0]?.file).toBe('MEMORY-deployment.md')
})

test('memory folder follows the Claude Code project slug', async () => {
  expect(memoryDir('/Users/u', '/Users/u/Documents/NoctusAI/noctusai')).toBe(
    '/Users/u/.claude/projects/-Users-u-Documents-NoctusAI-noctusai/memory',
  )
})

test('harness signature is read off the PostToolUse advisory', async () => {
  expect(harnessSignature('x\nHARNESS SIGNATURE MATCHED: `venv-less-worktree` (exit 1)')).toBe('venv-less-worktree')
  expect(harnessSignature('tests failed: 3')).toBe(null)
})

test('executor agents are recognised by their own EXECUTOR marker', async () => {
  expect(isExecutorOffer('Senior backend engineer — EXECUTOR. Dispatch for server-side slices')).toBe(true)
  expect(isExecutorOffer('Senior solution architect — ADVISOR (read-only).')).toBe(false)
})

test('task-branch starts are seen through the MCP tool and the CLI', async () => {
  expect(isTaskBranchStart('mcp__noctusai__noctus_dev_task_branch', '{"action":"start","slug":"x"}')).toBe(true)
  expect(isTaskBranchStart('mcp__noctusai__noctus_dev_task_branch', '{"action":"cleanup"}')).toBe(false)
  expect(isTaskBranchStart('Bash', 'python3 mcp/noctusai/cli.py --task-branch start --task-branch-slug x')).toBe(true)
})

test('the band draws one bell, not the title bell as well', async () => {
  expect(stripBell('🔔 Contract wording for PJ parties')).toBe('Contract wording for PJ parties')
  expect(stripBell('No bell here')).toBe('No bell here')
})

test('the task-branch slug is read from the MCP input and the CLI flag', async () => {
  expect(taskBranchSlug('{"action":"start","slug":"guard-redirect"}')).toBe('guard-redirect')
  expect(taskBranchSlug('python3 cli.py --task-branch start --task-branch-slug harness-mods --x')).toBe('harness-mods')
  expect(taskBranchSlug('{"action":"start"}')).toBe(null)
})
