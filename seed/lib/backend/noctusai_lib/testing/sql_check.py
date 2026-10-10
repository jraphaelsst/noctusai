"""
Translate a migration's SQL `CHECK (...)` expression into a Python predicate
the mock can enforce on a row.

WHY (2026-10-10). `MockSupabaseClient` already learns every table's COLUMNS
from the migrations (`_schema_cache`), so a write naming a column the real
table lacks fails in the test, not in production. CHECK constraints had no
such path: the single-column `CheckManifest` and the `_por_origem`-shaped
`ConditionalPresenceManifest` are opt-in and hand-written, and a cross-column
CHECK (`ends_at > starts_at`, `pct_a + pct_b + pct_c = 100`,
`num_nonnulls(lead_id, meta_ads_lead_id) = 1`) fit neither. 75 of the 92 such
CHECKs in active products were mirrored nowhere, so the suite stayed green on
a write the real INSERT refuses (the `atendimento_contrato_versoes` class,
2026-09-22). Deriving the predicate FROM the migration means there is no
mirror to keep in sync, and a new migration is enforced the day it lands.

SCOPE. The SQL subset the corpus actually uses: AND / OR / NOT, comparisons,
`IS [NOT] NULL`, `IS [NOT] TRUE|FALSE`, `IS [NOT] DISTINCT FROM`, `[NOT] IN`,
`[NOT] BETWEEN`, `+ - * / % ||`, casts (`::type`), parentheses, literals
(incl. `E'...'`), `ARRAY[...]`, array containment (`<@` / `@>`), regex match
against a literal pattern (`~ ~* !~ !~*`, refusing POSIX-only syntax), and
the functions in `_FUNCTIONS`. Anything else — subqueries, `CASE`, `LIKE`,
a user-defined SQL function — raises
`UnsupportedCheck` at COMPILE time: the caller reports it as untranslatable
(`stand_in_conformance` leg B(iv)), it is never silently treated as passing.

SEMANTICS. Postgres three-valued logic: a CHECK passes unless it evaluates to
FALSE (NULL passes). Where the mock cannot judge a value faithfully — a
column the row doesn't carry, incomparable types, a timezone-aware vs naive
timestamp — the result is UNKNOWN (`None`), i.e. passes: the mock may miss a
violation, but it never fails a test on a guess.
"""
from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Mapping, Optional


class UnsupportedCheck(ValueError):
    """The CHECK uses SQL this translator does not model."""


class _Unknown(Exception):
    """Raised mid-evaluation when a value can't be judged faithfully."""


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(
    r"""
    (?P<ws>\s+)
  | (?P<estr>[Ee]'(?:[^'\\]|\\.|'')*')
  | (?P<str>'(?:[^']|'')*')
  | (?P<num>\d+(?:\.\d+)?)
  | (?P<qident>"[^"]+")
  | (?P<ident>[A-Za-z_][A-Za-z0-9_$]*)
  | (?P<op><@|@>|!~\*|!~|~\*|<=|>=|<>|!=|::|\|\||[=<>+\-*/%(),.\[\]~!])
    """,
    re.VERBOSE,
)

_E_ESCAPES = {"t": "\t", "n": "\n", "r": "\r", "b": "\b", "f": "\f", "\\": "\\", "'": "'"}


def _tokenize(text: str) -> list[tuple[str, Any]]:
    tokens: list[tuple[str, Any]] = []
    pos = 0
    while pos < len(text):
        m = _TOKEN_RE.match(text, pos)
        if not m:
            raise UnsupportedCheck(f"unexpected character {text[pos]!r} at {pos}")
        pos = m.end()
        kind = m.lastgroup
        value = m.group(kind)
        if kind == "ws":
            continue
        if kind == "str":
            tokens.append(("lit", value[1:-1].replace("''", "'")))
        elif kind == "estr":
            body = value[2:-1].replace("''", "'")
            tokens.append(("lit", re.sub(r"\\(.)", lambda e: _E_ESCAPES.get(e.group(1), e.group(1)), body)))
        elif kind == "num":
            tokens.append(("lit", Decimal(value) if "." in value else int(value)))
        elif kind == "qident":
            tokens.append(("ident", value[1:-1]))
        elif kind == "ident":
            tokens.append(("ident", value))
        else:
            tokens.append(("op", value))
    tokens.append(("eof", None))
    return tokens


# ---------------------------------------------------------------------------
# Parser — precedence climbing into a tuple AST
# ---------------------------------------------------------------------------

_COMPARISONS = {"=", "<>", "!=", "<", "<=", ">", ">="}
_REGEX_OPS = {"~": (False, False), "~*": (True, False), "!~": (False, True), "!~*": (True, True)}
_CONTAINMENT_OPS = {"<@", "@>"}
#: POSIX regex features whose Python `re` meaning differs — refuse, don't guess.
_POSIX_ONLY_RE = re.compile(r"\[\[:|\\[mMyY]|\(\?[^:=!]")
_RESERVED = {
    "and", "or", "not", "is", "null", "true", "false", "in", "between",
    "distinct", "from", "like", "ilike", "similar", "case", "when", "then",
    "else", "end", "select", "exists", "any", "all", "array", "some",
}


class _Parser:
    def __init__(self, text: str):
        self.tokens = _tokenize(text)
        self.i = 0
        self.columns: set[str] = set()

    # -- token helpers --
    def peek(self, offset: int = 0):
        return self.tokens[self.i + offset]

    def kw(self, word: str, offset: int = 0) -> bool:
        kind, value = self.peek(offset)
        return kind == "ident" and value.lower() == word

    def op(self, symbol: str) -> bool:
        kind, value = self.peek()
        return kind == "op" and value == symbol

    def take(self):
        tok = self.tokens[self.i]
        self.i += 1
        return tok

    def expect_op(self, symbol: str) -> None:
        if not self.op(symbol):
            raise UnsupportedCheck(f"expected {symbol!r}, found {self.peek()[1]!r}")
        self.take()

    def expect_kw(self, word: str) -> None:
        if not self.kw(word):
            raise UnsupportedCheck(f"expected {word.upper()}, found {self.peek()[1]!r}")
        self.take()

    # -- grammar --
    def parse(self):
        node = self.or_expr()
        if self.peek()[0] != "eof":
            raise UnsupportedCheck(f"unexpected trailing {self.peek()[1]!r}")
        return node

    def or_expr(self):
        node = self.and_expr()
        while self.kw("or"):
            self.take()
            node = ("or", node, self.and_expr())
        return node

    def and_expr(self):
        node = self.not_expr()
        while self.kw("and"):
            self.take()
            node = ("and", node, self.not_expr())
        return node

    def not_expr(self):
        if self.kw("not"):
            self.take()
            return ("not", self.not_expr())
        return self.predicate()

    def predicate(self):
        left = self.additive()
        while True:
            kind, value = self.peek()
            if kind == "op" and value in _COMPARISONS:
                self.take()
                left = ("cmp", "<>" if value == "!=" else value, left, self.additive())
                continue
            if self.kw("is"):
                self.take()
                negate = False
                if self.kw("not"):
                    self.take()
                    negate = True
                if self.kw("null"):
                    self.take()
                    left = ("isnull", left, negate)
                elif self.kw("true") or self.kw("false"):
                    truth = self.take()[1].lower() == "true"
                    left = ("istruth", left, truth, negate)
                elif self.kw("distinct"):
                    self.take()
                    self.expect_kw("from")
                    left = ("distinct", left, self.additive(), negate)
                else:
                    raise UnsupportedCheck(f"unsupported IS form near {self.peek()[1]!r}")
                continue
            negate = False
            if self.kw("not") and (self.kw("in", 1) or self.kw("between", 1)):
                self.take()
                negate = True
            if self.kw("in"):
                self.take()
                self.expect_op("(")
                if self.kw("select"):
                    raise UnsupportedCheck("subquery in IN (...)")
                items = [self.additive()]
                while self.op(","):
                    self.take()
                    items.append(self.additive())
                self.expect_op(")")
                left = ("in", left, items, negate)
                continue
            if self.kw("between"):
                self.take()
                low = self.additive()
                self.expect_kw("and")
                high = self.additive()
                left = ("between", left, low, high, negate)
                continue
            if kind == "op" and value in _REGEX_OPS:
                self.take()
                pattern = self.additive()
                if pattern[0] != "lit" or not isinstance(pattern[1], str):
                    raise UnsupportedCheck("regex operand must be a string literal")
                if _POSIX_ONLY_RE.search(pattern[1]):
                    raise UnsupportedCheck(f"POSIX-only regex syntax in {pattern[1]!r}")
                insensitive, negate_re = _REGEX_OPS[value]
                try:
                    compiled = re.compile(pattern[1], re.IGNORECASE if insensitive else 0)
                except re.error as exc:
                    raise UnsupportedCheck(f"regex {pattern[1]!r}: {exc}") from exc
                left = ("regex", left, compiled, negate_re)
                continue
            if kind == "op" and value in _CONTAINMENT_OPS:
                self.take()
                left = ("contains", value, left, self.additive())
                continue
            if self.kw("like") or self.kw("ilike") or self.kw("similar"):
                raise UnsupportedCheck("LIKE / SIMILAR TO is not modelled")
            return left

    def additive(self):
        node = self.multiplicative()
        while self.op("+") or self.op("-") or self.op("||"):
            symbol = self.take()[1]
            node = ("arith", symbol, node, self.multiplicative())
        return node

    def multiplicative(self):
        node = self.unary()
        while self.op("*") or self.op("/") or self.op("%"):
            symbol = self.take()[1]
            node = ("arith", symbol, node, self.unary())
        return node

    def unary(self):
        if self.op("-"):
            self.take()
            return ("neg", self.unary())
        if self.op("+"):
            self.take()
            return self.unary()
        return self.postfix()

    def postfix(self):
        node = self.primary()
        while self.op("::"):
            self.take()
            node = ("cast", node, self.type_name())
        return node

    def type_name(self) -> str:
        kind, value = self.take()
        if kind != "ident":
            raise UnsupportedCheck(f"expected a type after '::', found {value!r}")
        name = value.lower()
        if name == "double" and self.kw("precision"):
            self.take()
            name = "double precision"
        if self.op("("):  # varchar(20), numeric(12,2)
            self.take()
            while not self.op(")"):
                if self.peek()[0] == "eof":
                    raise UnsupportedCheck("unterminated type modifier")
                self.take()
            self.take()
        if self.op("["):
            self.take()
            self.expect_op("]")
            name += "[]"
        return name

    def primary(self):
        kind, value = self.peek()
        if kind == "lit":
            self.take()
            return ("lit", value)
        if kind == "op" and value == "(":
            self.take()
            if self.kw("select"):
                raise UnsupportedCheck("subquery")
            node = self.or_expr()
            self.expect_op(")")
            return node
        if kind == "ident":
            low = value.lower()
            if low == "null":
                self.take()
                return ("lit", None)
            if low in ("true", "false"):
                self.take()
                return ("lit", low == "true")
            if low == "array" and self.peek(1) == ("op", "["):
                self.take()
                self.take()
                items = [] if self.op("]") else [self.additive()]
                while self.op(","):
                    self.take()
                    items.append(self.additive())
                self.expect_op("]")
                return ("array", items)
            if low in _RESERVED:
                raise UnsupportedCheck(f"unsupported construct {value.upper()}")
            self.take()
            if self.op("("):
                return self.call(low)
            if self.op("."):  # qualified column `t.col` → `col`
                self.take()
                kind2, col = self.take()
                if kind2 != "ident":
                    raise UnsupportedCheck("bad qualified name")
                if self.op("("):
                    raise UnsupportedCheck(f"function {value}.{col}() is not modelled")
                value = col
            self.columns.add(value)
            return ("col", value)
        raise UnsupportedCheck(f"unexpected token {value!r}")

    def call(self, name: str):
        if name not in _FUNCTIONS:
            raise UnsupportedCheck(f"function {name}() is not modelled")
        self.expect_op("(")
        args = []
        if not self.op(")"):
            args.append(self.or_expr())
            while self.op(","):
                self.take()
                args.append(self.or_expr())
        self.expect_op(")")
        return ("call", name, args)


# ---------------------------------------------------------------------------
# Evaluation — three-valued
# ---------------------------------------------------------------------------

_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?)?(Z|[+-]\d{2}(:?\d{2})?)?$")


def _as_temporal(value):
    if isinstance(value, (_dt.datetime, _dt.date)):
        return value
    if isinstance(value, str) and _ISO_RE.match(value.strip()):
        text = value.strip().replace("Z", "+00:00")
        try:
            if len(text) == 10:
                return _dt.date.fromisoformat(text)
            return _dt.datetime.fromisoformat(text)
        except ValueError:
            return None
    return None


def _as_number(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        return value
    if isinstance(value, str):
        try:
            return Decimal(value.strip())
        except InvalidOperation:
            return None
    return None


def _comparable(a, b):
    """Normalize a pair for comparison, or raise `_Unknown`."""
    if isinstance(a, bool) or isinstance(b, bool):
        if isinstance(a, bool) and isinstance(b, bool):
            return a, b
        raise _Unknown
    na, nb = _as_number(a), _as_number(b)
    if na is not None and nb is not None and not (isinstance(a, str) and isinstance(b, str)):
        return _num(na), _num(nb)
    ta, tb = _as_temporal(a), _as_temporal(b)
    if ta is not None and tb is not None:
        if isinstance(ta, _dt.datetime) != isinstance(tb, _dt.datetime):
            raise _Unknown  # a date vs a timestamp: Postgres casts; we don't guess
        if isinstance(ta, _dt.datetime) and (ta.tzinfo is None) != (tb.tzinfo is None):
            raise _Unknown
        return ta, tb
    if isinstance(a, str) and isinstance(b, str):
        return a, b
    if type(a) is type(b):
        return a, b
    raise _Unknown


def _num(value):
    return Decimal(str(value)) if isinstance(value, float) else Decimal(value) if isinstance(value, int) else value


def _compare(op: str, a, b) -> Optional[bool]:
    if a is None or b is None:
        return None
    x, y = _comparable(a, b)
    try:
        if op == "=":
            return x == y
        if op == "<>":
            return x != y
        if op == "<":
            return x < y
        if op == "<=":
            return x <= y
        if op == ">":
            return x > y
        if op == ">=":
            return x >= y
    except TypeError as exc:
        raise _Unknown from exc
    raise UnsupportedCheck(op)


def _truth(value) -> Optional[bool]:
    if value is None or isinstance(value, bool):
        return value
    raise _Unknown  # a non-boolean where SQL needs one


def _jsonb_typeof(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float, Decimal)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, Mapping):
        return "object"
    if isinstance(value, (list, tuple)):
        return "array"
    raise _Unknown


def _str_arg(value) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise _Unknown
    return value


def _btrim(args):
    s = _str_arg(args[0])
    chars = _str_arg(args[1]) if len(args) > 1 else " "
    return None if s is None or chars is None else s.strip(chars)


def _cardinality(args):
    v = args[0]
    if v is None:
        return None
    if not isinstance(v, (list, tuple)):
        raise _Unknown
    return len(v)


def _array_length(args):
    v = args[0]
    if v is None:
        return None
    if not isinstance(v, (list, tuple)):
        raise _Unknown
    return len(v) or None  # Postgres: array_length('{}', 1) IS NULL


def _non_null(args):
    return [a for a in args if a is not None]


def _abs(args):
    if args[0] is None:
        return None
    n = _as_number(args[0])
    if n is None:
        raise _Unknown
    return abs(_num(n))


def _extreme(pick):
    def run(args):
        values = _non_null(args)
        if len({type(v) for v in values}) > 1:
            raise _Unknown
        return pick(values) if values else None
    return run


_FUNCTIONS: dict[str, Callable[[list], Any]] = {
    "length": lambda a: None if _str_arg(a[0]) is None else len(a[0]),
    "char_length": lambda a: None if _str_arg(a[0]) is None else len(a[0]),
    "btrim": _btrim,
    "trim": lambda a: None if _str_arg(a[0]) is None else a[0].strip(" "),
    "ltrim": lambda a: None if _str_arg(a[0]) is None else a[0].lstrip(a[1] if len(a) > 1 else " "),
    "rtrim": lambda a: None if _str_arg(a[0]) is None else a[0].rstrip(a[1] if len(a) > 1 else " "),
    "lower": lambda a: None if _str_arg(a[0]) is None else a[0].lower(),
    "upper": lambda a: None if _str_arg(a[0]) is None else a[0].upper(),
    "coalesce": lambda a: next((v for v in a if v is not None), None),
    "nullif": lambda a: None if a[0] is not None and _compare("=", a[0], a[1]) else a[0],
    "num_nonnulls": lambda a: len(_non_null(a)),
    "num_nulls": lambda a: len(a) - len(_non_null(a)),
    "jsonb_typeof": lambda a: _jsonb_typeof(a[0]),
    "json_typeof": lambda a: _jsonb_typeof(a[0]),
    "jsonb_array_length": lambda a: _cardinality(a),
    "cardinality": _cardinality,
    "array_length": _array_length,
    "abs": _abs,
    "greatest": _extreme(max),
    "least": _extreme(min),
}


def _cast(value, type_name: str):
    if value is None:
        return None
    if type_name.endswith("[]"):  # an array cast is element-wise
        if not isinstance(value, (list, tuple)):
            raise _Unknown
        return [_cast(v, type_name[:-2]) for v in value]
    base = type_name
    if base in ("text", "varchar", "character", "char", "citext", "name"):
        return value if isinstance(value, str) else str(value)
    if base in ("int", "integer", "int4", "int8", "int2", "bigint", "smallint"):
        n = _as_number(value)
        if n is None:
            raise _Unknown
        return int(n)
    if base in ("numeric", "decimal", "real", "float4", "float8", "double precision"):
        n = _as_number(value)
        if n is None:
            raise _Unknown
        return _num(n)
    if base in ("bool", "boolean"):
        if isinstance(value, bool):
            return value
        raise _Unknown
    return value  # date/timestamptz/jsonb/uuid/…: the comparison normalizer handles them


def _eval(node, row: Mapping[str, Any]):
    tag = node[0]
    if tag == "lit":
        return node[1]
    if tag == "col":
        return row[node[1]]
    if tag == "and":
        a, b = _truth(_eval(node[1], row)), _truth(_eval(node[2], row))
        if a is False or b is False:
            return False
        return None if a is None or b is None else True
    if tag == "or":
        a, b = _truth(_eval(node[1], row)), _truth(_eval(node[2], row))
        if a is True or b is True:
            return True
        return None if a is None or b is None else False
    if tag == "not":
        a = _truth(_eval(node[1], row))
        return None if a is None else not a
    if tag == "cmp":
        return _compare(node[1], _eval(node[2], row), _eval(node[3], row))
    if tag == "isnull":
        is_null = _eval(node[1], row) is None
        return not is_null if node[2] else is_null
    if tag == "istruth":
        value = _truth(_eval(node[1], row))
        result = value is node[2]
        return not result if node[3] else result
    if tag == "distinct":
        a, b = _eval(node[1], row), _eval(node[2], row)
        if a is None or b is None:
            same = a is None and b is None
        else:
            same = _compare("=", a, b)
        distinct = not same
        return not distinct if node[3] else distinct
    if tag == "in":
        left = _eval(node[1], row)
        values = [_eval(item, row) for item in node[2]]
        if left is None:
            return None
        hit = any(v is not None and _compare("=", left, v) for v in values)
        result = True if hit else (None if any(v is None for v in values) else False)
        if node[3]:
            return None if result is None else not result
        return result
    if tag == "between":
        value, low, high = (_eval(n, row) for n in node[1:4])
        lo, hi = _compare(">=", value, low), _compare("<=", value, high)
        result = False if lo is False or hi is False else (None if lo is None or hi is None else True)
        if node[4]:
            return None if result is None else not result
        return result
    if tag == "regex":
        value = _str_arg(_eval(node[1], row))
        if value is None:
            return None
        hit = node[2].search(value) is not None
        return not hit if node[3] else hit
    if tag == "contains":
        a, b = _eval(node[2], row), _eval(node[3], row)
        if a is None or b is None:
            return None
        if not isinstance(a, (list, tuple)) or not isinstance(b, (list, tuple)):
            raise _Unknown
        inner, outer = (a, b) if node[1] == "<@" else (b, a)
        return all(any(i is not None and _compare("=", i, o) for o in outer) for i in inner)
    if tag == "arith":
        a, b = _eval(node[2], row), _eval(node[3], row)
        if a is None or b is None:
            return None
        if node[1] == "||":
            return f"{a}{b}"
        x, y = _as_number(a), _as_number(b)
        if x is None or y is None:
            raise _Unknown
        x, y = _num(x), _num(y)
        try:
            return {"+": lambda: x + y, "-": lambda: x - y, "*": lambda: x * y,
                    "/": lambda: x / y, "%": lambda: x % y}[node[1]]()
        except (ArithmeticError, InvalidOperation) as exc:
            raise _Unknown from exc
    if tag == "neg":
        v = _eval(node[1], row)
        if v is None:
            return None
        n = _as_number(v)
        if n is None:
            raise _Unknown
        return -_num(n)
    if tag == "cast":
        return _cast(_eval(node[1], row), node[2])
    if tag == "call":
        return _FUNCTIONS[node[1]]([_eval(a, row) for a in node[2]])
    if tag == "array":
        return [_eval(item, row) for item in node[1]]
    raise UnsupportedCheck(tag)


@dataclass(frozen=True)
class CompiledCheck:
    """One CHECK, ready to judge rows. `columns` = the columns it reads."""

    name: str
    body: str
    columns: frozenset[str]
    _ast: Any

    def verdict(self, row: Mapping[str, Any]) -> Optional[bool]:
        """True = satisfied, False = VIOLATED, None = unknown / not judgeable
        (a referenced column absent from `row`, or a value the mock can't
        compare faithfully). Only False is a violation."""
        if not self.columns <= row.keys():
            return None
        try:
            return _truth(_eval(self._ast, row))
        except _Unknown:
            return None


def compile_check(body: str, name: str = "<check>") -> CompiledCheck:
    """Compile a CHECK body (the text INSIDE `CHECK (...)`). Raises
    `UnsupportedCheck` for SQL outside the modelled subset."""
    parser = _Parser(body)
    tree = parser.parse()
    return CompiledCheck(name=name, body=body, columns=frozenset(parser.columns), _ast=tree)


def compile_cross_column_checks(
    raw: Mapping[str, Mapping[str, str]],
) -> tuple[dict[str, list[CompiledCheck]], list[tuple[str, str, str]]]:
    """From `{table: {constraint_name: body}}` (`migration_parser.
    parse_check_files`): (`{table: [compiled CROSS-COLUMN CHECKs]}`,
    `[(table, name, reason)]` for every CHECK this module can't model).
    The one compile path for the mock (`_schema_cache.get_check_map`) and
    for `stand_in_conformance` leg B(iv) — what the gate calls covered is
    exactly what the mock enforces."""
    compiled: dict[str, list[CompiledCheck]] = {}
    unsupported: list[tuple[str, str, str]] = []
    for table, named in raw.items():
        for name, body in named.items():
            try:
                check = compile_check(body, name)
            except UnsupportedCheck as exc:
                unsupported.append((table, name, str(exc)))
                continue
            if len(check.columns) >= 2:
                compiled.setdefault(table, []).append(check)
    return compiled, unsupported


__all__ = ["CompiledCheck", "UnsupportedCheck", "compile_check", "compile_cross_column_checks"]
