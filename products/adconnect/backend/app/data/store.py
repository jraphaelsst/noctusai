from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_DATA_DIR = Path(__file__).parent


def _load(name: str) -> Any:
    with open(_DATA_DIR / name, "r", encoding="utf-8") as f:
        return json.load(f)


class Store:
    def __init__(self) -> None:
        self.products: list[dict[str, Any]] = _load("products.json")
        self.categories: list[dict[str, Any]] = _load("categories.json")
        self.distributors: list[dict[str, Any]] = _load("distributors.json")
        self.reward_rules: list[dict[str, Any]] = _load("reward-rules.json")
        self.promos: list[dict[str, Any]] = _load("promos.json")
        self.rewards_history: list[dict[str, Any]] = _load("rewards-history.json")
        self.sellout_reports: list[dict[str, Any]] = _load("sellout-reports.json")
        self.invoices: list[dict[str, Any]] = _load("invoices.json")
        self.orders: list[dict[str, Any]] = []
        self.users: list[dict[str, Any]] = []


store = Store()
