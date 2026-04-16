"""Repo analysis utilities shared by Guardian and Lab agents."""
import os
import re
import subprocess
from pathlib import Path
from typing import Optional

from agents.shared.config import REPO_ROOT, PRODUCTS_DIR


def read_file(path: Path) -> Optional[str]:
    """Read a file and return its contents. Returns None if file doesn't exist."""
    try:
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, UnicodeDecodeError):
        return None


def find_imports(file_path: Path) -> list[str]:
    """Extract import statements from a Python file."""
    content = read_file(file_path)
    if not content:
        return []
    imports = []
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("import ") or line.startswith("from "):
            imports.append(line)
    return imports


def find_ts_imports(file_path: Path) -> list[str]:
    """Extract import statements from a TypeScript/TSX file."""
    content = read_file(file_path)
    if not content:
        return []
    pattern = re.compile(r'import\s+.*?from\s+["\']([^"\']+)["\']')
    return pattern.findall(content)


def get_product_structure(product_path: Path) -> dict:
    """Map a product's file tree."""
    structure = {"backend": {}, "frontend": {}}

    backend = product_path / "backend" / "app"
    if backend.exists():
        structure["backend"]["routers"] = [
            f.stem for f in (backend / "routers").glob("*.py")
            if f.stem != "__init__" and not f.stem.startswith("__")
        ] if (backend / "routers").exists() else []
        structure["backend"]["services"] = [
            f.stem for f in (backend / "services").glob("*.py")
            if f.stem != "__init__" and not f.stem.startswith("__")
        ] if (backend / "services").exists() else []
        structure["backend"]["schemas"] = [
            f.stem for f in (backend / "schemas").glob("*.py")
            if f.stem != "__init__" and not f.stem.startswith("__")
        ] if (backend / "schemas").exists() else []

    frontend = product_path / "frontend" / "src"
    if frontend.exists():
        structure["frontend"]["pages"] = [
            f.stem for f in (frontend / "pages").glob("*.tsx")
        ] if (frontend / "pages").exists() else []
        structure["frontend"]["hooks"] = [
            f.stem for f in (frontend / "hooks").glob("*.ts")
        ] if (frontend / "hooks").exists() else []

    return structure


def run_tests(product_path: Path, timeout: int = 60) -> dict:
    """Run pytest for a product backend. Returns {passed, failed, errors, output}."""
    backend = product_path / "backend"
    if not (backend / "tests").exists():
        return {"passed": 0, "failed": 0, "errors": 0, "output": "no tests directory"}

    try:
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/", "-q", "--tb=no"],
            cwd=str(backend),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout + result.stderr

        passed = failed = errors = 0
        for line in output.splitlines():
            if "passed" in line:
                match = re.search(r"(\d+) passed", line)
                if match:
                    passed = int(match.group(1))
            if "failed" in line:
                match = re.search(r"(\d+) failed", line)
                if match:
                    failed = int(match.group(1))
            if "error" in line:
                match = re.search(r"(\d+) error", line)
                if match:
                    errors = int(match.group(1))

        return {"passed": passed, "failed": failed, "errors": errors, "output": output.strip()}
    except subprocess.TimeoutExpired:
        return {"passed": 0, "failed": 0, "errors": 1, "output": "timeout"}
    except Exception as e:
        return {"passed": 0, "failed": 0, "errors": 1, "output": str(e)}


def count_lines(file_path: Path) -> int:
    """Count lines in a file."""
    content = read_file(file_path)
    return len(content.splitlines()) if content else 0


def find_files(directory: Path, pattern: str) -> list[Path]:
    """Find files matching a glob pattern, excluding node_modules, __pycache__, .backup."""
    results = []
    for f in directory.rglob(pattern):
        parts = str(f)
        if "node_modules" in parts or "__pycache__" in parts or ".backup" in parts:
            continue
        results.append(f)
    return sorted(results)
