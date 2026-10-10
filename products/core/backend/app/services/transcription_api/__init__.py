"""Platform async transcription API — service layer (core, schema ``public``).

Contract: ``products/core/projects/transcription-api/CONTRACT.md`` (§1 auth,
§2 endpoints, §3 safety, §5 worker + retention). Everything IO-shaped goes
through a seam:

* transcriber        -> ``noctusai_lib.integrations.transcription`` (seed)
* queue + worker     -> ``noctusai_lib.domain.jobs`` (seed)
* audio storage      -> ``noctusai_lib.integrations.storage`` (seed)
* auth               -> ``noctusai_lib.api.auth.session`` (seed)
* burst rate limits  -> core's ``app.rate_limit.limiter``
* table access       -> ``repository.TranscricaoRepo`` (Protocol + Fake + Supabase)
"""
