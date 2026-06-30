# CI-dispatchable prod deploy (`.github/workflows/deploy-prod.yml`)

A `workflow_dispatch` GitHub Actions workflow that fast-forwards the VPS checkout
(`/opt/noctus/noctusai`) to `origin/prod` (or `origin/main`) over CI. CI runners
have open egress and can SSH the VPS, so deploys work from environments that
**cannot make outbound `:22` connections** — e.g. a sandboxed agent (egress
proven to block port 22; `github.com:22` times out, `:443` works), or any
network where SSH is filtered.

It does **not** supersede `noctus.dev.release` — bless/promote stays the
source-of-truth gate deciding WHAT lands on `prod`. This only **pulls
`origin/prod` onto the box** (the `noctus.dev.deploy_pull` step), triggerable
without a local SSH path.

## Security model — forced-command + ref-whitelist (defense in depth)

The deploy key is a **forced-command key**: its `authorized_keys` entry pins the
command to `scripts/deploy/prod-pull.sh`, so the key can run ONLY the safe §2a
pull script — it can never get a shell or run arbitrary commands. Same lockdown
philosophy as the existing port-forward-only cache key
(`command="/bin/false",permitopen="127.0.0.1:5432"`). The client's requested
`<mode> <ref>` arrives in `$SSH_ORIGINAL_COMMAND`, which the script treats as
UNTRUSTED and re-validates (mode ∈ {dry-run,apply}; ref ∈ {origin/prod,
origin/main, 40-hex-sha}). The workflow inputs are `choice`-constrained too, so
there is no free-text injection surface even before the VPS-side whitelist.

`prod-pull.sh` runs the §2a drill (mirrors `noctus.dev.deploy_pull`): inspect →
**refuse non-FF** (HEAD must be an ancestor of the target) → **refuse overlap**
(an incoming file with uncommitted local edits) → backup (`git tag
deploy-backup-<ts>` + a `tar` snapshot OUTSIDE the repo) → `git merge --ff-only`.
By construction it never runs `reset` / `checkout -f` / `clean` / `push` / any
force.

## Dormant until provisioned

With `NOCTUS_VPS_DEPLOY_PROD_KEY` / `NOCTUS_VPS_HOST` unset the job emits a
`::warning::` and no-ops — safe to ship to `prod` inert. The secret→`env`
mapping + step-output gate is deliberate: the `secrets` context is **forbidden in
step `if:`** (it fails the workflow at STARTUP with no logs) — so the guard step
reads the env vars and writes `ready=1`, and the SSH step gates on
`steps.guard.outputs.ready` (a `steps` context, allowed in `if:`). See
`memory feedback_ci_secrets_in_if_startup_failure`.

## One-time activation runbook (requires VPS access — operator does this once)

1. **Generate a dedicated key on a trusted machine:**
   `ssh-keygen -t ed25519 -f noctus-deploy-prod -C "ci-deploy-prod" -N ""`
2. **On the VPS**, add the PUBLIC half to `root`'s `~/.ssh/authorized_keys` as a
   forced-command entry (one line):
   ```
   command="/opt/noctus/noctusai/scripts/deploy/prod-pull.sh",no-pty,no-port-forwarding,no-X11-forwarding,no-agent-forwarding ssh-ed25519 AAAA... ci-deploy-prod
   ```
3. **On the VPS**, ensure the script is executable (it ships in the repo at that
   path, so it is present after any checkout — but `git` does not always preserve
   the exec bit on a fresh clone): `chmod +x /opt/noctus/noctusai/scripts/deploy/prod-pull.sh`.
   Bootstrap note (chicken-and-egg): the FIRST deploy that introduces this script
   must reach the VPS some other way (a manual `git pull` once, or the existing
   local `noctus.dev.deploy_pull`); thereafter the workflow is self-sufficient.
4. **Set the repo secrets** (Settings → Secrets and variables → Actions):
   - `NOCTUS_VPS_DEPLOY_PROD_KEY` — the PRIVATE half of the key.
   - `NOCTUS_VPS_HOST` — the VPS hostname (already used by the cache-gate workflow).
5. **Trigger:** `gh workflow run deploy-prod.yml -f mode=dry-run` (review the
   plan in the run logs), then `gh workflow run deploy-prod.yml -f mode=apply`.

## Composition

- Build/push images: `build-and-push.yml` → GHCR `:<sha>` (the artifact layer).
- Decide what is on prod: `noctus.dev.release` bless → promote (the gate).
- Pull onto the VPS: this workflow OR local `noctus.dev.deploy_pull` (the
  reachability layer — same §2a drill, two transports).
- For runtime-image changes a container recreate is still a separate step
  (`noctus.dev.deploy_image` / `noctus.vps.recreate`); this workflow only does the
  git-FF, which is sufficient for non-runtime changes (KB/docs/tooling).

→ `noctus.dev.deploy_pull` · `.github/workflows/embedding-cache-gate.yml` (the
vetted VPS-SSH-from-CI pattern) · `KB § GUIDES/production-deploy.md § 2a`.
