"""Tests for `app/importer/bundle.py` — JSONL parsing + validation."""
import json

import pytest

from app.importer.bundle import (
    MAX_BUNDLE_BYTES,
    MAX_BUNDLE_LINES,
    BundleInvalid,
    BundleTooLarge,
    SecretDetected,
    parse_bundle_lines,
    path_is_denylisted,
)


def _line(path="KNOWLEDGE-BASE/GERAL/foo.md", content="# Foo\n\nBody.", **overrides):
    row = {
        "path": path,
        "git_sha": "abc123",
        "git_author_raw": "Alguem <alguem@example.com>",
        "git_committed_at": "2026-01-01T10:00:00Z",
        "git_message": "add foo",
        "content": content,
    }
    row.update(overrides)
    return json.dumps(row)


class TestParseHappyPath:
    def test_parses_valid_lines(self):
        raw = "\n".join([_line(path="a.md"), _line(path="b.md")])
        lines = parse_bundle_lines(raw)
        assert len(lines) == 2
        assert lines[0].path == "a.md"
        assert lines[1].path == "b.md"

    def test_blank_lines_are_ignored(self):
        raw = _line(path="a.md") + "\n\n\n" + _line(path="b.md") + "\n"
        lines = parse_bundle_lines(raw)
        assert len(lines) == 2

    def test_accepts_bytes(self):
        raw = _line(path="a.md").encode("utf-8")
        lines = parse_bundle_lines(raw)
        assert len(lines) == 1

    def test_git_committed_at_dt_parses_z_suffix(self):
        lines = parse_bundle_lines(_line(path="a.md", git_committed_at="2026-03-01T12:30:00Z"))
        assert lines[0].git_committed_at_dt.year == 2026
        assert lines[0].git_committed_at_dt.month == 3


class TestShapeValidation:
    def test_invalid_json_raises_bundle_invalid(self):
        with pytest.raises(BundleInvalid):
            parse_bundle_lines("{not json")

    def test_non_object_line_raises_bundle_invalid(self):
        with pytest.raises(BundleInvalid):
            parse_bundle_lines(json.dumps(["a", "b"]))

    def test_missing_field_raises_bundle_invalid(self):
        row = json.loads(_line())
        del row["git_message"]
        with pytest.raises(BundleInvalid):
            parse_bundle_lines(json.dumps(row))

    def test_non_string_field_raises_bundle_invalid(self):
        row = json.loads(_line())
        row["content"] = 12345
        with pytest.raises(BundleInvalid):
            parse_bundle_lines(json.dumps(row))


class TestSizeCap:
    def test_too_many_lines_raises_bundle_too_large(self):
        raw = "\n".join(_line(path=f"f{i}.md") for i in range(MAX_BUNDLE_LINES + 1))
        with pytest.raises(BundleTooLarge):
            parse_bundle_lines(raw)

    def test_exactly_at_line_cap_is_accepted(self):
        raw = "\n".join(_line(path=f"f{i}.md") for i in range(MAX_BUNDLE_LINES))
        lines = parse_bundle_lines(raw)
        assert len(lines) == MAX_BUNDLE_LINES

    def test_too_many_bytes_raises_bundle_too_large(self):
        big_content = "x" * (MAX_BUNDLE_BYTES + 1000)
        raw = _line(path="a.md", content=big_content)
        with pytest.raises(BundleTooLarge):
            parse_bundle_lines(raw)


class TestPathDenylist:
    @pytest.mark.parametrize(
        "path",
        [
            ".env",
            ".env.production",
            "config/.env.local",
            "app/id_rsa",
            "app/id_rsa.pub",
            "keys/server.pem",
            "keys/server.key",
            "secrets/foo.txt",
            "app/some-secret-file.md",
            "credentials.json",
            "app/credentials-backup.json",
            ".npmrc",
        ],
    )
    def test_denylisted_paths_detected(self, path):
        assert path_is_denylisted(path) is True

    @pytest.mark.parametrize(
        "path",
        [
            "KNOWLEDGE-BASE/GERAL/foo.md",
            "docs/SPEC.md",
            "projects/state/tasks.json",
            "KNOWLEDGE-BASE/DECISOES/0001-decisoes.md",
        ],
    )
    def test_ordinary_paths_not_denylisted(self, path):
        assert path_is_denylisted(path) is False

    def test_denylisted_path_raises_secret_detected(self):
        raw = _line(path=".env.production", content="ok")
        with pytest.raises(SecretDetected) as exc_info:
            parse_bundle_lines(raw)
        assert exc_info.value.path == ".env.production"


class TestContentSecretScan:
    def test_secret_in_content_raises_secret_detected(self):
        raw = _line(
            path="KNOWLEDGE-BASE/GERAL/foo.md",
            content="ghp_1234567890abcdefghijklmnopqrstuvwx",
        )
        with pytest.raises(SecretDetected) as exc_info:
            parse_bundle_lines(raw)
        assert exc_info.value.path == "KNOWLEDGE-BASE/GERAL/foo.md"

    def test_ordinary_content_is_accepted(self):
        raw = _line(content="# Foo\n\nConteudo normal em portugues, nada suspeito.")
        lines = parse_bundle_lines(raw)
        assert len(lines) == 1
