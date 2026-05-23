"""parse_drive_url / is_folder_url — pure mappers, no network."""
import pytest

from app.integrations.google_drive import is_folder_url, parse_drive_url


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://drive.google.com/file/d/ABC123def_-/view?usp=sharing", "ABC123def_-"),
        ("https://drive.google.com/drive/folders/FOLDERid123", "FOLDERid123"),
        ("https://drive.google.com/open?id=XYZ7890abcd", "XYZ7890abcd"),
        ("https://drive.google.com/uc?export=download&id=Q1w2e3r4t5", "Q1w2e3r4t5"),
        ("ABCdef123456", "ABCdef123456"),
    ],
)
def test_parse_drive_url(url, expected):
    assert parse_drive_url(url) == expected


def test_parse_drive_url_invalid():
    with pytest.raises(ValueError):
        parse_drive_url("https://example.com/nothing-here")


def test_is_folder_url():
    assert is_folder_url("https://drive.google.com/drive/folders/X")
    assert not is_folder_url("https://drive.google.com/file/d/X/view")
