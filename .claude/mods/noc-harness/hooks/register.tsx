// noc-harness — the NoctusAI harness mod. A UX + reliability layer over the
// canonical Python gates (KB § PATTERNS/common/harness-mods.md): it renders
// what `cli.py --harness-*` answers and records friction; it never decides a
// gate. Every feature has a userConfig kill switch; NOC_HARNESS_OFF=1 stops all.
import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { HarnessStatus, Panel, Refusal, Route } from '../types'
import {
  COMPACTION_KEEP,
  harnessSignature,
  isExecutorOffer,
  isTaskBranchStart,
  taskBranchSlug,
  isGitCommit,
  matchTopics,
  memoryDir,
  parseTopics,
  refusingGuard,
  statusLine,
  stripBell,
} from './derive'
import type { Topic } from './derive'

const fast = atom({ plugin: 'noc-harness', key: 'fast' } as const, null)
const full = atom({ plugin: 'noc-harness', key: 'full' } as const, null)
const degraded = atom({ plugin: 'noc-harness', key: 'degraded' } as const, null)
const refusals = atom({ plugin: 'noc-harness', key: 'refusals' } as const, [])
const wrapup = atom({ plugin: 'noc-harness', key: 'wrapup' } as const, null)
const bandHidden = atom({ plugin: 'noc-harness', key: 'bandHidden' } as const, false)
const bandExpanded = atom({ plugin: 'noc-harness', key: 'bandExpanded' } as const, false)
const claimed = atom({ plugin: 'noc-harness', key: 'claimed' } as const, null)
const panels = atom({ plugin: 'noc-harness', key: 'panels' } as const, {})

// The live panels: each is `cli.py --harness-panel <name>`, drawn as-is.
const PANELS: Record<string, string> = {
  'noc-vectors': 'vectors',
  'noc-baselines': 'baselines',
  'noc-codify': 'codify',
  'noc-gates': 'gates',
}

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

async function harnessPanel($: EngineInterface, name: string): Promise<Outcome<Panel>> {
  const root = await primaryRoot($)
  try {
    const ran = await $.process.run(
      ['python3', `${root}/mcp/noctusai/cli.py`, '--harness-panel', name],
      { cwd: root, timeoutMs: 60000 },
    )
    if (ran.exitCode !== 0) return { ok: false, error: failure(`harness-panel ${name}`, ran.exitCode, ran.stderr, ran.stdout) }
    const parsed = JSON.parse(ran.stdout) as Panel
    if (parsed.schema !== 'noc.harness_panel/v1') return { ok: false, error: `harness-panel answered schema ${String(parsed.schema)}` }
    return { ok: true, value: parsed }
  } catch (err) {
    return { ok: false, error: `harness-panel ${name}: ${err instanceof Error ? err.message : String(err)}` }
  }
}

async function harnessClaim($: EngineInterface, worktree: string | null): Promise<Outcome<string>> {
  const root = await primaryRoot($)
  const sessionId = await $.session.id()
  const stdin = JSON.stringify(worktree === null ? { session_id: sessionId, release: true } : { session_id: sessionId, worktree })
  try {
    const ran = await $.process.run(
      ['python3', `${root}/mcp/noctusai/cli.py`, '--harness-claim-worktree'],
      { cwd: root, stdin, timeoutMs: 15000 },
    )
    const answer = JSON.parse(ran.stdout || '{}') as { status?: string; error?: string; worktree?: string }
    if (ran.exitCode !== 0 || answer.status === 'error') {
      return { ok: false, error: `harness-claim-worktree: ${answer.error ?? failure('exit', ran.exitCode, ran.stderr, ran.stdout)}` }
    }
    return { ok: true, value: answer.status ?? 'ok' }
  } catch (err) {
    return { ok: false, error: `harness-claim-worktree: ${err instanceof Error ? err.message : String(err)}` }
  }
}

async function harnessRoute($: EngineInterface, prompt: string): Promise<Outcome<Route>> {
  const root = await primaryRoot($)
  try {
    const ran = await $.process.run(
      ['python3', `${root}/mcp/noctusai/cli.py`, '--harness-route'],
      { cwd: root, stdin: JSON.stringify({ prompt }), timeoutMs: 15000 },
    )
    if (ran.exitCode !== 0) return { ok: false, error: failure('harness-route', ran.exitCode, ran.stderr, ran.stdout) }
    const parsed = JSON.parse(ran.stdout) as Route
    if (parsed.schema !== 'noc.harness_route/v1') return { ok: false, error: `harness-route answered schema ${String(parsed.schema)}` }
    return { ok: true, value: parsed }
  } catch (err) {
    return { ok: false, error: `harness-route: ${err instanceof Error ? err.message : String(err)}` }
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
  const claim = await read($, claimed)
  const line = statusLine(snap, await read($, full)) + (claim ? ` · ↪ ${claim}` : '')
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

async function claimWorktree($: EngineInterface, slug: string | null): Promise<string> {
  const root = await primaryRoot($)
  const worktree = slug === null ? null : `${root}/.claude/worktrees/${slug}`
  const done = await harnessClaim($, worktree)
  if (!done.ok) {
    await noteDegraded($, done.error)
    return done.error
  }
  await update($, claimed, () => slug)
  await paintStatus($)
  return slug === null
    ? 'Released the worktree claim: primary-checkout writes are refused again.'
    : `Claimed ${worktree}: this session's Edit/Write into the primary checkout now redirect there (visibly).`
}

async function loadPanel($: EngineInterface, name: string): Promise<void> {
  const got = await harnessPanel($, name)
  await update($, panels, all => ({ ...all, [name]: got.ok ? got.value : got.error }))
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
    await $.command.register({ name: 'noc-claim', description: 'Claim a worktree (<slug>) for the primary-write redirect, or `release`', argumentHint: '<slug> | release' })
    if (enabled('wrapup_nudge')) {
      await $.command.register({ name: 'noc-wrapup', description: 'Run the noc-wrap-up check on what this session committed (clears the band nudge)' })
    }
    if (enabled('code_panels')) {
      await $.command.register({ name: 'noc-vectors', description: 'Live pane: vector platform — caches, freshness, cost (what /vector-status shows)' })
      await $.command.register({ name: 'noc-baselines', description: 'Live pane: kb + code recurrence baselines vs the last ratification' })
      await $.command.register({ name: 'noc-codify', description: 'Live pane: codification radar — s1/s2 ready for promotion' })
      await $.command.register({ name: 'noc-gates', description: 'Live pane: wired guards, a health probe of each, recent refusals' })
    }
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

  on('command.run', { command: 'noc-claim' }, async ($, e) => {
    const arg = e.args.trim()
    if (arg === '') return { text: 'Usage: /noc-claim <worktree-slug> | release' }
    return { text: await claimWorktree($, arg === 'release' ? null : arg) }
  })

  on('command.run', { command: 'noc-wrapup' }, async $ => {
    await update($, wrapup, () => null)
    await $.prompt.submit({ text: 'wrap up — run the noc-wrap-up check on what this session just committed' })
    return { text: 'Wrap-up check queued.' }
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
    if (e.agentId === undefined && isTaskBranchStart(String(e.tool), JSON.stringify(e))) {
      void refreshFull($)
      const slug = taskBranchSlug(JSON.stringify(e))
      if (slug !== null && ran.isError !== true && ran.deny === undefined) {
        $.ui.toast(await claimWorktree($, slug))
      }
    }
    const notes = 'context' in ran && ran.context ? ran.context.join('\n') : ''
    const signature = harnessSignature(notes)
    if (signature !== null && enabled('harness_invalid_alerts')) {
      const invalid: Refusal = {
        at: new Date(await $.clock.now()).toISOString(),
        tool: String(e.tool),
        guard: `harness:${signature}`,
        reason: 'INCONCLUSIVE — this red judges the setup, not the code',
      }
      await update($, refusals, list => [...list, invalid].slice(-50))
      $.ui.toast(`INCONCLUSIVE — harness signature ${signature}: this red judges the setup, not the code`)
      void record($, { kind: 'harness_invalid', target: `harness:${signature}`, summary: `${String(e.tool)} red matched harness signature ${signature}`, session_id: await $.session.id() })
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
    const isPerson = e.origin.kind === 'composer' || e.origin.kind === 'bridge'
    // A nudge belongs to the turn that earned it: moving on dismisses it.
    if (isPerson && (await read($, wrapup)) !== null) await update($, wrapup, () => null)
    if (isOff || !enabled('memory_routing') || !isPerson) return next(e)
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
    let hits: { title: string; file: string }[] = matchTopics(e.text, topics).filter(t => !routed.has(t.file))
    if (hits.length === 0 && enabled('semantic_routing') && e.text.length >= 40) {
      const routedBy = await harnessRoute($, e.text)
      if (routedBy.ok) {
        hits = routedBy.value.topics.slice(0, 2).filter(t => !routed.has(t.file))
        if (routedBy.value.errors.length > 0) await noteDegraded($, `semantic routing: ${routedBy.value.errors[0]?.error ?? ''}`)
      } else {
        await noteDegraded($, routedBy.error)
      }
    }
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

  for (const [command, name] of Object.entries(PANELS)) {
    on('command.run', { command }, async $ => {
      await $.ui.open({ id: `noc-panel-${name}`, title: `NoctusAI · ${name}`, focus: true })
      void loadPanel($, name)
      return { text: `${name} pane opened.` }
    })
    on('ui.render', { component: 'Pane', requestId: `noc-panel-${name}` }, async ($, e) => {
      const { Box, Button, Text } = $.ui.resolve(e)
      const got = (await read($, panels))[name]
      const refresh = <Button key="refresh" label="Refresh" hotkey="r" onPress={() => void loadPanel($, name)} />
      if (got === undefined) return <Box flexDirection="column"><Text dimColor>Loading {name}…</Text>{refresh}</Box>
      if (typeof got === 'string') return <Box flexDirection="column"><Text color="red">Unavailable: {got}</Text>{refresh}</Box>
      const TONE = { ok: 'green', warn: 'yellow', bad: 'red', info: undefined } as const
      return (
        <Box flexDirection="column">
          <Text dimColor>{got.title} · {got.generated_at.slice(11, 19)}</Text>
          {got.sections.map(section => (
            <Box key={`s-${section.heading}`} flexDirection="column">
              <Text bold>{section.heading}</Text>
              {section.rows.map(row => (
                <Text key={`r-${section.heading}-${row.label}`} color={TONE[row.tone]} wrap="truncate-end">
                  {row.label}: {row.value}
                </Text>
              ))}
            </Box>
          ))}
          {got.errors.map(x => (
            <Text key={`e-${x.section}`} color="red" wrap="truncate-end">⚠ {x.section}: {x.error}</Text>
          ))}
          {refresh}
        </Box>
      )
    })
  }

  // Offer EXECUTOR agent types once a worktree exists to work in. UX only:
  // the Python executor-dispatch rule is what enforces; unknown ⇒ offered.
  on('agent.offer', async ($, e, next) => {
    const offered = await next(e)
    if (isOff || !enabled('executor_offer') || !offered.isOffered || !isExecutorOffer(e.description)) return offered
    const snap = await read($, full)
    if (snap === null || snap.worktrees === null) return offered
    const live = new Set((snap.branch_pointers ?? []).filter(p => p.status === 'on_going').map(p => p.worktree))
    const hasRoom = snap.worktrees.some(w => live.has(w.path) || [...live].some(l => l !== '' && w.path.endsWith(l)))
    return hasRoom ? offered : { isOffered: false }
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    if (isOff || !enabled('reminders_band') || e.props.hasSurvey || (await read($, bandHidden))) return next(e)
    const snap = await read($, fast)
    const pending = await read($, wrapup)
    const why = await read($, degraded)
    const reminders = snap?.reminders ?? []
    if (reminders.length === 0 && pending === null && why === null) return next(e)
    const { Box, Button, Text } = $.ui.resolve(e)
    const isOpen = await read($, bandExpanded)
    const room = Math.max(1, e.props.maxRows - 2)
    const count = reminders.length
    return (
      <Box flexDirection="column">
        {isOpen &&
          reminders.slice(0, room).map(r => (
            <Text key={r.file} color="yellow" wrap="truncate-end">
              🔔 {stripBell(r.title)}
            </Text>
          ))}
        {why !== null && (
          <Text key="degraded" color="red" wrap="truncate-end">
            noc-harness degraded — {why}
          </Text>
        )}
        <Box key="actions" flexDirection="row">
          {count > 0 && (
            <Text key="count" color="yellow">
              🔔 {count} owner reminder{count === 1 ? '' : 's'}{' '}
            </Text>
          )}
          {count > 0 && (
            <Button
              key="toggle"
              plain
              label={isOpen ? 'collapse' : 'show'}
              onPress={() => update($, bandExpanded, open => !open)}
            />
          )}
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
            <Text key="wrapup-hint" dimColor>
              {' '}/noc-wrapup · ctrl+x tab to focus{' '}
            </Text>
          )}
          {pending !== null && (
            <Button key="skip" label="Skip" onPress={() => update($, wrapup, () => null)} />
          )}
          <Button key="hide" plain label="hide" onPress={() => update($, bandHidden, () => true)} />
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
        <Text bold>Refusals & invalid harness this session ({recent.length})</Text>
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
