"""CoreStudio S5: key convention, signed download URLs, upload adoption, ``apagar_insumos`` (owner rule Q5).

Real seams: a ``FakeStorageBackend`` + the mock Supabase client; the event row is written by migration 346's AFTER
trigger (same transaction by construction), so it is asserted on the migration SQL.
"""
from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import pytest
from noctusai_lib.integrations.storage import FakeStorageBackend
from noctusai_lib.testing.migrations import migration_path
from noctusai_lib.testing.mocks import MockSupabaseClient

from app.modules.media_creation import midia_storage as ms
from app.modules.media_creation.midia_storage import MIDIA_BUCKET, MidiaStorageError

ORG = str(uuid.uuid4())
SQL = migration_path(Path(__file__).resolve().parents[3], "cs_post_insumos_apagados").read_text(encoding="utf-8")


def _id() -> str:
    return str(uuid.uuid4())


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def env():
    db = MockSupabaseClient()
    storage = FakeStorageBackend()
    post = _id()
    db.from_("cs_posts").insert({"id": post, "org_id": ORG, "titulo": "P"}).execute()
    return db, storage, post


def _put(storage, post, zona, nome, org=ORG):
    key = f"org/{org}/posts/{post}/{zona}/{nome}"
    run(storage.put(bucket=MIDIA_BUCKET, key=key, data=b"x", content_type="video/mp4"))
    return key


def _asset(db, post, key, ordem, status="pronto", org=ORG):
    aid = _id()
    db.from_("cs_post_assets").insert({
        "id": aid, "org_id": org, "post_id": post, "storage_path": key, "ordem": ordem, "versao": 1, "status": status,
        "tipo_midia": "video", "apagado_em": None,
    }).execute()
    return aid


def _exists(storage, key):
    return run(storage.exists(bucket=MIDIA_BUCKET, key=key))


class TestKeys:
    def test_prefix_convention(self):
        assert ms.prefixo_zona(ORG, "abcdef12", "insumos") == f"org/{ORG}/posts/abcdef12/insumos/"
        assert ms.zona_de(f"org/{ORG}/posts/abcdef12/preview/a.png") == "preview"
        assert ms.zona_de(f"org/{ORG}/posts/abcdef12/a.png") is None

    def test_chave_upload_sanitises_and_never_takes_a_client_prefix(self):
        k = ms.chave_upload(ORG, "abcdef12", "insumos", "../../etc/pa ss?.mp4")
        assert k == f"org/{ORG}/posts/abcdef12/insumos/pa_ss_.mp4"

    @pytest.mark.parametrize("bad", ["../x", "org/other/posts/p/insumos/a.mp4", "/insumos/a.mp4"])
    def test_validar_chave_refuses_foreign_or_traversal(self, bad):
        with pytest.raises(MidiaStorageError):
            ms.validar_chave(ORG, "abcdef12", bad)

    def test_validar_chave_requires_a_zone(self):
        with pytest.raises(MidiaStorageError):
            ms.validar_chave(ORG, "abcdef12", f"org/{ORG}/posts/abcdef12/a.mp4")
        assert ms.validar_chave(ORG, "abcdef12", f"org/{ORG}/posts/abcdef12/saidas/a.mp4") == "saidas"

    def test_invalid_ids_are_refused(self):
        with pytest.raises(MidiaStorageError):
            ms.prefixo_post("a/../b", "abcdef12")

    def test_download_url_is_signed_with_default_ttl_and_scoped(self, env):
        _, storage, post = env
        key = _put(storage, post, "saidas", "a.mp4")
        url = run(ms.url_download(storage, org_id=ORG, post_id=post, storage_path=key))
        assert "expires=" in url
        with pytest.raises(MidiaStorageError):
            run(ms.url_download(storage, org_id=_id(), post_id=post, storage_path=key))


class TestApagarInsumos:
    def test_deletes_only_insumos_and_marks_rows(self, env):
        db, storage, post = env
        i1, i2 = _put(storage, post, "insumos", "a.mp4"), _put(storage, post, "insumos", "b.mp4")
        saida, prev = _put(storage, post, "saidas", "final.mp4"), _put(storage, post, "preview", "p.png")
        a_in = _asset(db, post, i1, 1)
        a_out = _asset(db, post, saida, 2, status="aprovado")
        res = run(ms.apagar_insumos(db, storage, org_id=ORG, post_id=post, ator_id=_id()))
        assert (res.blobs_apagados, res.assets_marcados) == (2, 1)
        assert not _exists(storage, i1) and not _exists(storage, i2)
        assert _exists(storage, saida) and _exists(storage, prev)  # approved outputs + preview are never deleted
        rows = {r["id"]: r for r in db.from_("cs_post_assets").select("*").execute().data}
        assert rows[a_in]["apagado_em"] is not None
        assert rows[a_out]["apagado_em"] is None and rows[a_out]["status"] == "aprovado"

    def test_idempotent(self, env):
        db, storage, post = env
        _asset(db, post, _put(storage, post, "insumos", "a.mp4"), 1)
        run(ms.apagar_insumos(db, storage, org_id=ORG, post_id=post))
        again = run(ms.apagar_insumos(db, storage, org_id=ORG, post_id=post))
        assert (again.blobs_apagados, again.assets_marcados) == (0, 0)

    def test_does_not_touch_another_posts_insumos(self, env):
        db, storage, post = env
        outro = _id()
        db.from_("cs_posts").insert({"id": outro, "org_id": ORG, "titulo": "O"}).execute()
        k = _put(storage, outro, "insumos", "a.mp4")
        run(ms.apagar_insumos(db, storage, org_id=ORG, post_id=post))
        assert _exists(storage, k)

    def test_foreign_org_post_is_not_found(self, env):
        db, storage, post = env
        with pytest.raises(MidiaStorageError) as e:
            run(ms.apagar_insumos(db, storage, org_id=_id(), post_id=post))
        assert e.value.code == "post_nao_encontrado"

    def test_recovers_after_blobs_gone_but_rows_unmarked(self, env):
        db, storage, post = env
        k = _put(storage, post, "insumos", "a.mp4")
        a = _asset(db, post, k, 1)
        run(storage.delete(bucket=MIDIA_BUCKET, key=k))  # a previous run died between the two steps
        res = run(ms.apagar_insumos(db, storage, org_id=ORG, post_id=post))
        assert res.assets_marcados == 1
        assert db.from_("cs_post_assets").select("*").eq("id", a).execute().data[0]["apagado_em"] is not None


class TestAdotarUpload:
    def test_moves_the_assembled_upload_into_the_post_zone(self, env):
        _, storage, post = env

        class _Sessao:
            filename, content_type = "Meu Video.mp4", "video/mp4"

        class _Svc:
            async def consume(self, *, org_id, session_id):
                return _Sessao(), b"bytes"

        key = run(ms.adotar_upload(_Svc(), storage, org_id=ORG, post_id=post, upload_id=_id()))
        assert key == f"org/{ORG}/posts/{post}/insumos/Meu_Video.mp4"
        assert run(storage.get(bucket=MIDIA_BUCKET, key=key)).data == b"bytes"


class TestMigration346:
    def test_event_is_written_by_the_trigger_in_the_same_statement(self):
        assert "'insumos_apagados'" in SQL
        assert "OLD.apagado_em IS NULL AND NEW.apagado_em IS NOT NULL" in SQL
        assert "ADD COLUMN IF NOT EXISTS apagado_em" in SQL
        assert "AFTER" not in SQL or "CREATE TRIGGER" not in SQL  # the trigger itself is migration 342's; only the function is replaced
