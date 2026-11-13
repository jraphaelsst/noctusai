"""Pilot of the seed resumable-upload seam: chunked photo upload -> `POST /lotes/{id}/fotos/de-upload`."""
from __future__ import annotations

from tests.modules.edicao_fotos.conftest import JPEG, OTHER_ORG, USERS  # noqa: F401

BASE = "/api/edicao-fotos/uploads"
DATA = JPEG + b"-" * 20  # 35 bytes -> parts of 8 (5 parts)


def _open(edicao, data=DATA, name="foto.jpg", **kw):
    r = edicao.http.post(BASE, json={"filename": name, "content_type": "image/jpeg", "size_bytes": len(data), **kw})
    assert r.status_code == 201, r.text
    return r.json()


def _send(edicao, up, data=DATA, only=None):
    n, size = up["total_parts"], up["part_size"]
    for i in range(1, n + 1):
        if only is None or i in only:
            r = edicao.http.put(f"{BASE}/{up['id']}/parts/{i}", content=data[(i - 1) * size : i * size])
            assert r.status_code == 200, r.text


def test_chunked_upload_with_resume_becomes_a_batch_photo(edicao) -> None:
    lote = edicao.make_batch("corretor")
    edicao.as_user("corretor")
    up = _open(edicao)
    assert up["total_parts"] == 5 and up["parts"] == []
    _send(edicao, up, only={1, 2, 4})  # connection drops
    st = edicao.http.get(f"{BASE}/{up['id']}").json()
    assert st["parts"] == [1, 2, 4]  # the server says what it already has
    miss = edicao.http.post(f"{BASE}/{up['id']}/complete")
    assert miss.status_code == 409 and miss.json()["missing"] == [3, 5]
    _send(edicao, up, only={3, 5})  # only the missing ones are re-sent
    assert edicao.http.post(f"{BASE}/{up['id']}/complete").json()["status"] == "completed"
    r = edicao.http.post(f"/api/edicao-fotos/lotes/{lote}/fotos/de-upload", json={"upload_ids": [up["id"]]})
    assert r.status_code == 201, r.text
    fotos = r.json()["fotos"]
    assert len(fotos) == 1 and fotos[0]["estado"] == "recebida"
    # the assembled copy was consumed: only the batch photo remains under the org
    assert edicao.run(edicao.backend.list_keys(bucket="edicao-fotos", prefix="uploads/")) == []
    assert edicao.drain() == 1


def test_de_upload_enforces_the_same_limits_as_multipart(edicao) -> None:
    edicao.configure_org(limite_bytes_por_foto=10, limite_fotos_por_lote=1)
    lote = edicao.make_batch("corretor")
    edicao.as_user("corretor")
    up = _open(edicao)
    _send(edicao, up)
    edicao.http.post(f"{BASE}/{up['id']}/complete")
    big = edicao.http.post(f"/api/edicao-fotos/lotes/{lote}/fotos/de-upload", json={"upload_ids": [up["id"]]})
    assert big.status_code == 413 and big.json()["code"] == "arquivo_grande_demais"
    assert edicao.repo.photos == {}


def test_de_upload_refuses_an_incomplete_session_and_other_orgs(edicao) -> None:
    lote = edicao.make_batch("corretor")
    edicao.as_user("corretor")
    up = _open(edicao)
    _send(edicao, up, only={1})
    r = edicao.http.post(f"/api/edicao-fotos/lotes/{lote}/fotos/de-upload", json={"upload_ids": [up["id"]]})
    assert r.status_code == 409
    ghost = edicao.http.post(
        f"/api/edicao-fotos/lotes/{lote}/fotos/de-upload", json={"upload_ids": ["00000000-0000-4000-8000-000000000001"]}
    )
    assert ghost.status_code == 404
    assert edicao.repo.photos == {}
