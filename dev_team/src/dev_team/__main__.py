"""``python -m dev_team`` entrypoint — delegates to :mod:`dev_team.cli`."""

from __future__ import annotations

from dev_team.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
