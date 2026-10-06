export type HarnessSession = {
  cwd: string
  tree: 'primary' | 'worktree' | 'outside'
  worktree_slug: string | null
  branch: string | null
  is_shared_branch: boolean
  dirty: number
}

export type HarnessPointer = {
  branch: string
  agent: string
  role: string
  status: string
  brief: string
  worktree: string
  paths: string[]
  updated_at: string
}

export type HarnessWorktree = {
  slug: string
  path: string
  branch: string
  head: string
  dirty: number
  ahead_of_dev: number
}

/** `noc.harness_status/v1` — the JSON `cli.py --harness-status` prints. */
export type HarnessStatus = {
  schema: string
  generated_at: string
  mode: 'fast' | 'full'
  repo_root: string
  session: HarnessSession
  dev: { local_ahead: number; local_behind: number; dev_ahead_of_main: number }
  reminders: { title: string; file: string }[]
  caches: { stale: string[]; total: number } | null
  auto_improvement: {
    open_s1: number
    open_s2: number
    top: { target: string; stage: string; summary: string }[]
  } | null
  branch_pointers: HarnessPointer[] | null
  worktrees: HarnessWorktree[] | null
  dispatcher_pending: number | null
  errors: { section: string; error: string }[]
}

export type Refusal = { at: string; tool: string; guard: string; reason: string }

export type WrapUp = { commits: number; at: string }

export type PanelRow = { label: string; value: string; tone: 'ok' | 'warn' | 'bad' | 'info' }

/** `noc.harness_panel/v1` — what `cli.py --harness-panel <name>` prints. */
export type Panel = {
  schema: string
  panel: string
  generated_at: string
  title: string
  sections: { heading: string; rows: PanelRow[] }[]
  errors: { section: string; error: string }[]
}

/** `noc.harness_route/v1` — what `cli.py --harness-route` prints. */
export type Route = {
  schema: string
  topics: { file: string; title: string; score: number; via: string }[]
  errors: { section: string; error: string }[]
}

declare module 'claude-code' {
  interface PluginState {
    'noc-harness': {
      fast: HarnessStatus | null
      full: HarnessStatus | null
      degraded: string | null
      refusals: Refusal[]
      wrapup: WrapUp | null
      bandHidden: boolean
      bandExpanded: boolean
      claimed: string | null
      panels: Record<string, Panel | string>
    }
  }
}
