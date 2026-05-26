# SSH deploy-key restrictions — `restrict` vs `permitopen` quirk

Standalone gotcha encountered while wiring the GitHub Actions tunnel into prod
`noctus-cache-pg` (see `KB § PATTERNS/devops/ci-embedding-cache-gate.md`).
Worth pinning so the next time someone provisions a restricted deploy key on
OpenSSH 9.x they don't repeat the same hour of trial-and-error.

## The trap

Intuitive form (what you'd write first):

```
restrict,permitopen="127.0.0.1:5432" ssh-ed25519 AAAA… deploy-key@<host>
```

The intent is clean: `restrict` drops every dangerous capability (pty, X11,
agent-forwarding, port-forwarding, exec) and `permitopen` punches a single
controlled hole back through to localhost:5432. The man page for
`authorized_keys` even lists them as composable.

What actually happens on **Ubuntu OpenSSH_9.6p1** (and matches what was
verified in-flight 2026-05-26 via `ssh -v`):

```
debug1: Sending command: ...
channel 0: open failed: administratively prohibited: open failed
```

`restrict` overrides the `permitopen` allow-list because `restrict` includes
`no-port-forwarding` and the override happens at the openssh policy layer
rather than the keyword layer. Net effect: no port forwarding allowed at all,
even though `permitopen` is sitting right there next to it.

## The canonical pattern

Spell out each restriction explicitly — drop `restrict` entirely:

```
command="/bin/false",no-pty,no-X11-forwarding,no-agent-forwarding,permitopen="127.0.0.1:5432" ssh-ed25519 AAAA… deploy-key@<host>
```

This produces the intended deploy-key shape:

- `command="/bin/false"` — every interactive/exec attempt returns failure
  immediately. The key cannot shell.
- `no-pty` — no allocation of a controlling terminal.
- `no-X11-forwarding` / `no-agent-forwarding` — close those covert sub-channels.
- `permitopen="127.0.0.1:5432"` — the ONE permitted forward. The key may open
  `-L 5432:127.0.0.1:5432` (or any local port → 127.0.0.1:5432 on the host).
  Nothing else.

Verify with the same `ssh -vv -i <key> -L 5432:127.0.0.1:5432 -fN <host>` —
you should see the channel open succeed, no "administratively prohibited".

## Why we don't just drop `restrict` everywhere

`restrict` is still the right primitive when you have a key that should do
NOTHING (no port-forwarding, no exec, no anything). The catch is that
`restrict` and `permitopen` don't compose the way the man page implies — so
the moment you want to permit one forward, expand to the explicit form.

## Related

- `KB § PATTERNS/devops/ci-embedding-cache-gate.md` — the CI workflow that
  consumes this key shape.
- `KB § PATTERNS/devops/prod-cache-container.md` — the host-loopback compose
  that this tunnel reaches (`127.0.0.1:5432` carve-out).
- `feedback_cache_pg_live_prod.md` — the memory entry that named the conflict
  in passing; this KB note is the depth pointer.
