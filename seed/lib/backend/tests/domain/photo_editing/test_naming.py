from __future__ import annotations

import pytest

from noctusai_lib.domain.photo_editing.naming import (
    STAGING_SUFFIX,
    storage_path,
    upload_path,
    zip_entry_name,
    zip_file_name,
    zip_number_width,
)
from noctusai_lib.domain.photo_editing.types import EditType


def test_two_digits_up_to_99_three_above() -> None:
    assert zip_number_width(99) == 2
    assert zip_number_width(100) == 3
    assert zip_entry_name(7, total_photos=99, tipos=[EditType.CEU]) == "07.jpg"
    assert zip_entry_name(7, total_photos=100, tipos=[]) == "007.jpg"
    assert zip_entry_name(100, total_photos=100, tipos=[]) == "100.jpg"


def test_staging_suffix() -> None:
    assert STAGING_SUFFIX == "_imagem-gerada-com-ia"
    name = zip_entry_name(3, total_photos=5, tipos=[EditType.COR_LUZ, EditType.STAGING_VIRTUAL])
    assert name == "03_imagem-gerada-com-ia.jpg"


@pytest.mark.parametrize("ordem,total", [(0, 5), (6, 5)])
def test_ordem_bounds(ordem, total) -> None:
    with pytest.raises(ValueError):
        zip_entry_name(ordem, total_photos=total, tipos=[])


def test_storage_path_layout_starts_with_org() -> None:
    assert storage_path("o", "l", "f", "original.jpg") == "o/l/f/original.jpg"
    assert upload_path("o", "l", "t", ".HEIC") == "o/l/t/upload.heic"
    for bad in ("", "a/b", "..", "."):
        with pytest.raises(ValueError):
            storage_path("o", bad, "f", "x")
    with pytest.raises(ValueError):
        upload_path("o", "l", "t", "jp/g")


def test_zip_file_name_is_safe() -> None:
    assert zip_file_name('Casa 1/2: "vista"') == "Casa 1-2- -vista-.zip"
    assert zip_file_name("  ") == "lote.zip"
