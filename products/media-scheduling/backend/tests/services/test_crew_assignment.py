"""Skill-based crew assignment.

Ported from `whatsapp-google-scheduling/tests/test_crew_assignment.py`.

Source-side: SQLAlchemy join over `users` + `crew_skills`.
Product-side: Supabase client over `media_scheduling.authorized_users`
+ `media_scheduling.crew_skills`. Same algorithm: lowest-id active
`media_crew` whose owned skills superset the requested set wins.

Source seed: Cadu (id=4, photos only); Vini (id=6, photos+videos+reels+virtual_tour).
Lowest-id full-coverage rule:
  - pure photos                  → Cadu (covers, id=4 < id=6)
  - anything with videos/reels/virtual_tour → Vini (only one who covers)
  - photos+videos                → Vini (only one who covers both)
  - empty / unknown skill        → None
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.crew_assignment import pick_crew_for_services


# ---------------------------------------------------------------------------
# Supabase stub — minimal, enough for the two queries `pick_crew_for_services`
# issues:
#
#   1. authorized_users where role=media_crew, active=True, ordered by id asc.
#   2. crew_skills where user_id IN (...).
# ---------------------------------------------------------------------------


@dataclass
class _StubResponse:
    data: list[dict]


class _AuthorizedUsersBuilder:
    def __init__(self, users: list[dict]):
        self._users = users
        self._role: str | None = None
        self._active: bool | None = None

    def select(self, *_args, **_kwargs) -> "_AuthorizedUsersBuilder":
        return self

    def eq(self, col: str, value: object) -> "_AuthorizedUsersBuilder":
        if col == "role":
            self._role = str(value)
        elif col == "active":
            self._active = bool(value)
        return self

    def order(self, *_args, **_kwargs) -> "_AuthorizedUsersBuilder":
        return self

    def execute(self) -> _StubResponse:
        rows = self._users
        if self._role is not None:
            rows = [r for r in rows if r.get("role") == self._role]
        if self._active is not None:
            rows = [r for r in rows if bool(r.get("active")) is self._active]
        return _StubResponse(data=sorted(rows, key=lambda r: int(r["id"])))


class _CrewSkillsBuilder:
    def __init__(self, skills: list[dict]):
        self._skills = skills
        self._user_ids: list[int] | None = None

    def select(self, *_args, **_kwargs) -> "_CrewSkillsBuilder":
        return self

    def in_(self, col: str, values: list) -> "_CrewSkillsBuilder":
        if col == "user_id":
            self._user_ids = [int(v) for v in values]
        return self

    def execute(self) -> _StubResponse:
        rows = self._skills
        if self._user_ids is not None:
            rows = [r for r in rows if int(r["user_id"]) in self._user_ids]
        return _StubResponse(data=rows)


class _StubSchema:
    def __init__(self, users: list[dict], skills: list[dict]):
        self._users = users
        self._skills = skills

    def table(self, name: str):
        if name == "authorized_users":
            return _AuthorizedUsersBuilder(self._users)
        if name == "crew_skills":
            return _CrewSkillsBuilder(self._skills)
        raise AssertionError(f"unexpected table: {name}")


class _StubSupabase:
    def __init__(self, users: list[dict], skills: list[dict]):
        self._users = users
        self._skills = skills

    def schema(self, _name: str) -> _StubSchema:
        return _StubSchema(self._users, self._skills)


# ---------------------------------------------------------------------------
# Seed: Cadu (photos only), Vini (full package). Mirrors source mock_data.sql.
# ---------------------------------------------------------------------------


def _seeded() -> _StubSupabase:
    users = [
        {
            "id": 4,
            "name": "Cadu",
            "role": "media_crew",
            "phone_number": "+5511977776666",
            "email": "cadu@noctusai.com",
            "linked_identity": None,
            "active": True,
            "created_at": None,
            "updated_at": None,
        },
        {
            "id": 6,
            "name": "Vini",
            "role": "media_crew",
            "phone_number": "+5511988889898",
            "email": "vini@noctusai.com",
            "linked_identity": None,
            "active": True,
            "created_at": None,
            "updated_at": None,
        },
    ]
    skills = [
        {"user_id": 4, "skill": "photos"},
        {"user_id": 6, "skill": "photos"},
        {"user_id": 6, "skill": "videos"},
        {"user_id": 6, "skill": "reels"},
        {"user_id": 6, "skill": "virtual_tour"},
    ]
    return _StubSupabase(users, skills)


# ---------------------------------------------------------------------------
# Tests — one-to-one with the source repo.
# ---------------------------------------------------------------------------


def test_pure_photos_routes_to_cadu() -> None:
    crew = pick_crew_for_services(_seeded(), ["photos"])  # type: ignore[arg-type]

    assert crew is not None
    assert crew.name == "Cadu"
    assert crew.email == "cadu@noctusai.com"


def test_videos_only_routes_to_vini() -> None:
    crew = pick_crew_for_services(_seeded(), ["videos"])  # type: ignore[arg-type]

    assert crew is not None
    assert crew.name == "Vini"


def test_reels_routes_to_vini() -> None:
    crew = pick_crew_for_services(_seeded(), ["reels"])  # type: ignore[arg-type]

    assert crew is not None
    assert crew.name == "Vini"


def test_virtual_tour_routes_to_vini() -> None:
    crew = pick_crew_for_services(_seeded(), ["virtual_tour"])  # type: ignore[arg-type]

    assert crew is not None
    assert crew.name == "Vini"


def test_photos_plus_videos_routes_to_vini_because_only_he_covers_both() -> None:
    crew = pick_crew_for_services(_seeded(), ["photos", "videos"])  # type: ignore[arg-type]

    assert crew is not None
    assert crew.name == "Vini"


def test_full_package_routes_to_vini() -> None:
    crew = pick_crew_for_services(
        _seeded(),  # type: ignore[arg-type]
        ["photos", "videos", "reels", "virtual_tour"],
    )

    assert crew is not None
    assert crew.name == "Vini"


def test_unknown_skill_returns_none() -> None:
    crew = pick_crew_for_services(_seeded(), ["drone_video"])  # type: ignore[arg-type]

    assert crew is None


def test_empty_services_returns_none() -> None:
    # Source contract: empty needed-set returns None without DB roundtrip.
    assert pick_crew_for_services(_seeded(), []) is None  # type: ignore[arg-type]


def test_no_active_media_crew_returns_none() -> None:
    """Edge case: all crew inactive → no candidate to consider."""
    sb = _StubSupabase(
        users=[
            {
                "id": 4,
                "name": "Cadu",
                "role": "media_crew",
                "phone_number": "+5511977776666",
                "email": "cadu@noctusai.com",
                "linked_identity": None,
                "active": False,  # inactive
                "created_at": None,
                "updated_at": None,
            },
        ],
        skills=[{"user_id": 4, "skill": "photos"}],
    )
    assert pick_crew_for_services(sb, ["photos"]) is None  # type: ignore[arg-type]
