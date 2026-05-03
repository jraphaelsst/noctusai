"""Tests for the TypeScript / TSX outline tool."""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev import outline_typescript as ot


def write(tmp_path: Path, name: str, body: str) -> Path:
    f = tmp_path / name
    f.write_text(textwrap.dedent(body).lstrip("\n"), encoding="utf-8")
    return f


class TestMissingFile:
    def test_returns_parse_error(self, tmp_path):
        result = ot.outline_typescript(str(tmp_path / "nope.ts"))
        assert result.parse_error is not None
        assert "not found" in result.parse_error
        assert result.symbol_count == 0


class TestTopLevelDeclarations:
    def test_function_declaration(self, tmp_path):
        f = write(tmp_path, "m.ts", """
            export function greet(name: string): string {
              return `hi ${name}`;
            }
        """)
        result = ot.outline_typescript(str(f))
        assert len(result.functions) == 1
        assert result.functions[0].name == "greet"
        assert result.functions[0].kind == "function"

    def test_async_function(self, tmp_path):
        f = write(tmp_path, "m.ts", """
            export async function fetchUser() {
              return null;
            }
        """)
        result = ot.outline_typescript(str(f))
        assert result.functions[0].kind == "async_function"

    def test_default_export_function(self, tmp_path):
        f = write(tmp_path, "m.ts", """
            export default function App() {
              return null;
            }
        """)
        result = ot.outline_typescript(str(f))
        assert len(result.functions) == 1
        assert result.functions[0].name == "App"

    def test_arrow_function_const_captured_as_function(self, tmp_path):
        f = write(tmp_path, "m.ts", """
            export const useCounter = () => {
              return 1;
            };
        """)
        result = ot.outline_typescript(str(f))
        assert len(result.functions) == 1
        assert result.functions[0].name == "useCounter"

    def test_arrow_with_typed_props(self, tmp_path):
        f = write(tmp_path, "m.tsx", """
            export const Card = ({ title }: { title: string }) => {
              return <div>{title}</div>;
            };
        """)
        result = ot.outline_typescript(str(f))
        assert len(result.functions) == 1
        assert result.functions[0].name == "Card"

    def test_async_arrow_function(self, tmp_path):
        f = write(tmp_path, "m.ts", """
            export const fetchData = async () => {
              return await fetch('/api');
            };
        """)
        result = ot.outline_typescript(str(f))
        assert len(result.functions) == 1
        assert result.functions[0].kind == "async_function"


class TestClassesAndMethods:
    def test_class_with_methods(self, tmp_path):
        f = write(tmp_path, "m.ts", """
            export class Greeter {
              private name: string;

              constructor(name: string) {
                this.name = name;
              }

              greet(): string {
                return `hi ${this.name}`;
              }

              async greetAsync(): Promise<string> {
                return `hi ${this.name}`;
              }
            }
        """)
        result = ot.outline_typescript(str(f))
        assert len(result.classes) == 1
        cls = result.classes[0]
        assert cls.name == "Greeter"
        assert cls.kind == "class"
        names = [m.name for m in result.methods]
        assert "constructor" in names
        assert "greet" in names
        assert "greetAsync" in names
        assert all(m.parent == "Greeter" for m in result.methods)
        async_method = next(m for m in result.methods if m.name == "greetAsync")
        assert async_method.kind == "async_method"

    def test_method_does_not_collide_with_control_flow(self, tmp_path):
        """The method regex shouldn't fire on `if (...)`, `for (...)`, etc."""
        f = write(tmp_path, "m.ts", """
            export class C {
              method(): void {
                if (true) {
                  return;
                }
                for (const x of [1, 2]) {
                  console.log(x);
                }
              }
            }
        """)
        result = ot.outline_typescript(str(f))
        names = [m.name for m in result.methods]
        assert "method" in names
        assert "if" not in names
        assert "for" not in names


class TestInterfacesAndTypes:
    def test_interface_captured(self, tmp_path):
        f = write(tmp_path, "m.ts", """
            export interface User {
              id: string;
              name: string;
            }
        """)
        result = ot.outline_typescript(str(f))
        # Interfaces fold into classes bucket with kind="interface"
        assert any(c.name == "User" and c.kind == "interface" for c in result.classes)

    def test_type_alias_captured(self, tmp_path):
        f = write(tmp_path, "m.ts", """
            export type UserId = string;
            export type Status = 'active' | 'inactive';
        """)
        result = ot.outline_typescript(str(f))
        type_names = [c.name for c in result.classes if c.kind == "type"]
        assert "UserId" in type_names
        assert "Status" in type_names

    def test_generic_type_alias(self, tmp_path):
        f = write(tmp_path, "m.ts", """
            export type Maybe<T> = T | null;
        """)
        result = ot.outline_typescript(str(f))
        assert any(c.name == "Maybe" and c.kind == "type" for c in result.classes)


class TestConstants:
    def test_uppercase_const_captured_as_constant(self, tmp_path):
        f = write(tmp_path, "m.ts", """
            export const DEFAULT_TIMEOUT = 5000;
            export const MAX_RETRIES = 3;
        """)
        result = ot.outline_typescript(str(f))
        names = [c.name for c in result.constants]
        assert "DEFAULT_TIMEOUT" in names
        assert "MAX_RETRIES" in names

    def test_mixed_case_data_const_also_captured(self, tmp_path):
        """Non-functional, non-uppercase consts are still useful symbols."""
        f = write(tmp_path, "m.ts", """
            export const config = { url: 'https://example.com' };
        """)
        result = ot.outline_typescript(str(f))
        # Mixed-case data const → still captured as constant (not a function)
        assert any(c.name == "config" for c in result.constants)


class TestImports:
    def test_named_import(self, tmp_path):
        f = write(tmp_path, "m.ts", """
            import { useState } from 'react';
        """)
        result = ot.outline_typescript(str(f))
        assert len(result.imports) == 1
        assert "useState" in result.imports[0].name

    def test_default_import(self, tmp_path):
        f = write(tmp_path, "m.ts", """
            import React from 'react';
        """)
        result = ot.outline_typescript(str(f))
        assert len(result.imports) == 1
        assert "React" in result.imports[0].name

    def test_multiline_import_collapsed_to_one_line(self, tmp_path):
        f = write(tmp_path, "m.ts", """
            import {
              useState,
              useEffect,
              useMemo,
            } from 'react';
        """)
        result = ot.outline_typescript(str(f))
        assert len(result.imports) == 1
        # Multi-line collapsed to one line for display
        assert "\n" not in result.imports[0].name
        assert "useState" in result.imports[0].name
        assert "useEffect" in result.imports[0].name
        assert "from 'react'" in result.imports[0].name


class TestCommentHandling:
    def test_block_comment_with_function_keyword_does_not_match(self, tmp_path):
        """`/* function foo() */` inside a comment should NOT register as a top-level fn."""
        f = write(tmp_path, "m.ts", """
            /* This is a block comment that mentions function fakeFn() */
            export function realFn() {
              return 1;
            }
        """)
        result = ot.outline_typescript(str(f))
        names = [f.name for f in result.functions]
        assert "realFn" in names
        assert "fakeFn" not in names

    def test_line_comment_with_function_keyword_does_not_match(self, tmp_path):
        f = write(tmp_path, "m.ts", """
            // function fakeLine() — never declared
            export function realFn() {
              return 1;
            }
        """)
        result = ot.outline_typescript(str(f))
        names = [f.name for f in result.functions]
        assert "realFn" in names
        assert "fakeLine" not in names


class TestSymbolCountAndSerialization:
    def test_aggregate_count(self, tmp_path):
        f = write(tmp_path, "m.ts", """
            import { x } from 'y';

            export const DEFAULT = 1;

            export function f() {
              return 1;
            }

            export class C {
              m(): void {}
            }

            export interface I {
              field: string;
            }

            export type T = string;
        """)
        result = ot.outline_typescript(str(f))
        # symbol_count = classes(+ types/interfaces) + functions + methods + constants
        assert result.symbol_count >= 5
        assert len(result.imports) == 1

    def test_to_dict_round_trip(self, tmp_path):
        f = write(tmp_path, "m.ts", """
            export function f() {
              return 1;
            }
        """)
        result = ot.outline_typescript(str(f))
        d = result.to_dict()
        assert d["path"]
        assert d["parse_error"] is None
        assert d["functions"][0]["name"] == "f"
        # schema_version is shared with outline_python (same dataclass);
        # outline_typescript reuses OutlineResult so the contract version
        # must come through unchanged.
        assert result.schema_version == 1
        assert d["schema_version"] == 1


class TestRealWorldFile:
    def test_outlines_an_actual_repo_tsx(self):
        """Smoke test on a real repo TSX file (the Vista showcase page)."""
        repo_root = Path(__file__).resolve().parents[3]
        target = repo_root / "products" / "erp-imobiliario" / "frontend" / "src" / "pages" / "VistaShowcase.tsx"
        if not target.exists():
            pytest.skip("Vista showcase TSX not present in this checkout")
        result = ot.outline_typescript(str(target))
        assert result.parse_error is None
        # Has at least one function (the page component) + imports
        assert len(result.functions) > 0
        assert len(result.imports) > 0

    def test_outlines_an_actual_repo_ts_hook(self):
        """Smoke test on a real repo TS hooks file."""
        repo_root = Path(__file__).resolve().parents[3]
        target = repo_root / "products" / "erp-imobiliario" / "frontend" / "src" / "hooks" / "useVistaShowcase.ts"
        if not target.exists():
            pytest.skip("Vista showcase hook not present in this checkout")
        result = ot.outline_typescript(str(target))
        assert result.parse_error is None
        # Should find the useVista* hooks as functions and the interfaces as classes-bucket entries
        function_names = {f.name for f in result.functions}
        assert "useVistaImoveis" in function_names
        assert "useVistaTabs" in function_names
        interface_names = {c.name for c in result.classes if c.kind == "interface"}
        assert "VistaShowcaseImovel" in interface_names
