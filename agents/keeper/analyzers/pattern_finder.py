"""
Pattern Finder — scans products for repeated code patterns.

Identifies code that's duplicated across products and could be
extracted into the seed lib or framework.
"""
import re
from pathlib import Path
from collections import defaultdict

from agents.shared.config import list_products
from agents.shared.repo import read_file, find_files


def find_duplicated_functions(min_lines: int = 5) -> list[dict]:
    """Find functions that appear in multiple products with similar signatures."""
    products = list_products()
    function_map = defaultdict(list)

    for product in products:
        backend = product["path"] / "backend" / "app"
        if not backend.exists():
            continue

        for py_file in find_files(backend, "*.py"):
            content = read_file(py_file)
            if not content:
                continue

            # Extract function definitions with their body length
            lines = content.splitlines()
            i = 0
            while i < len(lines):
                match = re.match(r'^(async )?def (\w+)\(', lines[i].strip())
                if match:
                    func_name = match.group(2)
                    if func_name.startswith("_"):
                        i += 1
                        continue

                    # Count function body lines
                    body_start = i + 1
                    body_end = body_start
                    indent = len(lines[i]) - len(lines[i].lstrip())
                    while body_end < len(lines):
                        line = lines[body_end]
                        if line.strip() and (len(line) - len(line.lstrip())) <= indent:
                            break
                        body_end += 1

                    body_lines = body_end - body_start
                    if body_lines >= min_lines:
                        rel_path = py_file.relative_to(product["path"])
                        function_map[func_name].append({
                            "product": product["name"],
                            "file": str(rel_path),
                            "line": i + 1,
                            "body_lines": body_lines,
                        })
                i += 1

    # Filter to functions that appear in 2+ products
    duplicates = []
    for func_name, locations in function_map.items():
        products_with = set(loc["product"] for loc in locations)
        if len(products_with) >= 2:
            duplicates.append({
                "function": func_name,
                "products": list(products_with),
                "locations": locations,
                "suggestion": f"'{func_name}' appears in {len(products_with)} products — candidate for seed lib extraction",
            })

    return sorted(duplicates, key=lambda d: len(d["products"]), reverse=True)


def find_inline_hooks() -> list[dict]:
    """Find TanStack Query hooks inlined in page components instead of dedicated files."""
    products = list_products()
    issues = []

    for product in products:
        pages_dir = product["path"] / "frontend" / "src" / "pages"
        if not pages_dir.exists():
            continue

        for tsx_file in find_files(pages_dir, "*.tsx"):
            content = read_file(tsx_file)
            if not content:
                continue

            has_useQuery = "useQuery(" in content or "useMutation(" in content
            if has_useQuery:
                issues.append({
                    "product": product["name"],
                    "file": str(tsx_file.relative_to(product["path"])),
                    "issue": "TanStack Query hooks inlined in page — should be in dedicated hook file",
                    "severity": "warning",
                })

    return issues


def find_similar_services() -> list[dict]:
    """Find services across products that have similar method signatures."""
    products = list_products()
    service_methods = defaultdict(list)

    for product in products:
        services_dir = product["path"] / "backend" / "app" / "services"
        if not services_dir.exists():
            continue

        for py_file in find_files(services_dir, "*.py"):
            content = read_file(py_file)
            if not content:
                continue

            for match in re.finditer(r'(async )?def (\w+)\(self.*?\)', content):
                method = match.group(2)
                if not method.startswith("_"):
                    service_methods[method].append({
                        "product": product["name"],
                        "file": str(py_file.relative_to(product["path"])),
                    })

    # Find methods in 3+ products
    patterns = []
    for method, locations in service_methods.items():
        products_with = set(loc["product"] for loc in locations)
        if len(products_with) >= 3:
            patterns.append({
                "method": method,
                "count": len(products_with),
                "products": list(products_with),
                "suggestion": f"Service method '{method}' exists in {len(products_with)} products — potential shared pattern",
            })

    return sorted(patterns, key=lambda p: p["count"], reverse=True)


def run_all() -> dict:
    """Run all pattern analysis."""
    return {
        "duplicated_functions": find_duplicated_functions(),
        "inline_hooks": find_inline_hooks(),
        "similar_services": find_similar_services(),
    }
