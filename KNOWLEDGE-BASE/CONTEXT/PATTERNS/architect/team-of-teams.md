# Team of teams: one tree deployer, self-managing teams, decisions through the orchestrator

> Owner rule, typed 2026-11-09 (transcript `5ff8685d`), after the queue-lifecycle decision
> (`project-history/assistant-chatbot/queue-lifecycle-decision.md`). Written role-first on
> purpose: **no session names appear in the rule**, so it holds for 2 teams or 20.
> Composes with `KB § PATTERNS/architect/orchestration-craft-canon.md` §2 (team shape) and §6
> (session↔session protocol), `KB § PATTERNS/devops/release-steward.md` (the deployer role),
> `KB § PATTERNS/common/proposals-and-improvements.md` (the proposal record) and
> `KB § PATTERNS/common/council.md` (the council informs; the one who called it decides).

## 1 · The shape

```
                 owner
                   │
   ┌───────────────┼────────────────┐
 orchestrator A  orchestrator B  …  orchestrator N   ← one per team (a top-level session)
   │  team A       │  team B          │  team N        ← its subagents and slice branches
   └───────────────┴──────┬───────────┘
                          │ deliveries (release_steward request)
                   ONE tree deployer                  ← the release-steward lease holder
                          │
                   dev queue → main → prod
```

- **One tree deployer.** Exactly one session holds the lease: it enqueues to `dev`, lands, blesses,
  deploys and runs prod migrations. Every other team files deliveries and keeps building
  (`release-steward.md`). The deployer is a role, held by whichever session has the lease.
  It is the **guardian**, a service leaf under the owner (council 09340534, disposition A): its
  authority is the lane only, never content or priorities. It never patches a delivery branch
  and never opens a rescue branch (disposition B). An ejection goes back to the team's branch
  steward, who fixes it on its own branch (disposition K). An orphaned delivery parks as
  `blocked_on_steward` until the owner names a new branch steward (`release-steward.md` §7a).
- **Many teams, each self-managing.** A team is one orchestrator (a top-level session) plus the
  subagents and slice branches it dispatches. Inside its zone the team decomposes, builds,
  reviews and resolves on its own, without asking anyone.
- **The orchestrator is the team's single voice outward.** Members do not talk to other teams;
  their orchestrator does. This keeps the channel count about N instead of N(N−1)/2 (craft canon §2).

## 2 · Decisions between peers: positions up, common ground down

When two or more agents (**any role, any number**) have to settle something together, such as a
disagreement, a change that crosses zones, a shared file or the order of deliveries:

1. **Each party evaluates the grounds on its own.** It looks at the evidence through its own lens
   and does not negotiate the outcome with the others. Exchanging *facts* is fine; bargaining over
   the *decision* is not.
2. **Each party writes a position report:** what it claims, the grounds (evidence with paths or
   SHAs), what it proposes, and what it could accept. The reports are short and comparable.
3. **Every report goes to the manager,** meaning the orchestrator of the smallest team that contains
   all the parties:
   - **Same team:** that team's orchestrator.
   - **Different teams:** the parties are the team orchestrators themselves, and the manager is the
     next level up. Today that is the owner.
   - **The manager is itself a party:** the decision goes one level up.
4. **The parties wait on that matter only.** Waiting is not blocking: everything that does not
   depend on the answer keeps moving.
5. **The manager decides the common ground.** It decides from the reports. For a high-stakes case
   it may convene the council (the council informs, the one who called it decides). It records the
   decision durably and answers **all parties in one message**.
6. **Everyone continues on the common ground.** A party that still disagrees files a new report.
   It never acts on its own position.

The rule is recursive, so it scales. A party is always "a team's voice at this level", whether the
team is two subagents or ten sessions. No step names a session; the manager is found by
position in the tree.

**Worked instance (2026-11-10):**
- The two stewards on the queue-lifecycle spec each wrote a decision with grounds (point 1 and
  point 2 of the reconciled record).
- Both views sat in one record in front of the owner. The owner set the common ground: both
  stewards' points stand.
- Both stewards then continued.

The record is `project-history/assistant-chatbot/queue-lifecycle-decision.md`.

## 3 · Improvement proposals travel the tree and are never dropped

Any orchestrator may propose an improvement **anywhere** in the tree, including outside its own
zone: a tool, a rule, a seed organ, another team's process. Learning happens throughout the tree,
not only at the top.

1. **File it** as a proposal: `noctus.dev.file_proposal`, the template in `templates/PROPOSAL-TEMPLATE.md`.
2. **Address it to the orchestrator of the team that owns the affected zone.** Ownership comes
   from, in order: the role registry, `owns_kb:`, and the collision class.
3. **That orchestrator owes it exactly one exit** (`noctus.dev.set_proposal_status`, reason always
   recorded):
   - **dealt with:**
     - `accepted`: built or scheduled, with the named slice or roadmap;
     - `adapted`: accepted in another shape, and says which;
     - `rejected`: refused, with the reason.
   - **passed on:**
     - `forwarded`: the reason names the destination, either the team that really owns the zone
       or the next level up. The receiving orchestrator then owes the same exit.
4. **"Noted" is not an exit.** A proposal sitting in `pending` is debt: hygiene sweeps surface it
   (`noc-hygiene`), as with fix-on-contact.

## 4 · What stays outside this rule

- **Permissions are per session.** A manager's common ground never grants a permission, approves
  a prompt, edits `CLAUDE.md` or settings, or consents to prod. Those remain the owner's,
  verified against the harness-written transcript (craft canon §6.9, `prod-exposure-consent.md`).
- **The queue rule is the deployer's own procedure** (`merge-queue.md` §3–§4,
  `release-steward.md` §7a). This doc covers how teams relate to the deployer and to each other.

## 5 · Mechanism today and the named destination

| Step | Today | Mechanized by |
|---|---|---|
| Position reports and the decision | `SendMessage` plus a decision record in the deciding team's `project-history/` | the steward inbox `needs_info` record (decision record, build 4) gains `position` and `decision` kinds |
| Manager lookup | the orchestrator reads the role registry (`release_steward` roles) | the role registry resolves "the manager of {parties}" |
| Proposal exits | `set_proposal_status` with `accepted`, `adapted`, `rejected` or `forwarded`, and a reason | `noc-hygiene` lists `pending` proposals older than 7 days |

Telemetry for the study: every resolution and every proposal exit is a row in
`project-history/assistant-chatbot/multi-steward-study.md` until the inbox kinds exist.
