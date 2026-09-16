from __future__ import annotations

import io
import zipfile

import pytest

from noctusai_lib.domain.photo_editing.types import (
    Decision,
    EditType,
    Photo,
    PhotoStatus,
    ReviewDecision,
)
from noctusai_lib.domain.photo_editing.zipper import (
    BatchNotDecidedError,
    NothingApprovedError,
    build_zip,
    plan_zip,
)


def photo(n: int, status=PhotoStatus.AGUARDANDO_DECISAO, edited=True) -> Photo:
    return Photo(
        id=f"f{n}", org_id="o", lote_id="l", ordem=n, storage_path_original=f"o/l/f{n}/original.jpg",
        storage_path_editada=f"o/l/f{n}/editada.jpg" if edited else None, status=status,
    )


def decision(n: int, d: Decision) -> ReviewDecision:
    return ReviewDecision(id=f"d{n}", org_id="o", lote_id="l", foto_id=f"f{n}", decisao=d,
                          decidido_por="u", comentario="x" if d is Decision.REJEITAR else None)


def test_undecided_photo_blocks_with_409_code() -> None:
    with pytest.raises(BatchNotDecidedError) as exc:
        plan_zip([photo(1), photo(2)], {"f1": decision(1, Decision.APROVAR)}, {})
    assert exc.value.pending_ids == ["f2"] and exc.value.code == "lote_nao_decidido"


def test_failed_photos_never_block_and_are_excluded() -> None:
    photos = [photo(1), photo(2, PhotoStatus.FALHOU, edited=False), photo(3)]
    decisions = {"f1": decision(1, Decision.APROVAR), "f3": decision(3, Decision.REJEITAR)}
    entries = plan_zip(photos, decisions, {"f1": (EditType.STAGING_VIRTUAL,)})
    assert [(e.name, e.foto_id) for e in entries] == [("01_imagem-gerada-com-ia.jpg", "f1")]


def test_nothing_approved() -> None:
    with pytest.raises(NothingApprovedError):
        plan_zip([photo(1)], {"f1": decision(1, Decision.REJEITAR)}, {})


def test_build_zip_is_deterministic_and_rejects_duplicates() -> None:
    files = [("01.jpg", b"a"), ("02.jpg", b"bb")]
    assert build_zip(files) == build_zip(files)
    with zipfile.ZipFile(io.BytesIO(build_zip(files))) as zf:
        assert zf.namelist() == ["01.jpg", "02.jpg"]
        assert zf.read("02.jpg") == b"bb"
    with pytest.raises(ValueError):
        build_zip([("a", b""), ("a", b"")])
