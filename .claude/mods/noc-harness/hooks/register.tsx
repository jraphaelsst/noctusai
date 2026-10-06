// noc-harness — the NoctusAI harness mod. A UX + reliability layer over the
// canonical Python gates (KB § PATTERNS/common/harness-mods.md): it renders
// what `cli.py --harness-*` answers and records friction; it never decides a
// gate. Every feature has a userConfig kill switch; NOC_HARNESS_OFF=1 stops all.
import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { HarnessStatus, Refusal } from '../types'
import {
  COMPACTION_KEEP,
  isGitCommit,
  matchTopics,
  memoryDir,
  parseTopics,
  refusingGuard,
  statusLine,
} from './derive'
import type { Topic } from './derive'

const fast = atom({ plugin: 'noc-harness', key: 'fast' } as const, null)
const full = atom({ plugin: 'noc-harness', key: 'full' } as const, null)
const degraded = atom({ plugin: 'noc-harness', key: 'degraded' } as const, null)
const refusals = atom({ plugin: 'noc-harness', key: 'refusals' } as const, [])
const wrapup = atom({ plugin: 'noc-harness', key: 'wrapup' } as const, null)
const bandHidden = atom({ plugin: 'noc-harness', key: 'bandHidden' } as const, false)

// The ONE bridge to the platform: `cli.py --harness-*`, fronting the
// noctus.dev.harness_status / harness_event tools. The mod renders what they
// answer; it never re-derives platform state.
const WORKTREE_MARK = '/.claude/worktrees/'

/** The primary checkout, also when the session runs inside a worktree. */
async function primaryRoot($: EngineInterface): Promise<string> {
  const root = await $.session.root()
  const at = root.indexOf(WORKTREE_MARK)
  return at >= 0 ? root.slice(0, at) : root
}

type Outcome<T> = { ok: true; value: T } | { ok: false; error: string }

function failure(what: string, exitCode: number, stderr: string, stdout: string): string {
  const tail = (stderr || stdout).trim().split('\n').slice(-1)[0] ?? ''
  return `${what} exited ${exitCode}${tail ? `: ${tail.slice(0, 160)}` : ''}`
}

async function harnessStatus(
  $: EngineInterface,
  full: boolean,
): Promise<Outcome<HarnessStatus>> {
  const root = await primaryRoot($)
  const cwd = await $.session.cwd()
  try {
    const ran = full
      ? await $.process.run(
          ['python3', `${root}/mcp/noctusai/cli.py`, '--harness-status', '--hs-full', '--hs-cwd', cwd],
          { cwd: root, timeoutMs: 30000 },
        )
      : await $.process.run(
          ['python3', `${root}/mcp/noctusai/cli.py`, '--harness-status', '--hs-cwd', cwd],
          { cwd: root, timeoutMs: 8000 },
        )
    if (ran.exitCode !== 0) {
      return { ok: false, error: failure('harness-status', ran.exitCode, ran.stderr, ran.stdout) }
    }
    const parsed = JSON.parse(ran.stdout) as HarnessStatus
    if (parsed.schema !== 'noc.harness_status/v1') {
      return { ok: false, error: `harness-status answered schema ${String(parsed.schema)}` }
    }
    return { ok: true, value: parsed }
  } catch (err) {
    return { ok: false, error: `harness-status: ${err instanceof Error ? err.message : String(err)}` }
  }
}

type HarnessEvent = {
  kind: 'gate_denied' | 'gate_timeout' | 'guard_error' | 'harness_invalid' | 'compaction_capture' | 'note'
  target: string
  summary: string
  detail?: string
  session_id?: string
}

async function harnessEvent($: EngineInterface, event: HarnessEvent): Promise<Outcome<string>> {
  const root = await primaryRoot($)
  const stdin = JSON.stringify({ ...event, source: 'noc-harness-mod' })
  try {
    const ran = await $.process.run(
      ['python3', `${root}/mcp/noctusai/cli.py`, '--harness-event'],
      { cwd: root, stdin, timeoutMs: 15000 },
    )
    if (ran.exitCode !== 0) {
      return { ok: false, error: failure('harness-event', ran.exitCode, ran.stderr, ran.stdout) }
    }
    return { ok: true, value: ran.stdout.trim() }
  } catch (err) {
    return { ok: false, error: `harness-event: ${err instanceof Error ? err.message : String(err)}` }
  }
}

const PANE = 'noc-orchestration'
const HAIKU = 'claude-haiku-4-5-20251001'

type Options = Readonly<Record<string, string | number | boolean | readonly string[]>>

// Module state: a reload runs `register` again, which resets it.
let options: Options = {}
let isOff = false
let commitsThisTurn = 0
let wrapUpRan = false
let topics: Topic[] | null = null
const routed = new Set<string>()

function enabled(key: string): boolean {
  return options[key] !== false
}

// Nothing here fails silently: a failure lands in `degraded`, which the
// status line, the band and the pane all show.
async function noteDegraded($: EngineInterface, why: string | null): Promise<void> {
  await update($, degraded, () => why)
}

async function paintStatus($: EngineInterface): Promise<void> {
  if (!enabled('status_line')) return $.ui.status(undefined)
  const why = await read($, degraded)
  const snap = await read($, fast)
  if (snap === null) return $.ui.status(why ? `noc · degraded — ${why}` : 'noc · …')
  const line = statusLine(snap, await read($, full))
  $.ui.status(why ? `${line} · degraded — ${why}` : line)
}

async function refreshFast($: EngineInterface): Promise<void> {
  const got = await harnessStatus($, false)
  if (got.ok) {
    await update($, fast, () => got.value)
    await noteDegraded($, null)
  } else {
    await noteDegraded($, got.error)
  }
  await paintStatus($)
}

async function refreshFull($: EngineInterface): Promise<void> {
  const got = await harnessStatus($, true)
  if (got.ok) {
    await update($, full, () => got.value)
    await update($, fast, () => got.value)
  } else {
    await noteDegraded($, got.error)
  }
  await paintStatus($)
}

async function record($: EngineInterface, event: HarnessEvent): Promise<void> {
  const done = await harnessEvent($, event)
  if (!done.ok) await noteDegraded($, done.error)
}

export const register: Register = (on, given) => {
  options = given
  isOff = false
  commitsThisTurn = 0
  wrapUpRan = false
  topics = null
  routed.clear()
  const refreshMs = Math.max(15, Number(options.full_refresh_seconds ?? 60)) * 1000

  on('session.start', async ($, e, next) => {
    isOff = (await $.env.get('NOC_HARNESS_OFF')) === '1'
    if (isOff) {
      $.ui.status('noc · harness mod off (NOC_HARNESS_OFF=1)')
      return next(e)
    }
    if (enabled('orchestration_pane')) {
      await $.command.register({ name: 'noc-pane', description: 'NoctusAI orchestration pane: worktrees, branch pointers, inbox, open s1/s2, refusals' })
    }
    if (enabled('reminders_band')) {
      await $.command.register({ name: 'noc-band', description: 'Show the NoctusAI reminders band again' })
    }
    await $.command.register({ name: 'noc-refresh', description: 'Refresh the NoctusAI harness snapshot now' })
    void refreshFast($)
    void refreshFull($)
    $.clock.every(refreshMs, () => void refreshFull($))
    return next(e)
  })

  on('command.run', { command: 'noc-pane' }, async $ => {
    await $.ui.open({ id: PANE, title: 'NoctusAI · orchestration', focus: true })
    void refreshFull($)
    return { text: 'Orchestration pane opened.' }
  })

  on('command.run', { command: 'noc-band' }, async $ => {
    await update($, bandHidden, () => false)
    return { text: 'Reminders band shown.' }
  })

  on('command.run', { command: 'noc-refresh' }, async $ => {
    await refreshFull($)
    const why = await read($, degraded)
    return { text: why ? `Refreshed, degraded: ${why}` : 'Harness snapshot refreshed.' }
  })

  on('turn.start', ($, e, next) => {
    commitsThisTurn = 0
    wrapUpRan = false
    return next(e)
  })

  // Friction ledger + wrap-up bookkeeping. Observes; never decides.
  on('tool.call', async ($, e, next) => {
    const ran = await next(e)
    if (isOff) return ran
    if (e.agentId === undefined && e.tool === 'Bash' && ran.isError !== true && isGitCommit(e.command)) {
      commitsThisTurn += 1
    }
    if (e.agentId === undefined && String(e.tool) === 'Skill' && JSON.stringify(e).includes('noc-wrap-up')) {
      wrapUpRan = true
    }
    const text = ran.deny ?? (ran.isError === true ? ran.text ?? '' : '')
    const guard = text ? refusingGuard(text) : null
    if (guard !== null && enabled('friction_ledger')) {
      const refusal: Refusal = {
        at: new Date(await $.clock.now()).toISOString(),
        tool: String(e.tool),
        guard,
        reason: text.replace(/\[noc-guard:[a-z0-9-]+\]\s*/, '').split('\n')[0]?.slice(0, 200) ?? '',
      }
      await update($, refusals, list => [...list, refusal].slice(-50))
      $.ui.toast(`noc-guard:${guard} refused ${refusal.tool} — logged as a learning event`)
      void record($, {
        kind: 'gate_denied',
        target: `guard:${guard}`,
        summary: `${refusal.tool} refused${e.agentId ? ` (agent ${e.agentId})` : ''}: ${refusal.reason}`,
        session_id: await $.session.id(),
      })
    }
    return ran
  }).catch(($, e, next) => next(e))

  on('turn.complete', async ($, e, next) => {
    const done = await next(e)
    if (isOff) return done
    if (enabled('wrapup_nudge') && e.agentId === undefined && commitsThisTurn > 0 && !wrapUpRan) {
      const commits = commitsThisTurn
      await update($, wrapup, () => ({ commits, at: new Date().toISOString() }))
      $.ui.toast(`${commits} commit${commits === 1 ? '' : 's'} this turn — wrap-up check offered above the prompt`)
    }
    void refreshFast($)
    return done
  })

  // Memory-topic routing: point at the MEMORY-<topic>.md the prompt touches,
  // derived from the MEMORY.md topic table — never a hand-kept keyword list.
  on('prompt.submit', async ($, e, next) => {
    if (isOff || !enabled('memory_routing') || (e.origin.kind !== 'composer' && e.origin.kind !== 'bridge')) return next(e)
    const home = (await $.env.get('HOME')) ?? ''
    const dir = memoryDir(home, await primaryRoot($))
    if (topics === null) {
      try {
        topics = parseTopics(await $.fs.read(`${dir}/MEMORY.md`))
      } catch (err) {
        topics = []
        await noteDegraded($, `memory routing: ${err instanceof Error ? err.message : String(err)}`)
      }
    }
    const hits = matchTopics(e.text, topics).filter(t => !routed.has(t.file))
    if (hits.length === 0) return next(e)
    hits.forEach(t => routed.add(t.file))
    const pointer =
      'noc-harness memory routing: this prompt touches ' +
      hits.map(t => `"${t.title}" → ${dir}/${t.file}`).join(' and ') +
      '. Per MEMORY.md, topic files are not auto-loaded — open the matching one before acting on the task.'
    return next({ ...e, context: [...(e.context ?? []), pointer] })
  }).catch(($, e, next) => next(e))

  // Compaction: tell the summarizer what the methodology cannot lose, and
  // record the learnings in flight as s1 events before they are summarized.
  on('session.compact', async ($, e, next) => {
    if (isOff || !enabled('compaction_capture') || e.agentId !== undefined) return next(e)
    const transcript = e.messages
      .slice(-80)
      .map(m => `${m.role}: ${m.text}`)
      .join('\n')
      .slice(-40000)
    const asked = await $.model.complete({
      model: HAIKU,
      maxTokens: 1200,
      system:
        'You extract engineering learnings from a coding-session transcript. Answer ONLY a JSON array (max 5) of ' +
        '{"target": "<file, gate, tool or pattern it is about>", "summary": "<one sentence>"} for drift found, ' +
        'gates that refused, workarounds needed, or improvements proposed but not yet recorded. [] when none.',
      prompt: transcript,
    })
    if (asked.isAnswered) {
      try {
        const found = JSON.parse(asked.text.replace(/^[^[]*/, '').replace(/[^\]]*$/, '')) as { target: string; summary: string }[]
        const sessionId = await $.session.id()
        for (const one of found.slice(0, 5)) {
          await record($, { kind: 'compaction_capture', target: one.target, summary: one.summary, session_id: sessionId })
        }
      } catch (err) {
        await noteDegraded($, `compaction capture: unreadable answer (${err instanceof Error ? err.message : String(err)})`)
      }
    } else {
      await noteDegraded($, `compaction capture: model unanswered (${asked.reason})`)
    }
    const instructions = e.instructions ? `${e.instructions}\n\n${COMPACTION_KEEP}` : COMPACTION_KEEP
    return next({ ...e, instructions })
  }).catch(($, e, next) => (next.called ? next(e) : next(e)))

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (isOff || !enabled('reminders_band') || e.props.hasSurvey || (await read($, bandHidden))) return next(e)
    const snap = await read($, fast)
    const pending = await read($, wrapup)
    const why = await read($, degraded)
    const reminders = snap?.reminders ?? []
    if (reminders.length === 0 && pending === null && why === null) return next(e)
    const { Box, Button, Text } = $.ui.resolve(e)
    const room = Math.max(1, e.props.maxRows - (pending ? 2 : 1))
    return (
      <Box flexDirection="column">
        {reminders.slice(0, room).map(r => (
          <Text key={r.file} color="yellow" wrap="truncate-end">
            🔔 {r.title}
          </Text>
        ))}
        {why !== null && (
          <Text key="degraded" color="red" wrap="truncate-end">
            noc-harness degraded — {why}
          </Text>
        )}
        <Box key="actions" flexDirection="row">
          {pending !== null && (
            <Button
              key="wrapup"
              variant="primary"
              hotkey="w"
              label={`Run wrap-up (${pending.commits} commit${pending.commits === 1 ? '' : 's'})`}
              onPress={async () => {
                await update($, wrapup, () => null)
                await $.prompt.submit({ text: 'wrap up — run the noc-wrap-up check on what this session just committed' })
              }}
            />
          )}
          {pending !== null && (
            <Button key="skip" label="Skip" onPress={() => update($, wrapup, () => null)} />
          )}
          <Button key="hide" label="Hide" onPress={() => update($, bandHidden, () => true)} />
        </Box>
      </Box>
    )
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Button, Text } = $.ui.resolve(e)
    const snap = await read($, full)
    const why = await read($, degraded)
    const recent = await read($, refusals)
    if (snap === null) {
      return (
        <Box flexDirection="column">
          <Text dimColor>{why ? `Unavailable: ${why}` : 'Loading the harness snapshot…'}</Text>
          <Button key="refresh" label="Refresh" hotkey="r" onPress={() => void refreshFull($)} />
        </Box>
      )
    }
    const s = snap.session
    const pointers = snap.branch_pointers ?? []
    const trees = snap.worktrees ?? []
    const ai = snap.auto_improvement
    return (
      <Box flexDirection="column">
        <Text dimColor wrap="truncate-end">
          snapshot {snap.generated_at.slice(11, 19)} · {s.tree}@{s.branch ?? '?'}
          {s.worktree_slug ? ` (${s.worktree_slug})` : ''} · dev↑{snap.dev.local_ahead}↓{snap.dev.local_behind} · main+{snap.dev.dev_ahead_of_main}
        </Text>
        <Text bold>Branch pointers ({pointers.length} live)</Text>
        {pointers.length === 0 && <Text dimColor>none</Text>}
        {pointers.slice(0, 12).map(p => (
          <Text key={`bp-${p.branch}`} wrap="truncate-end">
            {p.status === 'on_going' ? '●' : '○'} {p.branch} · {p.agent}/{p.role} · {p.brief}
          </Text>
        ))}
        <Text bold>Worktrees ({trees.length})</Text>
        {trees.slice(0, 12).map(w => (
          <Text key={`wt-${w.slug}`} wrap="truncate-end" color={w.dirty > 0 ? 'yellow' : undefined}>
            {w.slug} · {w.branch} · {w.head.slice(0, 9)} · +{w.ahead_of_dev} · {w.dirty} dirty
          </Text>
        ))}
        {trees.length > 12 && <Text dimColor>… {trees.length - 12} more</Text>}
        <Text bold>
          Inbox {snap.dispatcher_pending ?? '?'} · s1 {ai?.open_s1 ?? '?'} · s2 {ai?.open_s2 ?? '?'} · caches{' '}
          {snap.caches ? `${snap.caches.stale.length}/${snap.caches.total} stale` : '?'}
        </Text>
        {(ai?.top ?? []).map(t => (
          <Text key={`ai-${t.target}`} dimColor wrap="truncate-end">
            [{t.stage}] {t.target} — {t.summary}
          </Text>
        ))}
        <Text bold>Refusals this session ({recent.length})</Text>
        {recent.slice(-6).map(r => (
          <Text key={`rf-${r.at}`} color="red" wrap="truncate-end">
            {r.at.slice(11, 19)} {r.guard} · {r.tool} · {r.reason}
          </Text>
        ))}
        {[...snap.errors, ...(why ? [{ section: 'mod', error: why }] : [])].map(x => (
          <Text key={`err-${x.section}`} color="red" wrap="truncate-end">
            ⚠ {x.section}: {x.error}
          </Text>
        ))}
        <Button key="refresh" label="Refresh" hotkey="r" onPress={() => void refreshFull($)} />
      </Box>
    )
  })
}
