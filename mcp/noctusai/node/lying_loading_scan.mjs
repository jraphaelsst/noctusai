#!/usr/bin/env node
/**
 * lying_loading_scan.mjs — real ts-morph AST scan for Mode B of
 * `check_lying_loading_state` (`mcp/noctusai/tools/noctus/dev/compliance.py`).
 *
 * WHY AST, not regex (per that function's docstring + `KB § PATTERNS/
 * common/ast.md`): Mode B ("skeleton-over-data" / refetch-unmount) is a
 * `return`-statement / conditional-render DATAFLOW question — "does this
 * `if`-test's boolean expression, or the local variable it flows through,
 * carry a `&& !data`-shaped guard on its `isFetching` term before it
 * reaches an early `return` or a JSX ternary?" That is exactly the class
 * of question a line/brace regex answers unreliably (multi-line
 * conditions, parenthesised sub-expressions, one-hop local variables like
 * `const carregando = isPending || isFetching;` used two statements later)
 * and a real parser answers exactly: ts-morph resolves the TypeScript
 * binder, so "is this identifier the SAME `carregando` declared above" is
 * a real symbol question, not a name coincidence.
 *
 * Invoked by `check_lying_loading_state()` in `compliance.py` as a single
 * batched child process (one `Project`, N source files add via
 * `addSourceFilesAtPaths`) — NOT one spawn per file; parsing ~250 files
 * individually would dominate wall-clock. Reads one JSON payload
 * `{files: [absPath, ...]}` from stdin, prints one JSON result
 * `{results: {absPath: [finding, ...]}, errors: {absPath: message}}` to
 * stdout. `errors` is populated (never silently dropped) when a file
 * fails to parse — an honest typed signal, per `KB § 01-PHILOSOPHY.md`
 * "no silent errors": a skipped file must be visible as skipped, not
 * indistinguishable from "scanned, zero findings."
 *
 * DETECTION ALGORITHM (single-file dataflow, one variable-alias hop):
 *
 *   1. Collect every REAL "read" occurrence of `.isFetching` (property
 *      access `x.isFetching`) or a bare destructured `isFetching`
 *      identifier (excludes the declaration site itself, import
 *      specifiers, property-access member names, and JSX attribute
 *      names — those are declaration/naming positions, not reads).
 *   2. For each occurrence, climb the AST from the occurrence upward,
 *      tracking whether any `&&`-sibling passed along the way text-matches
 *      a "no data yet" guard (`!x.data`, `!data`, `<expr>.length === 0`,
 *      `!<expr>.length`, `<expr>.data === undefined`) — the SAME guard
 *      shape the canonical in-tree fix uses (`Funil.tsx:733`:
 *      `isPending || (isFetching && stages.length === 0)`).
 *   3. The climb stops at one of three outcomes:
 *        - a VARIABLE DECLARATION whose initializer contains the
 *          occurrence (the `carregando = isPending || isFetching` shape)
 *          → record as a TAINTED LOCAL with its own guard status; do NOT
 *          flag at the declaration line itself (declaring the boolean is
 *          not the bug — using it unguarded is).
 *        - a GATING ROOT: an `if (...) return ...;` (Mode B's canonical
 *          shape — the shipped bug), a `return <cond> ? <A> : <B>;` /
 *          `return <cond> && <JSX>;` (the whole-component-body ternary),
 *          or a JSX ternary at CHILD position (`{cond ? <A/> : <B/>}`,
 *          which unmounts one branch for the other) → flag UNLESS the
 *          climb found a guard.
 *        - a NON-GATING stop: a JSX attribute value (`disabled={x}`,
 *          `loading={x}` as a plain non-`.isLoading` boolean prop,
 *          `className=`, spinner/opacity props), or a bare `{cond &&
 *          <X/>}` at JSX child position (additive — does not remove
 *          sibling content the way a `return`/ternary does) → not a
 *          finding. This is the explicit ALLOWED set from the brief:
 *          "class name, `disabled=`, opacity, or spinner attribute."
 *   4. For each TAINTED LOCAL, find every later read-reference to that
 *      exact declared name (ts-morph symbol-resolved, not text-matched)
 *      and repeat step 2's climb from THAT reference. The occurrence is
 *      flagged only if BOTH the declaration's own initializer AND this
 *      usage site lack a guard — the `products/p-studio/frontend/src/
 *      pages/Integracoes.tsx` shape (`const carregando = isPending ||
 *      isFetching; ... if (carregando && !data) return <Spinner/>;`) is
 *      SAFE by this rule: the declaration is unguarded but the usage
 *      site supplies `&& !data`.
 *
 * SCOPE — deliberately ONE variable-alias hop. A `loading` prop threaded
 * through a SECOND local (`const x = carregando; ...; if (x) return...`)
 * or through a custom hook's return value consumed in another file is
 * NOT resolved — that is genuine cross-file/cross-hop dataflow, out of
 * scope here exactly as `check_lying_loading_state`'s own docstring says
 * for the original Mode-B gap. Recorded honestly, not silently passed.
 *
 * Deliberately NOT flagged (by design, not omission):
 *   - bare `isPending` with no `isFetching` in the same test, and no
 *     `&& !data` companion. TanStack Query v5 defines `isPending` as
 *     "no data has EVER resolved for this query" — i.e. `isPending`
 *     ALREADY implies `data === undefined` (the state-machine table in
 *     `KB § PATTERNS/frontend/lying-loading-state.md`: the only row with
 *     `isPending: true` has `data: undefined`). `if (isPending) return
 *     <Skeleton/>;` is the KB doc's own decision-procedure step 2, cited
 *     verbatim as CORRECT. Flagging it fleet-wide produces false
 *     positives against real, non-TanStack `.isPending` (a MUTATION's
 *     `isPending`, e.g. `products/erp-imobiliario/frontend/src/
 *     components/clientes/LeadScoreBadge.tsx:49` — `const { mutate,
 *     isPending } = useLeadScore(); if (isPending) return <Badge>...`,
 *     which has no `data` concept at all) — a violation of the
 *     zero-false-positive gate on this detector. `isPending` participates
 *     in a finding only as PART OF a test where a bare `.isFetching`
 *     occurrence is ALSO present and unguarded (`isPending || isFetching`
 *     — the exact shape that shipped 2026-08-31) — `isFetching`, not
 *     `isPending`, is the unguarded term doing the damage.
 */
import { Project, SyntaxKind, ts } from "ts-morph";

function readStdin() {
  return new Promise((resolve, reject) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => {
      data += chunk;
    });
    process.stdin.on("end", () => resolve(data));
    process.stdin.on("error", reject);
  });
}

// "No data yet" guard shapes admitted alongside `isFetching` via `&&`:
// `!x.data`, `!data`, `x.y.data === undefined`, `<expr>.length === 0`,
// `!<expr>.length`. Matched against the SIBLING operand's own source
// text (never the whole test), so an unrelated `&&` elsewhere in a long
// condition can't accidentally "launder" an unguarded occurrence. Every
// `!`-prefixed alternative carries a negative lookbehind for a second
// `!` immediately before it — `!!data` means "data IS present" (the
// opposite of a no-data guard) and must never be misread as one.
const NO_DATA_GUARD_RE = new RegExp(
  [
    String.raw`(?<!!)!\s*[\w$]+(?:\.[\w$]+)*\.data\b`,
    String.raw`(?<!!)!\s*data\b`,
    String.raw`[\w$]+(?:\.[\w$]+)*\.data\s*===?\s*undefined\b`,
    String.raw`[\w$]+(?:\.[\w$]+)*\.length\s*===?\s*0\b`,
    String.raw`(?<!!)!\s*[\w$]+(?:\.[\w$]+)*\.length\b`,
  ].join("|")
);

/** True if `node` is a genuine READ of identifier `name` — excludes
 * declaration names, import specifiers, property-access member names,
 * and JSX attribute names (all naming/declaration positions, not reads). */
function isReadIdentifier(node, name) {
  if (node.getKind() !== SyntaxKind.Identifier) return false;
  if (node.getText() !== name) return false;
  const parent = node.getParent();
  if (!parent) return true;
  const pk = parent.getKind();
  if (pk === SyntaxKind.BindingElement && parent.getNameNode?.() === node) return false;
  // The SOURCE-side key of a renamed destructure (`{ isLoading:
  // isLoadingFoo }`) — not a read of a local `isLoading` binding at all.
  if (pk === SyntaxKind.BindingElement && parent.getPropertyNameNode?.() === node) return false;
  if (pk === SyntaxKind.Parameter && parent.getNameNode?.() === node) return false;
  if (pk === SyntaxKind.VariableDeclaration && parent.getNameNode?.() === node) return false;
  if (pk === SyntaxKind.PropertyAccessExpression && parent.getNameNode?.() === node) return false;
  if (pk === SyntaxKind.ImportSpecifier) return false;
  if (pk === SyntaxKind.JsxAttribute && parent.getNameNode?.() === node) return false;
  if (pk === SyntaxKind.PropertySignature || pk === SyntaxKind.PropertyDeclaration) return false;
  return true;
}

/** True if the bare identifier `node` (already confirmed a real READ by
 * `isReadIdentifier`) resolves — via the REAL TypeScript binder, not a
 * name-text guess — to a declaration that is an OBJECT-destructured
 * binding: `const { data, isLoading } = useX();` or its renamed form
 * `const { data, isLoading: isLoadingFoo } = useX();`.
 *
 * WHY this matters (false-positive fix, 2026-08-31 fleet scan): `isLoading`
 * is ALSO a common name for HAND-ROLLED, non-TanStack UI state —
 * `const [isLoading, setIsLoading] = useState(false);` for a form-submit
 * spinner is a real, frequent shape (`products/erp-imobiliario/frontend/
 * src/components/modals/AdicionarRoleModal.tsx:39` — a first-pass Shape-5
 * scan flagged its `{isLoading ? 'Adicionando...' : 'Adicionar'}` BUTTON
 * LABEL ternary as a lying-loading-state violation, which it is not: this
 * `isLoading` is a manually-managed flag with none of TanStack's
 * "goes false mid-refetch" semantics, and the ternary swaps button TEXT,
 * not a skeleton over real data). An ARRAY-destructured `useState` local
 * (`ArrayBindingPattern`) is structurally never a TanStack query result —
 * `useQuery`/`useX()` hooks in this codebase always return an OBJECT.
 * Restricting bare-identifier taint to `ObjectBindingPattern` declarations
 * excludes the `useState` shape by construction, without needing to trace
 * the RHS call expression's return type (which ts-morph's default
 * `Project` — no full type-checker program — cannot cheaply resolve
 * anyway). `.isLoading` PROPERTY ACCESS (`x.isLoading`) is unaffected by
 * this check — reading a property literally named `isLoading` off some
 * object is already the established Mode-A precedent for "this is a query
 * result," and array-destructuring cannot produce that shape at all. */
function isObjectDestructuredIdentifier(node) {
  const symbol = node.getSymbol ? node.getSymbol() : null;
  if (!symbol) return false;
  const declarations = symbol.getDeclarations();
  if (!declarations || declarations.length === 0) return false;
  return declarations.some((decl) => {
    if (decl.getKind() !== SyntaxKind.BindingElement) return false;
    const bindingParent = decl.getParent();
    return !!bindingParent && bindingParent.getKind() === SyntaxKind.ObjectBindingPattern;
  });
}

/** Every real read-occurrence of `.<name>` (property access) or a bare
 * OBJECT-destructured `<name>` identifier in `sourceFile`. Shared by the
 * `isFetching` (guard-aware) and `isLoading` (Shape 5, guard-agnostic —
 * ANY gate reached is a violation, per the doc's absolute "no `.isLoading`
 * in a render branch" rule) taint passes in `scanFile`. */
function findTaintOccurrences(sourceFile, name) {
  const occurrences = [];
  sourceFile.forEachDescendant((node) => {
    if (node.getKind() === SyntaxKind.PropertyAccessExpression) {
      if (node.getName() === name) occurrences.push(node);
      return;
    }
    if (!isReadIdentifier(node, name)) return;
    if (!isObjectDestructuredIdentifier(node)) return; // excludes useState()'s ArrayBindingPattern shape.
    occurrences.push(node);
  });
  return occurrences;
}

/** Statement is (or directly contains, as its sole/first statement) a
 * `return`. Covers both `if (x) return y;` and `if (x) { return y; }`. */
function statementReturns(stmt) {
  if (!stmt) return false;
  if (stmt.getKind() === SyntaxKind.ReturnStatement) return true;
  if (stmt.getKind() === SyntaxKind.Block) {
    const stmts = stmt.getStatements();
    return stmts.length > 0 && stmts[0].getKind() === SyntaxKind.ReturnStatement;
  }
  return false;
}

/** Climb from `startNode` upward. Returns one of:
 *   {type: "declaration", varName, guarded, declLine}
 *   {type: "gate", kind, guarded, line, snippet}
 *   {type: "none"}
 * `guarded` = a `&&`-sibling matching NO_DATA_GUARD_RE was passed on the
 * climb from `startNode` to the returned boundary (declaration OR gate). */
function climb(startNode) {
  let current = startNode;
  let guarded = false;

  while (true) {
    const parent = current.getParent();
    if (!parent) return { type: "none" };
    const pk = parent.getKind();

    if (pk === SyntaxKind.ParenthesizedExpression) {
      current = parent;
      continue;
    }

    if (pk === SyntaxKind.BinaryExpression) {
      const opText = parent.getOperatorToken().getText();
      if (opText === "&&") {
        const left = parent.getLeft();
        const right = parent.getRight();
        const sibling = current === left ? right : left;
        if (sibling && NO_DATA_GUARD_RE.test(sibling.getText())) {
          guarded = true;
        }
      }
      // `||` provides no guard semantics — climb through it unguarded.
      current = parent;
      continue;
    }

    if (pk === SyntaxKind.VariableDeclaration) {
      // Only a match if we climbed here FROM the initializer (not the
      // name node — isReadIdentifier already excludes that case, but a
      // declaration boundary can only legitimately be reached via the
      // initializer subtree).
      if (parent.getInitializer() === current || isDescendantOf(current, parent.getInitializer())) {
        const nameNode = parent.getNameNode();
        if (nameNode.getKind() === SyntaxKind.Identifier) {
          return {
            type: "declaration",
            nameNode,
            varName: nameNode.getText(),
            guarded,
            declLine: parent.getStartLineNumber(),
          };
        }
      }
      return { type: "none" };
    }

    if (pk === SyntaxKind.IfStatement) {
      if (parent.getExpression() === current) {
        if (statementReturns(parent.getThenStatement())) {
          return {
            type: "gate",
            kind: "early_return",
            guarded,
            line: parent.getStartLineNumber(),
            snippet: truncate(parent.getText()),
          };
        }
      }
      return { type: "none" };
    }

    if (pk === SyntaxKind.ReturnStatement) {
      if (parent.getExpression() === current) {
        return {
          type: "gate",
          kind: "return_expr",
          guarded,
          line: parent.getStartLineNumber(),
          snippet: truncate(parent.getText()),
        };
      }
      return { type: "none" };
    }

    if (pk === SyntaxKind.ConditionalExpression) {
      if (parent.getCondition() === current) {
        // Ternary condition — a gating root only when it sits at JSX
        // CHILD position (unmounts one branch for the other) or IS the
        // return expression (already handled by the ReturnStatement case
        // above when we climb one more level, since `current` would then
        // equal this ConditionalExpression node).
        const cParent = parent.getParent();
        if (
          cParent &&
          cParent.getKind() === SyntaxKind.JsxExpression &&
          cParent.getParent() &&
          cParent.getParent().getKind() !== SyntaxKind.JsxAttribute
        ) {
          return {
            type: "gate",
            kind: "jsx_ternary",
            guarded,
            line: parent.getStartLineNumber(),
            snippet: truncate(parent.getText()),
          };
        }
        // Not at JSX-child / return position yet — keep climbing so the
        // ReturnStatement / JsxExpression ancestor case above
        // still gets a chance (e.g. `return isFetching ? <A/> : <B/>;`).
        current = parent;
        continue;
      }
      // We're inside a branch (whenTrue/whenFalse), not the condition —
      // not a gating question for THIS occurrence.
      return { type: "none" };
    }

    if (pk === SyntaxKind.JsxExpression) {
      // `{expr}` — if it's an attribute VALUE, that's the explicitly
      // ALLOWED non-destructive case (spinner/disabled/opacity/className
      // props). If it's a JSX CHILD and `current` is a bare `&&`
      // LogicalExpression (not wrapped in a ternary we already handled
      // above), that's the additive `{cond && <X/>}` shape — does not
      // remove sibling content, deliberately not flagged (see module
      // docstring). Either way: stop, not a gate.
      return { type: "none" };
    }

    // Any other boundary (Block as a statement-list, ArrowFunction body,
    // CallExpression argument, JsxAttribute value directly, etc.) — not
    // a recognised gating construct. Stop climbing.
    return { type: "none" };
  }
}

function isDescendantOf(node, ancestor) {
  if (!ancestor) return false;
  let cur = node;
  while (cur) {
    if (cur === ancestor) return true;
    cur = cur.getParent();
  }
  return false;
}

function truncate(text, max = 160) {
  const oneLine = text.replace(/\s+/g, " ").trim();
  return oneLine.length > max ? oneLine.slice(0, max) + "…" : oneLine;
}

/** Scan `sourceFile` for one taint name (`"isFetching"` or `"isLoading"`).
 * `guardAware=true` (isFetching): a gate is a finding only when UNguarded —
 * `isFetching && !data`-shaped guards make it safe. `guardAware=false`
 * (isLoading, Shape 5): ANY gate reached is a finding — the KB pattern's
 * rule is absolute ("No `.isLoading` anywhere in a render branch"); no
 * co-occurring condition rehabilitates it. Returns findings tagged with
 * `taint` so `check_lying_loading_state` can render the right remediation
 * text per shape. */
function scanTaint(sourceFile, name, guardAware) {
  const findings = [];
  // Keyed by the DECLARATION'S nameNode object (not the name STRING) —
  // two different functions each declaring their own local `carregando`
  // must never collide into one taint entry. See module docstring.
  const taintedLocals = new Map(); // nameNode -> {varName, guarded, declLine}

  const isViolation = (result) => (guardAware ? !result.guarded : true);

  for (const occ of findTaintOccurrences(sourceFile, name)) {
    const result = climb(occ);
    if (result.type === "gate" && isViolation(result)) {
      findings.push({
        line: result.line,
        kind: result.kind,
        snippet: result.snippet,
        via: null,
        taint: name,
      });
    } else if (result.type === "declaration") {
      const existing = taintedLocals.get(result.nameNode);
      taintedLocals.set(result.nameNode, {
        varName: result.varName,
        guarded: existing ? existing.guarded || result.guarded : result.guarded,
        declLine: result.declLine,
      });
    }
  }

  for (const [nameNode, decl] of taintedLocals) {
    // Real SCOPE-RESOLVED references to this exact declaration (the
    // TypeScript binder, not a same-spelled-string match) — a same-named
    // local declared in a sibling function never leaks in here.
    let refs;
    try {
      refs = nameNode.findReferencesAsNodes();
    } catch {
      refs = []; // language-service lookup failed for this node — skip, don't crash the whole scan.
    }
    for (const ref of refs) {
      if (ref === nameNode) continue; // findReferencesAsNodes usually excludes the decl itself; guard anyway.
      const result = climb(ref);
      if (result.type !== "gate") continue;
      const violation = guardAware ? !(decl.guarded || result.guarded) : true;
      if (violation) {
        findings.push({
          line: result.line,
          kind: result.kind,
          snippet: result.snippet,
          via: `${decl.varName} (declared line ${decl.declLine})`,
          taint: name,
        });
      }
    }
  }

  return findings;
}

function scanFile(sourceFile) {
  const findings = [
    ...scanTaint(sourceFile, "isFetching", /* guardAware */ true),
    ...scanTaint(sourceFile, "isLoading", /* guardAware */ false),
  ];

  // De-dupe (a single gating root can be reached via more than one
  // occurrence, e.g. `isPending || isFetching` inside one `if`).
  const seen = new Set();
  const deduped = [];
  for (const f of findings) {
    const key = `${f.line}:${f.kind}:${f.taint}`;
    if (seen.has(key)) continue;
    seen.add(key);
    deduped.push(f);
  }
  deduped.sort((a, b) => a.line - b.line);
  return deduped;
}

async function main() {
  const raw = await readStdin();
  let payload;
  try {
    payload = JSON.parse(raw);
  } catch (exc) {
    process.stdout.write(JSON.stringify({ ok: false, status: "bad_request", error: String(exc) }));
    process.exit(0);
    return;
  }

  const files = Array.isArray(payload.files) ? payload.files : [];
  const project = new Project({
    useInMemoryFileSystem: false,
    skipAddingFilesFromTsConfig: true,
    // `jsx` MUST be the numeric `ts.JsxEmit` enum, not the string
    // `"react-jsx"` — the language service's `findReferences` (used for
    // the one-hop variable-alias resolution below) throws
    // "jsx is a string value" against a raw string compiler option.
    compilerOptions: { jsx: ts.JsxEmit.ReactJSX, allowJs: false },
  });

  const results = {};
  const errors = {};

  for (const filePath of files) {
    let sourceFile;
    try {
      sourceFile = project.addSourceFileAtPath(filePath);
    } catch (exc) {
      errors[filePath] = `add_source_file_failed: ${String(exc)}`;
      continue;
    }
    try {
      results[filePath] = scanFile(sourceFile);
    } catch (exc) {
      errors[filePath] = `scan_failed: ${String(exc && exc.stack ? exc.stack : exc)}`;
    } finally {
      project.removeSourceFile(sourceFile);
    }
  }

  process.stdout.write(JSON.stringify({ ok: true, results, errors }));
}

main().catch((exc) => {
  process.stderr.write(String(exc && exc.stack ? exc.stack : exc));
  process.exit(1);
});
