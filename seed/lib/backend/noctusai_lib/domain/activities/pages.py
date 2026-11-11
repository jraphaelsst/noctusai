"""Page keys the activities organ offers a module (mirrors FE `ACTIVITIES_PAGES`; the manifest parity test pins both).

The card-hub TAB (`ActivitiesPanel`) is not a page: it lives inside the card hub and needs no key. `MyTasks` is the page.
A module spreads these into its `ModuleSpec.pages` (`PageSpec(**p)`), so a market mounts the organ without re-declaring keys.
"""
from __future__ import annotations

from typing import Final

ACTIVITIES_PAGES: Final[tuple[dict[str, str], ...]] = (
    {"key": "crm_atividades", "path": "/crm/atividades", "label": "Atividades"},
)

__all__ = ["ACTIVITIES_PAGES"]
