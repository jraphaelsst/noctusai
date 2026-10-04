"""FakeEditorialStore invariants + factory + the Supabase store's error mapping."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
from uuid import uuid4

import pytest

from noctusai_lib.domain.editorial import (
    EditorialConflict,
    EditorialDenied,
    EditorialNotFound,
    FakeEditorialStore,
    content_sha_of,
    make_editorial_store,
)
from noctusai_lib.domain.editorial.store_supabase import SupabaseEditorialStore, map_db_error

ORG = uuid4()
AUTHOR, ED, SEC, PUB = (uuid4() for _ in range(4))
EDIT, REV, REVSEC, PUBLICAR = (
    ["editorial:editar"], ["editorial:revisar"], ["editorial:revisar_seguranca"], ["editorial:publicar"],
)


def _store():
    return FakeEditorialStore()


def _create(s, content=None):
    return s.create_item(org_id=ORG, kind="doc", ref="a", content=content or {"t": "v1"}, actor_id=AUTHOR, grants=EDIT).item


def _publish_round(s, item_id, *, ed=ED, sec=SEC, pub=PUB):
    k = dict(org_id=ORG, item_id=item_id)
    s.apply(action="submit", actor_id=AUTHOR, grants=EDIT, **k)
    s.apply(action="approve_editorial", actor_id=ed, grants=REV, **k)
    s.apply(action="approve_security", actor_id=sec, grants=REVSEC, **k)
    return s.apply(action="publish", actor_id=pub, grants=PUBLICAR, **k)


def test_create_makes_item_v1_and_event():
    s = _store()
    r = s.create_item(org_id=ORG, kind="doc", ref="a", content={"t": 1}, actor_id=AUTHOR, grants=EDIT)
    assert (r.item.state, r.item.current_version_n, r.item.published_version_n) == ("rascunho", 1, None)
    assert r.version.n == 1 and r.version.author_id == AUTHOR and r.version.content_sha == content_sha_of({"t": 1})
    assert [(e.action, e.from_state, e.to_state, e.grant) for e in s.list_events(ORG, r.item.id)] == [
        ("create", None, "rascunho", "editorial:editar")
    ]


def test_create_needs_grant_and_is_unique_per_org_kind_ref():
    s = _store()
    with pytest.raises(EditorialDenied) as e:
        s.create_item(org_id=ORG, kind="doc", ref="a", content={}, actor_id=AUTHOR, grants=REV)
    assert e.value.code == "missing_grant"
    _create(s)
    with pytest.raises(EditorialConflict):
        _create(s)
    s.create_item(org_id=uuid4(), kind="doc", ref="a", content={}, actor_id=AUTHOR, grants=EDIT)  # other org ok


def test_full_happy_path_publishes_and_logs_every_step():
    s = _store()
    item = _create(s)
    r = _publish_round(s, item.id)
    assert (r.item.state, r.item.published_version_n) == ("publicado", 1)
    evs = s.list_events(ORG, item.id)
    assert [e.action for e in evs] == ["create", "submit", "approve_editorial", "approve_security", "publish"]
    assert [e.actor_id for e in evs] == [AUTHOR, AUTHOR, ED, SEC, PUB]
    assert [e.id for e in evs] == sorted(e.id for e in evs)
    assert s.get_published_version(ORG, item.id).content == {"t": "v1"}


@pytest.mark.parametrize("who,action,grants,code", [
    (AUTHOR, "approve_editorial", REV, "self_approval"),
    (ED, "approve_editorial", EDIT, "missing_grant"),
])
def test_editorial_approval_refusals(who, action, grants, code):
    s = _store()
    item = _create(s)
    s.apply(org_id=ORG, item_id=item.id, action="submit", actor_id=AUTHOR, grants=EDIT)
    with pytest.raises(EditorialDenied) as e:
        s.apply(org_id=ORG, item_id=item.id, action=action, actor_id=who, grants=grants)
    assert e.value.code == code
    assert s.get_item(ORG, item.id).state == "revisao_editorial"  # a refusal changes nothing
    assert len(s.list_events(ORG, item.id)) == 2


def test_security_approver_must_differ_from_editorial_approver_and_author():
    s = _store()
    item = _create(s)
    k = dict(org_id=ORG, item_id=item.id)
    s.apply(action="submit", actor_id=AUTHOR, grants=EDIT, **k)
    s.apply(action="approve_editorial", actor_id=ED, grants=REV, **k)
    for who, code in ((ED, "same_approver"), (AUTHOR, "self_approval")):
        with pytest.raises(EditorialDenied) as e:
            s.apply(action="approve_security", actor_id=who, grants=REVSEC, **k)
        assert e.value.code == code


def test_publish_needs_signoff_and_a_non_author():
    s = _store()
    item = _create(s)
    k = dict(org_id=ORG, item_id=item.id)
    s.apply(action="submit", actor_id=AUTHOR, grants=EDIT, **k)
    s.apply(action="approve_editorial", actor_id=ED, grants=REV, **k)
    with pytest.raises(EditorialDenied) as e:
        s.apply(action="publish", actor_id=PUB, grants=PUBLICAR, **k)
    assert e.value.code == "security_signoff_missing"
    s.apply(action="approve_security", actor_id=SEC, grants=REVSEC, **k)
    with pytest.raises(EditorialDenied) as e:
        s.apply(action="publish", actor_id=AUTHOR, grants=PUBLICAR, **k)
    assert e.value.code == "self_approval"


def test_send_back_requires_motivo_and_resets_the_round():
    s = _store()
    item = _create(s)
    k = dict(org_id=ORG, item_id=item.id)
    s.apply(action="submit", actor_id=AUTHOR, grants=EDIT, **k)
    s.apply(action="approve_editorial", actor_id=ED, grants=REV, **k)
    with pytest.raises(EditorialDenied) as e:
        s.apply(action="send_back", actor_id=SEC, grants=REVSEC, **k)
    assert e.value.code == "motivo_required"
    back = s.apply(action="send_back", actor_id=SEC, grants=REVSEC, motivo="fonte duvidosa", **k)
    assert back.item.state == "rascunho" and back.event.motivo == "fonte duvidosa"
    # same version re-submitted: the old editorial approval no longer counts
    s.apply(action="submit", actor_id=AUTHOR, grants=EDIT, **k)
    s.apply(action="approve_editorial", actor_id=SEC, grants=REV, **k)  # SEC may now be the editorial approver
    with pytest.raises(EditorialDenied) as e:
        s.apply(action="approve_security", actor_id=SEC, grants=REVSEC, **k)
    assert e.value.code == "same_approver"


def test_versions_are_immutable():
    s = _store()
    content = {"t": {"nested": [1, 2]}}
    item = s.create_item(org_id=ORG, kind="doc", ref="i", content=content, actor_id=AUTHOR, grants=EDIT).item
    content["t"]["nested"].append(3)  # caller mutates its own dict afterwards
    v = s.list_versions(ORG, item.id)[0]
    assert v.content == {"t": {"nested": [1, 2]}}
    v.content["t"]["nested"].append(99)  # mutating a returned copy never reaches the store
    assert s.list_versions(ORG, item.id)[0].content == {"t": {"nested": [1, 2]}}
    with pytest.raises(FrozenInstanceError):
        v.n = 5  # type: ignore[misc]
    assert not hasattr(s, "update_version") and not hasattr(s, "delete_version")


def test_events_are_append_only():
    s = _store()
    item = _create(s)
    first = s.list_events(ORG, item.id)[0]
    with pytest.raises(FrozenInstanceError):
        first.actor_id = uuid4()  # type: ignore[misc]
    s.apply(org_id=ORG, item_id=item.id, action="submit", actor_id=AUTHOR, grants=EDIT)
    after = s.list_events(ORG, item.id)
    assert after[0] == first and len(after) == 2
    assert not any(hasattr(s, n) for n in ("update_event", "delete_event"))


def test_edit_after_publish_keeps_the_published_version_serving():
    s = _store()
    item = _create(s)
    _publish_round(s, item.id)
    r = s.apply(org_id=ORG, item_id=item.id, action="edit", actor_id=ED, grants=EDIT, content={"t": "v2"})
    assert (r.item.state, r.item.current_version_n, r.item.published_version_n) == ("rascunho", 2, 1)
    assert r.version.n == 2 and r.version.author_id == ED  # the editor is the author of v2
    assert s.get_published_version(ORG, item.id).content == {"t": "v1"}  # still serving v1
    # v2 goes through review; the new author (ED) cannot approve their own version
    k = dict(org_id=ORG, item_id=item.id)
    s.apply(action="submit", actor_id=ED, grants=EDIT, **k)
    with pytest.raises(EditorialDenied) as e:
        s.apply(action="approve_editorial", actor_id=ED, grants=REV, **k)
    assert e.value.code == "self_approval"
    s.apply(action="approve_editorial", actor_id=AUTHOR, grants=REV, **k)
    s.apply(action="approve_security", actor_id=SEC, grants=REVSEC, **k)
    r = s.apply(action="publish", actor_id=PUB, grants=PUBLICAR, **k)
    assert r.item.published_version_n == 2
    assert s.get_published_version(ORG, item.id).content == {"t": "v2"}
    assert [v.n for v in s.list_versions(ORG, item.id)] == [1, 2]


def test_one_draft_at_a_time_edit_is_locked_during_review():
    s = _store()
    item = _create(s)
    k = dict(org_id=ORG, item_id=item.id)
    s.apply(action="submit", actor_id=AUTHOR, grants=EDIT, **k)
    for _ in range(2):
        with pytest.raises(EditorialDenied) as e:
            s.apply(action="edit", actor_id=AUTHOR, grants=EDIT, content={"t": "x"}, **k)
        assert e.value.code == "illegal_transition"
    assert len(s.list_versions(ORG, item.id)) == 1


def test_edit_in_rascunho_mints_next_version_and_needs_content():
    s = _store()
    item = _create(s)
    k = dict(org_id=ORG, item_id=item.id)
    with pytest.raises(EditorialDenied) as e:
        s.apply(action="edit", actor_id=AUTHOR, grants=EDIT, **k)
    assert e.value.code == "content_required"
    r = s.apply(action="edit", actor_id=AUTHOR, grants=EDIT, content={"t": "v2"}, **k)
    assert r.item.current_version_n == 2 and len(s.list_versions(ORG, item.id)) == 2


def test_archive_stops_serving_and_is_terminal():
    s = _store()
    item = _create(s)
    _publish_round(s, item.id)
    k = dict(org_id=ORG, item_id=item.id)
    with pytest.raises(EditorialDenied) as e:
        s.apply(action="archive", actor_id=PUB, grants=PUBLICAR, **k)
    assert e.value.code == "motivo_required"
    r = s.apply(action="archive", actor_id=PUB, grants=PUBLICAR, motivo="obsoleto", **k)
    assert (r.item.state, r.item.published_version_n) == ("arquivado", None)
    assert s.get_published_version(ORG, item.id) is None
    with pytest.raises(EditorialDenied):
        s.apply(action="edit", actor_id=AUTHOR, grants=EDIT, content={}, **k)


def test_org_scoping_and_queue_filters():
    s = _store()
    a = _create(s)
    other = uuid4()
    with pytest.raises(EditorialNotFound):
        s.get_item(other, a.id)
    with pytest.raises(EditorialNotFound):
        s.apply(org_id=other, item_id=a.id, action="submit", actor_id=AUTHOR, grants=EDIT)
    s.create_item(org_id=ORG, kind="act", ref="b", content={}, actor_id=AUTHOR, grants=EDIT)
    s.apply(org_id=ORG, item_id=a.id, action="submit", actor_id=AUTHOR, grants=EDIT)
    assert [i.id for i in s.list_items(ORG, state="revisao_editorial")] == [a.id]
    assert len(s.list_items(ORG)) == 2 and len(s.list_items(ORG, kind="act")) == 1 and s.list_items(other) == []


def test_factory_fake_real_and_no_silent_fallback():
    assert isinstance(make_editorial_store("agents", use_fake=True), FakeEditorialStore)
    with pytest.raises(RuntimeError):
        make_editorial_store("agents")
    assert isinstance(make_editorial_store("agents", client=object()), SupabaseEditorialStore)


@pytest.mark.parametrize("msg,code", [
    ("{'message': 'editorial_missing_grant', 'code': 'P0001'}", "missing_grant"),
    ("editorial_self_approval", "self_approval"),
    ("editorial_security_signoff_missing", "security_signoff_missing"),
    ("editorial_write_via_transition_only", "write_via_transition_only"),
])
def test_db_refusals_map_to_the_same_typed_denial(msg, code):
    err = map_db_error(RuntimeError(msg))
    assert isinstance(err, EditorialDenied) and err.code == code


def test_db_error_mapping_other_shapes():
    assert isinstance(map_db_error(RuntimeError("editorial_item_not_found")), EditorialNotFound)
    assert isinstance(map_db_error(RuntimeError("duplicate key editorial_items_org_kind_ref_key")), EditorialConflict)
    boom = RuntimeError("network down")
    assert map_db_error(boom) is boom
