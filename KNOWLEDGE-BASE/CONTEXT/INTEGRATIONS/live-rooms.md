# Live rooms (LiveKit) — consume-side reference

> Seed organ: `noctusai_lib.integrations.live_rooms`. Shipped 2026-09-16
> (Slice L, `seed-live-rooms-livekit`) as a **re-point lift** from
> `products/therapy-platform`'s pre-existing (and, against the installed
> `livekit-api` SDK version, partially broken — see Gaps) ad-hoc LiveKit
> calls in `app/services/livekit_service.py`. Therapy-platform is the
> first + current consumer; `products/community`'s room-composite MP4
> egress (Wave 0 design) is the second planned consumer, unbuilt.

## What ships (seed)

- **`noctusai_lib.integrations.live_rooms`** — Protocol
  (`LiveRoomProvider`) + Fake (`FakeLiveRoomProvider`) + Real
  (`RealLiveKitProvider`) + factory (`make_live_room_provider`). Surface:
  `create_room` · `issue_join_token` · `close_room` ·
  `list_participants` / `remove_participant` · `start_recording` /
  `stop_recording` · `parse_webhook` (normalizes the `egress_ended`
  webhook event). Every method is `async` — including
  `issue_join_token`, which does no network IO in the LiveKit adapter
  (pure JWT signing) — because therapy's existing call sites already
  `await` every one of these; a Protocol with one sync method among
  seven async ones would force every consumer to special-case it.
- **One error type, both adapters**: `LiveRoomError(op, detail)` —
  never `HTTPException` (a call can happen in a webhook handler or
  background job, not only an HTTP request) — plus
  `LiveRoomNotConfigured` (a `LiveRoomError` subclass) raised by the
  factory when `use_fake=False` and `url`/`api_key`/`api_secret` are
  missing. **Both `RealLiveKitProvider` and `FakeLiveRoomProvider` RAISE
  on failure — neither ever silently degrades to mock data.** This is
  the fix-on-contact this slice shipped: the OLD
  `livekit_service.py` caught every real-provider exception and
  returned `{"mock": True, "error": ...}`, making a live LiveKit outage
  in prod indistinguishable from a successful dev-mode mock call.
- **Client construction is dependency-injected, never monkeypatched.**
  `RealLiveKitProvider(url=..., api_key=..., api_secret=...,
  client_factory=...)` — `client_factory` returns a fresh
  `livekit.api.LiveKitAPI(url, api_key, api_secret)` by default, or (in
  tests) a double exposing the same `.room`/`.egress` async surface
  plus `aclose()`. `test_real_livekit.py` injects a fake factory;
  nothing patches `livekit.api` itself.
- **`RecordingSpec(file_type, filepath, audio_only, layout, output)`**
  where `output` is `S3Output` (bucket/region/endpoint/access_key/
  secret/force_path_style — covers Supabase Storage's S3-compatible
  endpoint and Cloudflare R2 equally) or `DefaultOutput` (use the
  LiveKit-deployment-configured default egress store — what therapy
  uses today, since it has no S3 bucket of its own).
- **`livekit-api` is now a seed pyproject dependency** (monolithic-
  install convention, same as `stripe`/`docxtpl`), lazily imported
  inside `real_livekit.py`'s methods so the Fake path and the module
  import itself never require it. Was already present in the shared
  venv at `>=1.0.0` (1.1.0) before this slice.

## Consume recipe

```python
from noctusai_lib.integrations.live_rooms import make_live_room_provider
from noctusai_lib.integrations.live_rooms.types import RecordingSpec, S3Output

provider = make_live_room_provider(
    use_fake=settings.use_fake_live_rooms,  # EXPLICIT — never inferred from missing creds
    url=settings.livekit_url,
    api_key=settings.livekit_api_key,
    api_secret=settings.livekit_api_secret,
)
room = await provider.create_room("appt-123", max_participants=2)
token = await provider.issue_join_token(room.name, "therapist-1", display_name="Terapeuta")
handle = await provider.start_recording(
    room.name,
    RecordingSpec(file_type="ogg", audio_only=True, filepath=f"recordings/{room.name}.ogg"),
)
# ... later, once the room-composite egress finishes:
result = await provider.stop_recording(handle.recording_id)
```

**`use_fake` selection is always explicit, never inferred.** A consumer
reads its OWN settings flag (e.g. `THERAPY_USE_FAKE_LIVE_ROOMS`) —
never "credentials happen to be missing, so fall back to Fake." A prod
deploy missing `*_LIVEKIT_URL`/`*_API_KEY`/`*_API_SECRET` now raises
`LiveRoomNotConfigured` at first use instead of silently degrading.

## therapy-platform: the re-point

`app/services/livekit_service.py` is now a **thin mapper**, not a
second LiveKit-calling implementation — it keeps the OLD dict-shaped
call sites (`create_room(room_name)`, `generate_token(room_name,
participant_identity, participant_name)`, `start_recording(room_name,
segment_id)`, `stop_recording(recording_id)`, `close_room(room_name)`)
so `session_service.py` / `routers/sessions.py` didn't need a wholesale
rewrite, but every one of those functions now delegates to the seed
provider and lets `LiveRoomError` propagate.

`session_service.py` handles that error explicitly, split by whether
the failing call is fatal to the session:

- **Fatal** (`create_room`, `generate_token`/`issue_join_token`) — no
  room means no video call, no token means no join access. Wrapped by
  `_create_room_or_503` / `_generate_token_or_503`, which translate
  `LiveRoomError` into a visible `HTTPException(503, ...)`.
- **Degrades, doesn't block** (`start_recording`) — a therapy session
  should still happen even if egress is down. `_start_recording_degraded`
  catches the failure and returns `{"recording_failed": True, "error":
  ...}` instead of a `recording_id`; the segment's `recording_id`
  column then stays NULL — its natural "no recording" state, no schema
  change needed — and the client can surface a warning banner from
  `recording_failed`.
- **Best-effort cleanup** (`stop_recording`, `close_room`, used during
  pause/end/auto-finalize/reopen) — a LiveKit hiccup must not block a
  therapist from pausing or ending a session. `_stop_recording_best_effort`
  / `_close_room_best_effort` log the failure (never silently swallow —
  it's visible in logs/monitoring) and let the DB lifecycle transition
  proceed.

Therapy keeps `max_participants=2` and `audio_only=True, file_type="ogg"`
as its own consumer arguments, with `output=DefaultOutput()` (no S3
bucket of its own — relies on whatever egress store the LiveKit
deployment is configured with). `community`'s Wave 0 design instead
plans room-composite MP4 to an explicit `S3Output` — a different
`RecordingSpec`, same Protocol, no new seed surface needed.

## Prod status (2026-09-16, read-only check — no deploy files touched)

- **`THERAPY_LIVEKIT_URL`/`_API_KEY`/`_API_SECRET`** do not appear in
  the repo's `deploy/` tree or in `.env.example` (root or
  `products/therapy-platform/`) — only in
  `products/therapy-platform/THERAPY-IMPLEMENTATION-PLAN.md`'s setup
  instructions. Whether they're set on the VPS's untracked `.env` is
  unverifiable from the repo alone; this slice does not assume either
  way — `make_live_room_provider` raises `LiveRoomNotConfigured` if
  they're absent (see Gaps for the practical consequence).
- **No LiveKit egress service exists in `deploy/`** — no compose
  service, no ingress config. A room-composite (or any) egress needs a
  running LiveKit Egress service reachable at `THERAPY_LIVEKIT_URL`;
  none is provisioned in this repo's deploy surface today.

## Gaps / follow-ups

- **The OLD `livekit_service.py` was already broken against the
  installed SDK.** `livekit-api` 1.1.0 (already in the shared venv
  before this slice) removed `RoomServiceClient`/`EgressServiceClient`
  in favor of `LiveKitAPI().room`/`.egress`. The old code's blanket
  `try/except` around every real call meant a `AttributeError:
  module 'livekit.api' has no attribute 'RoomServiceClient'` would have
  been swallowed into `{"mock": True, "error": ...}` — i.e. even IF
  `THERAPY_LIVEKIT_*` were configured in prod, room creation and
  recording were silently no-ops; only `generate_token` (which never
  touched `RoomServiceClient`) could have worked for real.
  `RealLiveKitProvider` targets the current 1.x shape.
- **`community`'s room-composite-to-S3 recipe is unbuilt** — this slice
  ships the seed capability (`S3Output`, `RecordingSpec(file_type="mp4")`)
  but no `products/community` consumer exists yet.
- **No LiveKit egress deploy surface** — provisioning a reachable
  LiveKit server + Egress service for a real recording pipeline is out
  of this slice's scope (explicitly: no deploy files touched).
