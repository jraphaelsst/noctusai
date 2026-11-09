# Handoff cloud → noc-0 (owner asleep; this file + commit bodies are the channel)

Owner order (2026-11-09): the cloud steward only puts work on branches; noc-0 owns
enqueue, merge and deploy. The owner is not relaying messages tonight — read this file
and the commit bodies on `cloud-work-2`.

## Protocol

1. `cloud-work` (mq/cloud-work--7c13213) is yours, already enqueued.
2. `cloud-work-2` is **NOT ready** until its tip commit subject starts with
   `chore(cloud-work-2): READY`. Before that, do not enqueue it, even if it moves.
3. When `cloud-work` lands, the cloud rebases `cloud-work-2` on `origin/dev`, re-runs
   the Tailwind codemod + `check_tailwind_v4_class_names` over the merged tree,
   regenerates the lockfiles, runs the fleet verify, and pushes the READY commit.
   The READY commit body lists what was verified and anything you must know.
4. If `cloud-work` is EJECTED: the cloud cannot read your messages. Leave the reason in
   a commit on `cloud-work` with subject `chore(cloud-work): EJECTED — <reason>` (or in
   the merge-queue status). The cloud checks the branch and the queue status on its own
   schedule and fixes on `cloud-work` itself.
5. Deploy: entirely yours. Nothing on these branches touches migrations, prod, `main`.

## What cloud-work-2 carries (detail in MANIFEST.md §4)

academia "Entrar" removal · actions/cache v6.1.0 · @hookform/resolvers 7 ·
google-genai <2.34 · lucide-react 1.70 (+ `@noctusai/lib/brand-icons`) ·
Tailwind 4.3 with the v3 look pinned · keeper `check_tailwind_v4_class_names`
(warn-first, D24).

## Deploy notes for when it ships

- Fleet-wide FE change (seed entry CSS): every active product image rebuilds.
- Browser floor rises to Safari 16.4+, Chrome 111+, Firefox 128+.
- Post-deploy: open one page per product (login + a list page) and look at it; the
  automated checks do not render the bundle (noc-dep-update guardrail).
- Inactive products are untouched and stay on their own v3 setup.
