"""Pesquisa wave 2 (Extrair + Assuntos Virais) closed vocabularies.

Single Python source of truth for the CHECK enums in migration
``221_cs_research_extraction.sql``. Later slices import these; a test
(`test_pesquisa_wave2_migration.py`) asserts the SQL carries exactly these
values, so code and table cannot drift. Contract:
projects/core-studio/specs/pesquisa-wave2-contract.md section 2.
"""

from __future__ import annotations

#: Post sources an extraction can read (``source_kind``). A future
#: monitored-profile source is one more value here + the two CHECKs.
FONTE_KINDS: tuple[str, ...] = ("instagram_media", "youtube_video", "mc_post")

#: What an extraction job produces (``cs_extraction_jobs.tipos`` elements and
#: ``cs_extraction_post_runs.tipo``).
EXTRACAO_TIPOS: tuple[str, ...] = ("pesquisa", "assuntos_virais")

#: Max elements of ``cs_extraction_jobs.tipos`` (combined job allowed).
EXTRACAO_TIPOS_MAX: int = 2

EXTRACAO_STATUSES: tuple[str, ...] = (
    "queued",
    "running",
    "completed",
    "completed_with_errors",
    "failed",
    "cancelled",
)

#: Statuses held by the partial unique index "one active job per user".
EXTRACAO_ACTIVE_STATUSES: tuple[str, ...] = ("queued", "running")

POST_RUN_STATUSES: tuple[str, ...] = ("done", "failed", "skipped")

#: ``cs_extraction_post_runs.motivo`` (NULL allowed).
POST_RUN_MOTIVOS: tuple[str, ...] = ("sem_texto", "llm_erro", "cancelado")

VIRAL_TOPIC_STATUSES: tuple[str, ...] = ("pending", "approved", "rejected")
VIRAL_TOPIC_ORIGINS: tuple[str, ...] = ("manual", "extraction")

VIRAL_TOPIC_MAX_CHARS: int = 255
