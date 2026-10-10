"""The `--paths` help lists the keepers that accept it DERIVED from cli.py's
own AST (paths_aware_keeper_flags), never a hand list (2026-10-10)."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cli  # noqa: E402


def test_derived_flags_cover_known_paths_keepers():
    flags = cli.paths_aware_keeper_flags()
    for known in ("--check-conflict-markers", "--check-git-hooks-bypass",
                  "--check-migration-number-refs-in-tests", "--check-storage-bucket-public"):
        assert known in flags


def test_every_derived_flag_is_a_real_parser_option():
    parser = cli.build_parser()
    options = {s for a in parser._actions for s in a.option_strings}
    flags = cli.paths_aware_keeper_flags()
    assert flags and set(flags) <= options


def test_help_renders_the_derived_list():
    with patch.object(sys, "argv", ["cli.py", "--help"]):
        parser = cli.build_parser()
    help_text = next(a.help for a in parser._actions if "--paths" in a.option_strings)
    assert all(f in help_text for f in cli.paths_aware_keeper_flags())
