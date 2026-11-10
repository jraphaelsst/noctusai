# Browser ops instead of the official APIs? Decision (2026-11-10)

- **Asked by:** the owner, typed in session b285e8 on 2026-11-10. Should a container on the server run Chrome, driven by Claude "as if it were me logged in", for Google and for one or more Instagram accounts, so the official APIs and app verification can wait?
- **Decider:** the branch steward (b285e8). The owner named it the decision maker. The council informs; the session that triggered it decides.
- **Pipeline (trial `decision-pipeline-browser-ops`):**
  1. The decider's prior, written and hashed before any input: `browser-ops/decider-prior.md`.
  2. Four independent specialist position reports in the team-of-teams §2 shape: `browser-ops/{architect,security,agents-security,legal}.md`.
  3. A blind council, `25e812af` (phase0, trust_boundary, 5 seats, 30 objections; brief `browser-ops/council-brief.md`), with an Opus chair.
  4. This decision.

## The decision
**Adopted: the chair's "B+C, API-first", with two additions of mine (marked ➕).**

1. **Google goes through the API only, never a browser.**
   - Extend the seed `google_drive` module with `DriveWriter`, `SheetsWriter` and `DocsWriter` (Protocol + Fake + Real + factory). The Assistant is consumer #1.
   - Start on the non-sensitive `drive.file` scope. Add `spreadsheets` and `documents` only when there is a measured need to edit files that already exist.
   - The "API that receives requests and executes them on Drive through the browser" is replaced by the Drive API, which has an audit trail.
2. ➕ **The Google token is minted fresh, once, by the owner.** On this machine the env trio has no refresh token. The only stored Google credential is a `drive.readonly` token from `drive_pull`, for the owner's account. The first step therefore reuses `drive_pull`'s server-less PKCE flow to mint the Assistant's owner token: Calendar, `drive.readonly` and `drive.file`. It costs the owner one consent click, and the "unverified app" screen is expected.
3. **Instagram goes through what the seed already ships.**
   - The Instagram Login adapter (`seed/lib/backend/noctusai_lib/integrations/meta/instagram_login_adapter.py`: profile, insights, media, stories, DM read and send) runs in Meta development mode, with the owner's account holding an app role.
   - Apify covers public profiles.
   - The residual logged-in actions the API cannot do run on the owner's laptop through Claude in Chrome, with the owner present.
4. **No server-side browser now.** A server runner may be built later, only after three gates:
   - (a) the residual Instagram jobs are listed and show recurring demand;
   - (b) a measured RSS spike under a cgroup `mem_limit` shows it fits on the VPS;
   - (c) a one-command kill switch exists, plus recorded-DOM fixtures, a Fake and a defined acceptance run.

   If it is built, its shape is fixed now:
   - one container, a separate profile and process per identity, never concurrent;
   - login over an SSH port-forward to a loopback VNC, switched on and off by hand;
   - recipes only, with Claude writing them at dev time;
   - expendable accounts first;
   - owner accounts only, with the client tier closed (legal red line: operator role, DPA, OAB);
   - no proxies, no evasion, no CAPTCHA solving;
   - a platform-tier `noctus.browser.*` service that sits outside the seed factory, so seed Real adapters stay API-only.
5. ➕ **The owner's "study a container" happens now, locally.** A measured browser-runner trial runs in Docker on the laptop: Playwright, one typed and versioned recipe definition, and an expendable Instagram account. It produces gate (b)'s RSS numbers and the recipe format that `noc-ig-analysis`, `noc-refs-sheet` and the QuintoAndar playbook converge on. Nothing runs on the VPS. This honours the owner's request to study the container without making prod its first contact.
6. **Confirmation outside WhatsApp.** The same WAHA self-chat both triggers and would confirm, so irreversible writes need a factor outside WAHA, or stay laptop-only until one exists (council F/YH). Slice 1 only creates calendar events, which are reversible (they can be deleted), so it is not blocked. The confirmation flow becomes a named seam in the seed agents/whatsapp layer, with the Assistant as consumer #1.
7. **Each interim recipe carries a `NOC-REMEDIATE[official-api]` marker** naming its replacement, owner, trigger and revisit date.

## What the pipeline changed against the decider's prior (trial metric)
1. **Instagram:** my prior said "a server browser container is the only quick path". It is not: the seed already ships an Instagram Login adapter, and I had missed it. The chair verified it, and the server container is now gated.
2. **Login channel:** my prior said noVNC "over the tunnel with auth"; it is now an SSH forward only.
3. **Proxies:** my prior was silent. The decision is no proxies; legal was right over the architect's residential-proxy option.
4. **Container count:** my prior said one container per account. The decision is one container with a profile and process per identity, reconciled against the measured capacity (3.5 GB free, 2 vCPU).
5. **The WAHA self-chat cannot be its own confirmation factor:** this was not in my prior at all.
6. **The Google token premise:** the council assumed the env trio; the decider's check found no refresh token locally (decision 2).

## Owner questions (the owner's to answer)
1. One Google consent click to mint the Assistant's token (Calendar + Drive read + `drive.file`), with the "unverified app" screen?
2. Instagram actions the API cannot do: laptop-only on your primary account with you watching, or an expendable account for the local container study? A written risk acceptance per account either way, as for WAHA.
3. A confirmation channel outside WAHA for irreversible writes: the platform admin UI, or a one-time code on another channel?

## First step (Monday, before building)
- Check both premises:
  - a `drive.file` write through the freshly minted owner token, starting the 7-day lifetime clock;
  - `get_profile` and `list_instagram_conversations` from the seed Instagram Login adapter against the owner's account, in dev mode.
- If either fails, return here. Do not fall back to Option A silently.
