"""Tests for product scaffolding."""
import sys
import shutil
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.scaffold import list_available_ports, scaffold_product

REPO_ROOT = Path(__file__).resolve().parents[3]


class TestAvailablePorts:
    def test_returns_ports(self):
        ports = list_available_ports()
        assert "next_backend_port" in ports
        assert "next_frontend_port" in ports
        assert ports["next_backend_port"] > 8006
        assert ports["next_frontend_port"] > 8120

    def test_used_ports_include_known(self):
        ports = list_available_ports()
        assert 8000 in ports["used_backend"]  # Core
        assert 8006 in ports["used_backend"]  # Mailing


class TestScaffold:
    def test_refuses_existing_product(self):
        result = scaffold_product("Seed", "seed", "seed", 8099, 8199)
        assert "error" in result
        assert "already exists" in result["error"]

    def test_creates_new_product(self):
        target = REPO_ROOT / "products" / "test-scaffold-temp"
        try:
            result = scaffold_product("Test Product", "test-scaffold-temp", "test_schema", 8099, 8199, "Zap")
            assert result["created"] is True
            assert result["files_processed"] > 0
            assert (target / "backend" / "app" / "main.py").exists()
            assert (target / "frontend" / "src" / "App.tsx").exists()
            assert "next_steps" in result
        finally:
            if target.exists():
                shutil.rmtree(target)
