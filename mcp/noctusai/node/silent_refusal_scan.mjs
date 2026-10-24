#!/usr/bin/env node
/**
 * silent_refusal_scan.mjs — ts-morph AST scan behind
 * `check_silent_refusal` (`mcp/noctusai/tools/noctus/dev/compliance.py`).
 *
 * THE CLASS. A refusal the user never sees. Four instances in one
 * social-wiring replay (2026-10-24): F76 a failed imóvel search (502/401)
 * rendered "Nenhum imóvel encontrado" + "Cadastrar novo"; F78 a 400 on an
 * anexo upload vanished; F86 a 422 on a certidão cell upload vanished; F75b
 * a client-side type check refused a valid file. Each was fixed locally;
 * this scan is the backstop that keeps the class from coming back. The
 * construction side is the seed upload organ (`@noctusai/lib/upload-refusal`:
 * `useUploadDocumento` + `<UploadErro>`) and `QueryErrorState`.
 * KB § PATTERNS/frontend/silent-refusal.md.
 *
 * Reads `{files: [absPath, ...]}` on stdin, prints
 * `{ok, results: {absPath: [finding]}, errors: {absPath: message}}`.
 * A file that fails to parse lands in `errors` — never a silent zero.
 *
 * RULE A — `empty_over_error` (.tsx only). A query's EMPTY branch is reachable
 * while the query is in ERROR. Detection, single file:
 *   1. Query bindings: `const q = useX(...)` used as `q.data` plus a query
 *      flag (`isPending/isLoading/isFetching/isError/error/refetch/isSuccess/
 *      status`), or `const { data, <a query flag> } = useX(...)`. Hooks that
 *      cannot be in error on screen (`useSuspenseQuery`, mutations, React
 *      built-ins) are excluded.
 *   2. Data expressions: `q.data…` / the destructured `data`, plus local
 *      aliases (`const rows = q.data?.items ?? []`), up to three hops,
 *      resolved by symbol, not by name.
 *   3. Empty predicates over a data expression: `E.length === 0` (also `== 0`,
 *      `< 1`, `<= 0`, `0 === E.length`) when E is DEFAULTED (`?? []`, `|| []`,
 *      a destructuring default) — undefined data fails `.length === 0` so an
 *      undefaulted `q.data?.length === 0` is safe — and `!E.length` always
 *      (`!undefined` is true).
 *   4. The predicate climbs `&&` / parentheses / one boolean alias
 *      (`const vazio = … rows.length === 0`) to a RENDER GATE: the test of a
 *      `?:`, the left side of a `&& <JSX>`, an `if (…) return`, or an
 *      `empty=`/`isEmpty=` JSX attribute.
 *   5. Guarded (no finding) when an `&&` sibling, an enclosing ternary's
 *      earlier test, or an earlier `if (…) return` in the same function
 *      references the query's error (`q.isError`, `q.error`, `q.status`,
 *      `q.isSuccess`, the destructured flags, or a boolean alias of them), or
 *      an `&&` sibling is the data itself (`q.data && …`).
 *   Out of scope, stated: a list handed to a child component through props
 *   (cross-file), and a `.length` read through a second function call.
 *
 * RULE B — upload refusals.
 *   B1 `upload_mutate_unhandled` (.tsx): `X.mutate(…)` / `X.mutateAsync(…)`
 *      whose first argument carries a file (`file`, `arquivo`, `files`,
 *      `arquivos`, `fotos` — an identifier, a property, or `e.target.files`)
 *      and nothing observes the failure: no `onError` in the call options,
 *      no `X.error` / `X.isError` read in the file, and — for `mutateAsync` —
 *      the promise is neither returned (a caller then owns it), awaited in a
 *      `try` with a non-empty `catch`, nor chained with `.catch` / a
 *      two-argument `.then`.
 *   B2 `upload_raw_unhandled` (.tsx): a direct `api.upload(…)` /
 *      `uploadMultipart(…)` call in a component with the same handling test.
 *   B3 `upload_organ_erro_unread` (.ts/.tsx): `useUploadDocumento(…)` whose
 *      `erro` is never read in the file — the organ's contract is that the
 *      caller renders the refusal (`<UploadErro erro={…} />`).
 *   B4 `upload_void_callback` (.tsx): a JSX `onUpload=` attribute whose arrow
 *      function calls `X.mutate(…)` — fire-and-forget; return
 *      `X.mutateAsync(…)` so the receiving component can show the refusal.
 *
 * Escape (per finding, same line or up to 3 lines above):
 *   `// noc-allow: silent-refusal — <why>`.
 */
import { Node, Project, SyntaxKind, ts } from "ts-morph";

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

const QUERY_FLAGS = new Set([
  "isPending", "isLoading", "isFetching", "isError", "error", "refetch", "isSuccess", "status",
]);
const ERROR_FLAGS = new Set(["isError", "error", "status", "isSuccess", "failureReason"]);
const NOT_QUERY_HOOK = /^(useState|useMemo|useRef|useCallback|useContext|useReducer|useEffect|useLayoutEffect|useTransition|useDeferredValue|useId|useSyncExternalStore|useSuspenseQuery|useSuspenseQueries|useQueryClient|useNavigate|useParams|useSearchParams|useLocation|useForm|useFormContext|useFieldArray|useWatch)$/;
const MUTATION_HOOK = /(Mutation|Mutations|Mutacao|Mutacoes)$/;
const FILE_NAMES = /^(file|files|arquivo|arquivos|fotos|foto|documento_arquivo|selectedFile|f)$/;
const ALLOW_RE = /noc-allow:\s*silent-refusal/;

// Per-file memo of `getDescendantsOfKind` — every rule walks the same node
// lists many times (one pass per query binding); re-walking the tree each time
// made a 700-file product take a minute.
const KIND_CACHE = new WeakMap();
function kinds(sf, kind) {
  let byKind = KIND_CACHE.get(sf);
  if (!byKind) {
    byKind = new Map();
    KIND_CACHE.set(sf, byKind);
  }
  if (!byKind.has(kind)) byKind.set(kind, sf.getDescendantsOfKind(kind));
  return byKind.get(kind);
}

const SYMBOL_CACHE = new WeakMap();

function calleeName(call) {
  const expr = call.getExpression();
  if (Node.isIdentifier(expr)) return expr.getText();
  if (Node.isPropertyAccessExpression(expr)) return expr.getName();
  return "";
}

function unwrapInit(init) {
  // `useX() as Foo`, `useX()!`, `(useX())`
  let cur = init;
  for (let i = 0; i < 4 && cur; i += 1) {
    if (Node.isAsExpression(cur) || Node.isNonNullExpression(cur) || Node.isParenthesizedExpression(cur) || Node.isSatisfiesExpression?.(cur)) {
      cur = cur.getExpression();
    } else break;
  }
  return cur;
}

function isHookCall(node) {
  if (!node || !Node.isCallExpression(node)) return false;
  const name = calleeName(node);
  return /^use[A-Z]/.test(name) && !NOT_QUERY_HOOK.test(name) && !MUTATION_HOOK.test(name);
}

function symbolOf(node) {
  const compiler = node.compilerNode;
  if (SYMBOL_CACHE.has(compiler)) return SYMBOL_CACHE.get(compiler);
  let s = null;
  try {
    s = node.getSymbol() ?? null;
  } catch {
    s = null;
  }
  SYMBOL_CACHE.set(compiler, s);
  return s;
}

function hasAllow(sf, line) {
  const lines = sf.getFullText().split("\n");
  for (let l = Math.max(0, line - 4); l <= line - 1 && l < lines.length; l += 1) {
    if (ALLOW_RE.test(lines[l])) return true;
  }
  return false;
}

// ─── Rule A ────────────────────────────────────────────────────────────────

/** Every query binding in the file: {kind, name, nameSym, dataSyms, errorSyms, dataDefaulted}. */
function collectQueries(sf) {
  const queries = [];
  for (const decl of kinds(sf, SyntaxKind.VariableDeclaration)) {
    const init = unwrapInit(decl.getInitializer());
    if (!isHookCall(init)) continue;
    const nameNode = decl.getNameNode();
    if (Node.isIdentifier(nameNode)) {
      const sym = symbolOf(nameNode);
      if (!sym) continue;
      const name = nameNode.getText();
      // Query-shaped use: `.data` AND a query flag on this very binding.
      let hasData = false;
      let hasFlag = false;
      for (const pa of kinds(sf, SyntaxKind.PropertyAccessExpression)) {
        const obj = pa.getExpression();
        if (!Node.isIdentifier(obj) || obj.getText() !== name) continue;
        if (symbolOf(obj) !== sym) continue;
        const prop = pa.getName();
        if (prop === "data") hasData = true;
        if (QUERY_FLAGS.has(prop)) hasFlag = true;
      }
      if (hasData && hasFlag) {
        queries.push({ kind: "object", name, sym, dataSyms: new Set(), errorSyms: new Set(), dataDefaulted: false, decl });
      }
    } else if (Node.isObjectBindingPattern(nameNode)) {
      let dataEl = null;
      let flag = false;
      const errorSyms = new Set();
      for (const el of nameNode.getElements()) {
        const propNode = el.getPropertyNameNode();
        const key = propNode ? propNode.getText() : el.getNameNode().getText();
        if (key === "data") dataEl = el;
        if (QUERY_FLAGS.has(key)) flag = true;
        if (ERROR_FLAGS.has(key)) {
          const s = symbolOf(el.getNameNode());
          if (s) errorSyms.add(s);
        }
      }
      if (!dataEl || !flag) continue;
      const dn = dataEl.getNameNode();
      if (!Node.isIdentifier(dn)) continue;
      const ds = symbolOf(dn);
      if (!ds) continue;
      queries.push({
        kind: "destructured",
        name: dn.getText(),
        sym: null,
        dataSyms: new Set([ds]),
        errorSyms,
        dataDefaulted: !!dataEl.getInitializer(),
        decl,
      });
    }
  }
  return queries;
}

/** Does `node`'s subtree read query Q's data (directly or through a known alias)? */
function readsData(node, q, aliasSyms) {
  const check = (n) => {
    if (Node.isPropertyAccessExpression(n) && q.kind === "object" && n.getName() === "data") {
      const obj = n.getExpression();
      if (Node.isIdentifier(obj) && symbolOf(obj) === q.sym) return true;
    }
    if (Node.isIdentifier(n)) {
      const s = symbolOf(n);
      if (s && (q.dataSyms.has(s) || aliasSyms.has(s))) return true;
    }
    return false;
  };
  if (check(node)) return true;
  return node.getDescendants().some(check);
}

const DEFAULT_RE = /(\?\?|\|\|)\s*(\[|\{|new (Map|Set)|EMPTY|VAZIO)/;

/** Data aliases: sym -> {defaulted}. */
function collectDataAliases(sf, q) {
  const aliases = new Map();
  const aliasSyms = new Set();
  for (let hop = 0; hop < 3; hop += 1) {
    let grew = false;
    for (const decl of kinds(sf, SyntaxKind.VariableDeclaration)) {
      if (decl === q.decl) continue;
      const nameNode = decl.getNameNode();
      if (!Node.isIdentifier(nameNode)) continue;
      const s = symbolOf(nameNode);
      if (!s || aliases.has(s)) continue;
      const init = decl.getInitializer();
      if (!init) continue;
      // A boolean predicate is not a data alias.
      if (Node.isBinaryExpression(init) && /^(===|!==|==|!=|<|>|<=|>=|&&)$/.test(init.getOperatorToken().getText())) continue;
      if (Node.isPrefixUnaryExpression(init)) continue;
      if (!readsData(init, q, aliasSyms)) continue;
      const text = init.getText();
      let defaulted = DEFAULT_RE.test(text);
      if (!defaulted) {
        for (const id of init.getDescendantsOfKind(SyntaxKind.Identifier)) {
          const is = symbolOf(id);
          if (is && aliases.get(is)?.defaulted) {
            defaulted = true;
            break;
          }
        }
      }
      if (!defaulted && q.dataDefaulted) {
        for (const id of init.getDescendantsOfKind(SyntaxKind.Identifier)) {
          const is = symbolOf(id);
          if (is && q.dataSyms.has(is)) {
            defaulted = true;
            break;
          }
        }
      }
      aliases.set(s, { defaulted });
      aliasSyms.add(s);
      grew = true;
    }
    if (!grew) break;
  }
  return { aliases, aliasSyms };
}

function exprDefaulted(expr, q, aliases) {
  if (DEFAULT_RE.test(expr.getText())) return true;
  const ids = Node.isIdentifier(expr) ? [expr] : expr.getDescendantsOfKind(SyntaxKind.Identifier);
  for (const id of ids) {
    const s = symbolOf(id);
    if (!s) continue;
    if (aliases.get(s)?.defaulted) return true;
    if (q.dataDefaulted && q.dataSyms.has(s)) return true;
  }
  return false;
}

function lengthTarget(node) {
  // `E.length` / `E?.length` -> E
  if (Node.isPropertyAccessExpression(node) && node.getName() === "length") return node.getExpression();
  return null;
}

/** Empty predicates over Q's data in the file. */
function emptyPredicates(sf, q, aliases, aliasSyms) {
  const out = [];
  for (const bin of kinds(sf, SyntaxKind.BinaryExpression)) {
    const op = bin.getOperatorToken().getText();
    const l = bin.getLeft();
    const r = bin.getRight();
    let target = null;
    if ((op === "===" || op === "==") && r.getText() === "0") target = lengthTarget(l);
    else if ((op === "===" || op === "==") && l.getText() === "0") target = lengthTarget(r);
    else if (op === "<" && r.getText() === "1") target = lengthTarget(l);
    else if (op === "<=" && r.getText() === "0") target = lengthTarget(l);
    if (!target) continue;
    if (!readsData(target, q, aliasSyms)) continue;
    if (!exprDefaulted(target, q, aliases)) continue;
    out.push(bin);
  }
  for (const pre of kinds(sf, SyntaxKind.PrefixUnaryExpression)) {
    if (pre.getOperatorToken() !== SyntaxKind.ExclamationToken) continue;
    const target = lengthTarget(pre.getOperand());
    if (!target) continue;
    if (!readsData(target, q, aliasSyms)) continue;
    // `!!x.length` is a non-empty test, not an empty one.
    const parent = pre.getParent();
    if (Node.isPrefixUnaryExpression(parent) && parent.getOperatorToken() === SyntaxKind.ExclamationToken) continue;
    out.push(pre);
  }
  return out;
}

/** Error-flag symbols of Q plus boolean aliases built from them. */
function errorRefSyms(sf, q) {
  const syms = new Set(q.errorSyms);
  const refsDirect = (node) => {
    const nodes = [node, ...node.getDescendants()];
    for (const n of nodes) {
      if (Node.isPropertyAccessExpression(n) && ERROR_FLAGS.has(n.getName())) {
        const obj = n.getExpression();
        if (q.kind === "object" && Node.isIdentifier(obj) && symbolOf(obj) === q.sym) return true;
      }
      if (Node.isIdentifier(n)) {
        const s = symbolOf(n);
        if (s && syms.has(s)) return true;
      }
    }
    return false;
  };
  for (let hop = 0; hop < 2; hop += 1) {
    for (const decl of kinds(sf, SyntaxKind.VariableDeclaration)) {
      const nameNode = decl.getNameNode();
      const init = decl.getInitializer();
      if (!Node.isIdentifier(nameNode) || !init) continue;
      const s = symbolOf(nameNode);
      if (s && !syms.has(s) && refsDirect(init)) syms.add(s);
    }
  }
  return { syms, refsError: refsDirect };
}

const LOADING_NAME = /^(isPending|isLoading|isFetching|isInitialLoading|showSkeleton|loading|carregando|pending)$/;

/** A NON-negated loading flag: `q.isPending`, `isLoading`, `showSkeleton`. */
function isLoadingFlag(node) {
  let n = node;
  while (Node.isParenthesizedExpression(n)) n = n.getExpression();
  if (Node.isPropertyAccessExpression(n)) return LOADING_NAME.test(n.getName());
  // A local name: `isLoading`, or a renamed binding (`isLoading: loadingMsgs`).
  if (Node.isIdentifier(n)) return LOADING_NAME.test(n.getText()) || /(loading|pending|skeleton|carregando)/i.test(n.getText());
  return false;
}

/** A bare data alias used as a truthy test (`detalhe && …` where `detalhe = q.data`). */
function isDataAliasTruthy(node, aliasSyms) {
  let n = node;
  while (Node.isParenthesizedExpression(n)) n = n.getExpression();
  if (!Node.isIdentifier(n)) return false;
  const s = symbolOf(n);
  return !!s && aliasSyms.has(s);
}

/** `a && (b && c)` -> [a, b, c] (parentheses unwrapped). */
function andOperands(node) {
  let n = node;
  while (Node.isParenthesizedExpression(n)) n = n.getExpression();
  if (Node.isBinaryExpression(n) && n.getOperatorToken().getKind() === SyntaxKind.AmpersandAmpersandToken) {
    return [...andOperands(n.getLeft()), ...andOperands(n.getRight())];
  }
  return [n];
}

function isDataTruthyGuard(node, q, aliasSyms) {
  // `q.data`, `data`, `q.data !== undefined`, `q.data != null`
  let n = node;
  while (Node.isParenthesizedExpression(n)) n = n.getExpression();
  if (Node.isBinaryExpression(n) && /^(!==|!=)$/.test(n.getOperatorToken().getText())) {
    const rt = n.getRight().getText();
    if (rt === "undefined" || rt === "null") n = n.getLeft();
  }
  if (Node.isPropertyAccessExpression(n) && n.getName() === "data" && q.kind === "object") {
    const obj = n.getExpression();
    return Node.isIdentifier(obj) && symbolOf(obj) === q.sym;
  }
  if (Node.isIdentifier(n)) {
    const s = symbolOf(n);
    return !!s && q.dataSyms.has(s);
  }
  return false;
}

function containsJsx(node) {
  if (!node) return false;
  const k = node.getKind();
  if (k === SyntaxKind.JsxElement || k === SyntaxKind.JsxSelfClosingElement || k === SyntaxKind.JsxFragment) return true;
  return node.getDescendants().some((d) => {
    const dk = d.getKind();
    return dk === SyntaxKind.JsxElement || dk === SyntaxKind.JsxSelfClosingElement || dk === SyntaxKind.JsxFragment;
  });
}

function enclosingFunction(node) {
  return node.getFirstAncestor((a) =>
    Node.isFunctionDeclaration(a) || Node.isArrowFunction(a) || Node.isFunctionExpression(a) || Node.isMethodDeclaration(a));
}

/** An earlier `if (<error>) return` in any enclosing function body, before `pos`. */
function earlierErrorReturn(node, refsError) {
  let fn = enclosingFunction(node);
  const pos = node.getStart();
  while (fn) {
    for (const ifs of fn.getDescendantsOfKind(SyntaxKind.IfStatement)) {
      if (ifs.getStart() >= pos) continue;
      if (ifs.getEnd() > pos && ifs.getStart() < pos) continue; // the gate sits inside it
      const then = ifs.getThenStatement();
      const returns = Node.isReturnStatement(then) || then.getDescendantsOfKind(SyntaxKind.ReturnStatement).length > 0;
      if (returns && refsError(ifs.getExpression())) return true;
    }
    fn = enclosingFunction(fn);
  }
  return false;
}

/** The gate sits in a branch of an `if (<error test>) … else …` (either branch: the test decided). */
function enclosingIfError(node, refsError) {
  for (const anc of node.getAncestors()) {
    if (!Node.isIfStatement(anc)) continue;
    const els = anc.getElseStatement();
    const inThen = anc.getThenStatement().containsRange(node.getStart(), node.getEnd());
    const inElse = els && els.containsRange(node.getStart(), node.getEnd());
    if ((inThen || inElse) && refsError(anc.getExpression())) return true;
  }
  return false;
}

/**
 * An enclosing `c ? A : B` (the gate in A or B) or `c && X` (the gate in X),
 * anywhere up to the enclosing function, whose test references the query's
 * error: the error was decided before the empty branch could render.
 */
function earlierTernaryError(node, refsError, dataGuard = () => false) {
  const fn = enclosingFunction(node);
  let cur = node;
  let parent = cur.getParent();
  while (parent && parent !== fn) {
    if (Node.isConditionalExpression(parent) && parent.getCondition() !== cur && refsError(parent.getCondition())) return true;
    // `data ? <…{empty}…/> : …` — the branch only renders with data in hand.
    if (Node.isConditionalExpression(parent) && parent.getWhenTrue() === cur && dataGuard(parent.getCondition())) return true;
    if (Node.isBinaryExpression(parent) && parent.getOperatorToken().getKind() === SyntaxKind.AmpersandAmpersandToken
        && parent.getRight() === cur && (refsError(parent.getLeft()) || dataGuard(parent.getLeft()))) return true;
    cur = parent;
    parent = cur.getParent();
  }
  return false;
}

/** Climb from an empty predicate to a render gate. Returns gate nodes [{gate, kind}] or [] (and recurses through a boolean alias). */
function climbToGates(start, ctx, depth = 0) {
  const { q, aliasSyms, refsError } = ctx;
  const gates = [];
  let cur = start;
  let guarded = false;
  for (;;) {
    const parent = cur.getParent();
    if (!parent) break;
    if (Node.isParenthesizedExpression(parent)) {
      cur = parent;
      continue;
    }
    if (Node.isBinaryExpression(parent) && parent.getOperatorToken().getKind() === SyntaxKind.AmpersandAmpersandToken) {
      const sibling = parent.getLeft() === cur ? parent.getRight() : parent.getLeft();
      if (parent.getLeft() === cur && containsJsx(sibling) && !Node.isBinaryExpression(sibling)) {
        // `<pred> && <JSX/>` — the JSX is the empty branch.
        if (!guarded) gates.push({ gate: parent, kind: "and_render" });
        return gates;
      }
      if (refsError(sibling) || andOperands(sibling).some((o) => isDataTruthyGuard(o, q, aliasSyms))) guarded = true;
      // `q.isPending && rows.length === 0 ? <Skeleton/>` — a LOADING gate
      // (the two-signal skeleton), not an empty branch.
      if (andOperands(sibling).some(isLoadingFlag)) return gates;
      cur = parent;
      continue;
    }
    if (Node.isConditionalExpression(parent) && parent.getCondition() === cur) {
      if (!guarded && containsJsx(parent.getWhenTrue())) gates.push({ gate: parent, kind: "ternary" });
      return gates;
    }
    if (Node.isIfStatement(parent) && parent.getExpression() === cur) {
      const then = parent.getThenStatement();
      const returnsJsx = then.getDescendantsOfKind(SyntaxKind.ReturnStatement).some((r) => containsJsx(r)) || (Node.isReturnStatement(then) && containsJsx(then));
      if (!guarded && returnsJsx) gates.push({ gate: parent, kind: "if_return" });
      return gates;
    }
    if (Node.isJsxExpression(parent)) {
      const attr = parent.getParent();
      if (Node.isJsxAttribute(attr)) {
        const an = attr.getNameNode().getText();
        if (!guarded && /^(empty|isEmpty|vazio|semResultados)$/.test(an)) {
          // `<ChartCard error={q.isError ? … : null} isEmpty={…}>` — the
          // component's own state priority (error before empty) guards it.
          const opening = attr.getParent()?.getParent();
          const siblingGuard = opening && (Node.isJsxOpeningElement(opening) || Node.isJsxSelfClosingElement(opening))
            && opening.getAttributes().some((a) => Node.isJsxAttribute(a)
              && /^(error|isError|erro|hasError)$/.test(a.getNameNode().getText())
              && a.getInitializer() && refsError(a.getInitializer()));
          if (!siblingGuard) gates.push({ gate: attr, kind: "empty_prop" });
        }
      }
      return gates;
    }
    if (Node.isVariableDeclaration(parent) && parent.getInitializer() === cur && depth < 2) {
      if (guarded) return gates;
      const nameNode = parent.getNameNode();
      if (!Node.isIdentifier(nameNode)) return gates;
      const s = symbolOf(nameNode);
      if (!s) return gates;
      const sf = parent.getSourceFile();
      for (const id of kinds(sf, SyntaxKind.Identifier)) {
        if (id === nameNode || id.getText() !== nameNode.getText()) continue;
        if (symbolOf(id) !== s) continue;
        gates.push(...climbToGates(id, ctx, depth + 1));
      }
      return gates;
    }
    break;
  }
  return gates;
}

function scanRuleA(sf) {
  const findings = [];
  const seen = new Set();
  for (const q of collectQueries(sf)) {
    const { aliases, aliasSyms } = collectDataAliases(sf, q);
    const { refsError } = errorRefSyms(sf, q);
    const ctx = { q, aliasSyms, refsError };
    for (const pred of emptyPredicates(sf, q, aliases, aliasSyms)) {
      for (const { gate, kind } of climbToGates(pred, ctx)) {
        const dataGuard = (n) => andOperands(n).some((o) => isDataTruthyGuard(o, q, aliasSyms) || isDataAliasTruthy(o, aliasSyms));
        if (earlierTernaryError(gate, refsError, dataGuard)) continue;
        if (earlierErrorReturn(gate, refsError)) continue;
        if (enclosingIfError(gate, refsError)) continue;
        const line = gate.getStartLineNumber();
        const key = `${line}:${q.name}`;
        if (seen.has(key)) continue;
        seen.add(key);
        if (hasAllow(sf, line)) continue;
        findings.push({
          rule: "empty_over_error",
          line,
          query: q.name,
          gate: kind,
          detail: `the empty branch at line ${line} renders while \`${q.name}\` is in ERROR (no isError/error guard before it): a failed request reads as "nothing found"`,
        });
      }
    }
  }
  return findings;
}

// ─── Rule B ────────────────────────────────────────────────────────────────

function carriesFile(arg) {
  if (!arg) return false;
  const nodes = [arg, ...arg.getDescendants()];
  for (const n of nodes) {
    if (Node.isIdentifier(n) && FILE_NAMES.test(n.getText())) {
      // the identifier as a value, or a shorthand/named property key
      return true;
    }
    if (Node.isPropertyAccessExpression(n) && n.getName() === "files") return true;
    if (Node.isNewExpression(n) && n.getExpression().getText() === "FormData") return true;
  }
  return false;
}

function promiseObserved(call) {
  // Returned (concise arrow body or `return`), chained `.catch` / `.then(a, b)`,
  // or awaited inside a `try` whose catch does something.
  let cur = call;
  let parent = cur.getParent();
  while (parent && (Node.isParenthesizedExpression(parent) || Node.isAwaitExpression(parent) || Node.isAsExpression(parent))) {
    cur = parent;
    parent = cur.getParent();
  }
  if (!parent) return false;
  if (Node.isReturnStatement(parent)) return true;
  if (Node.isArrowFunction(parent) && parent.getBody() === cur) return true;
  if (Node.isPropertyAccessExpression(parent) && parent.getExpression() === cur) {
    const name = parent.getName();
    const chained = parent.getParent();
    if (name === "catch" || name === "finally") return name === "catch";
    if (name === "then" && Node.isCallExpression(chained) && chained.getArguments().length >= 2) return true;
  }
  const tryStmt = call.getFirstAncestor((a) => Node.isTryStatement(a));
  if (tryStmt && tryStmt.getTryBlock().containsRange(call.getStart(), call.getEnd())) {
    const clause = tryStmt.getCatchClause();
    if (clause && clause.getBlock().getStatements().length > 0) return true;
  }
  return false;
}

function hasOnErrorOption(call) {
  const args = call.getArguments();
  for (const a of args.slice(1)) {
    if (Node.isObjectLiteralExpression(a) && a.getProperty("onError")) return true;
  }
  return false;
}

function mutationErrorRead(sf, rootText) {
  const re = new RegExp(`${rootText.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\??\\.(error|isError|failureReason)\\b`);
  return re.test(sf.getFullText());
}

function scanRuleB(sf, isTsx) {
  const findings = [];
  const push = (rule, node, detail) => {
    const line = node.getStartLineNumber();
    if (hasAllow(sf, line)) return;
    findings.push({ rule, line, detail });
  };
  for (const call of kinds(sf, SyntaxKind.CallExpression)) {
    const expr = call.getExpression();
    if (isTsx && Node.isPropertyAccessExpression(expr) && (expr.getName() === "mutate" || expr.getName() === "mutateAsync")) {
      const [first] = call.getArguments();
      if (!carriesFile(first)) continue;
      // B4: inside an `onUpload=` arrow, `mutate` is fire-and-forget.
      const attr = call.getFirstAncestor((a) => Node.isJsxAttribute(a));
      const rootText = expr.getExpression().getText();
      if (attr && /^onUpload/.test(attr.getNameNode().getText()) && expr.getName() === "mutate" && !hasOnErrorOption(call)) {
        push("upload_void_callback", call, `\`${rootText}.mutate(…)\` inside \`${attr.getNameNode().getText()}=\` is fire-and-forget: return \`${rootText}.mutateAsync(…)\` so the receiving component shows the refusal`);
        continue;
      }
      if (hasOnErrorOption(call)) continue;
      if (mutationErrorRead(sf, rootText)) continue;
      if (expr.getName() === "mutateAsync" && promiseObserved(call)) continue;
      push("upload_mutate_unhandled", call, `upload \`${rootText}.${expr.getName()}(…)\` has no onError, its error is never read and its promise is not observed: a server refusal vanishes — route it through useUploadDocumento + <UploadErro> (@noctusai/lib/upload-refusal)`);
      continue;
    }
    if (isTsx) {
      const isRawUpload =
        (Node.isPropertyAccessExpression(expr) && expr.getName() === "upload" && /^api$/.test(expr.getExpression().getText())) ||
        (Node.isIdentifier(expr) && expr.getText() === "uploadMultipart");
      if (isRawUpload) {
        if (call.getFirstAncestor((a) => Node.isPropertyAssignment(a) && /^(mutationFn|enviar)$/.test(a.getName()))) continue;
        // Inside the organ's send function, the organ owns the refusal.
        if (call.getFirstAncestor((a) => Node.isCallExpression(a) && calleeName(a) === "useUploadDocumento")) continue;
        if (promiseObserved(call)) continue;
        push("upload_raw_unhandled", call, `\`${expr.getText()}(…)\` in a component with no catch: a server refusal vanishes — route it through useUploadDocumento + <UploadErro>`);
      }
    }
    if (Node.isIdentifier(expr) && expr.getText() === "useUploadDocumento") {
      const decl = call.getFirstAncestor((a) => Node.isVariableDeclaration(a));
      if (!decl) {
        push("upload_organ_erro_unread", call, "useUploadDocumento(…) result is not bound: its `erro` must be rendered (<UploadErro erro={…} />)");
        continue;
      }
      const nameNode = decl.getNameNode();
      let read = false;
      if (Node.isIdentifier(nameNode)) {
        const name = nameNode.getText();
        read = new RegExp(`\\b${name}\\??\\.erro\\b`).test(sf.getFullText());
      } else if (Node.isObjectBindingPattern(nameNode)) {
        const el = nameNode.getElements().find((e) => (e.getPropertyNameNode()?.getText() ?? e.getNameNode().getText()) === "erro");
        if (el) {
          const local = el.getNameNode();
          const s = symbolOf(local);
          read = kinds(sf, SyntaxKind.Identifier).some((id) => id !== local && symbolOf(id) === s);
        }
      }
      if (!read) push("upload_organ_erro_unread", call, "useUploadDocumento(…)'s `erro` is never read: the organ's contract is that the caller renders the refusal (<UploadErro erro={…} />)");
    }
  }
  return findings;
}

function scanFile(sf) {
  const isTsx = sf.getFilePath().endsWith(".tsx");
  const text = sf.getFullText();
  // Cheap text gates: rule A needs a `.length` read, rule B an upload-ish call.
  const wantA = isTsx && text.includes(".length");
  const wantB = /mutate|\.upload\(|uploadMultipart|useUploadDocumento/.test(text);
  const findings = [...(wantA ? scanRuleA(sf) : []), ...(wantB ? scanRuleB(sf, isTsx) : [])];
  findings.sort((a, b) => a.line - b.line);
  return findings;
}

async function main() {
  const raw = await readStdin();
  let payload;
  try {
    payload = JSON.parse(raw);
  } catch (exc) {
    process.stdout.write(JSON.stringify({ ok: false, status: "bad_request", error: String(exc) }));
    return;
  }
  const files = Array.isArray(payload.files) ? payload.files : [];
  const project = new Project({
    useInMemoryFileSystem: false,
    skipAddingFilesFromTsConfig: true,
    skipFileDependencyResolution: true,
    compilerOptions: { jsx: ts.JsxEmit.ReactJSX, allowJs: false, noLib: true },
  });
  const results = {};
  const errors = {};
  // Add EVERY file first, then scan: symbol resolution needs a program, and
  // add/remove per file rebuilt it each time (~160 ms/file). One program for
  // the batch is ~15x faster.
  const added = [];
  for (const filePath of files) {
    try {
      added.push([filePath, project.addSourceFileAtPath(filePath)]);
    } catch (exc) {
      errors[filePath] = `add_source_file_failed: ${String(exc)}`;
    }
  }
  for (const [filePath, sourceFile] of added) {
    try {
      results[filePath] = scanFile(sourceFile);
    } catch (exc) {
      errors[filePath] = `scan_failed: ${String(exc && exc.stack ? exc.stack : exc)}`;
    }
  }
  process.stdout.write(JSON.stringify({ ok: true, results, errors }));
}

main().catch((exc) => {
  process.stderr.write(String(exc && exc.stack ? exc.stack : exc));
  process.exit(1);
});
