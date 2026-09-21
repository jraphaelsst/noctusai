/**
 * Line-level LCS diff aligned into side-by-side rows — for comparing two
 * compiled prompts (`texto_a` / `texto_b` from the §D1 diff endpoint).
 *
 * O(n·m) memory; `MAX_CELLS` bounds it. Past the bound the caller gets
 * `{demasiado: true}` and must say so on screen — never a silently unmarked
 * comparison.
 */
export type DiffRowKind = "igual" | "removida" | "adicionada" | "alterada";

export interface DiffRow {
  tipo: DiffRowKind;
  esquerda: string | null;
  direita: string | null;
  linhaA: number | null;
  linhaB: number | null;
}

export interface LineDiffResult {
  linhas: DiffRow[];
  demasiado: boolean;
  adicionadas: number;
  removidas: number;
}

export const MAX_CELLS = 4_000_000;

export function lineDiff(a: string, b: string): LineDiffResult {
  const la = a.split("\n");
  const lb = b.split("\n");
  const n = la.length;
  const m = lb.length;
  if (n * m > MAX_CELLS) return { linhas: [], demasiado: true, adicionadas: 0, removidas: 0 };

  // LCS lengths, suffix form: dp[i][j] = LCS(la[i:], lb[j:]).
  const w = m + 1;
  const dp = new Uint32Array((n + 1) * w);
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i * w + j] =
        la[i] === lb[j] ? dp[(i + 1) * w + j + 1] + 1 : Math.max(dp[(i + 1) * w + j], dp[i * w + j + 1]);
    }
  }

  const ops: { op: "eq" | "del" | "ins"; i: number; j: number }[] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (la[i] === lb[j]) {
      ops.push({ op: "eq", i, j });
      i++;
      j++;
    } else if (dp[(i + 1) * w + j] >= dp[i * w + j + 1]) {
      ops.push({ op: "del", i, j: -1 });
      i++;
    } else {
      ops.push({ op: "ins", i: -1, j });
      j++;
    }
  }
  while (i < n) ops.push({ op: "del", i: i++, j: -1 });
  while (j < m) ops.push({ op: "ins", i: -1, j: j++ });

  const linhas: DiffRow[] = [];
  let adicionadas = 0;
  let removidas = 0;
  let k = 0;
  while (k < ops.length) {
    const o = ops[k];
    if (o.op === "eq") {
      linhas.push({ tipo: "igual", esquerda: la[o.i], direita: lb[o.j], linhaA: o.i + 1, linhaB: o.j + 1 });
      k++;
      continue;
    }
    // Gather a change hunk (consecutive del/ins) and pair it row-by-row.
    const dels: number[] = [];
    const ins: number[] = [];
    while (k < ops.length && ops[k].op !== "eq") {
      if (ops[k].op === "del") dels.push(ops[k].i);
      else ins.push(ops[k].j);
      k++;
    }
    removidas += dels.length;
    adicionadas += ins.length;
    const rows = Math.max(dels.length, ins.length);
    for (let r = 0; r < rows; r++) {
      const di = dels[r];
      const ij = ins[r];
      const hasA = di !== undefined;
      const hasB = ij !== undefined;
      linhas.push({
        tipo: hasA && hasB ? "alterada" : hasA ? "removida" : "adicionada",
        esquerda: hasA ? la[di] : null,
        direita: hasB ? lb[ij] : null,
        linhaA: hasA ? di + 1 : null,
        linhaB: hasB ? ij + 1 : null,
      });
    }
  }
  return { linhas, demasiado: false, adicionadas, removidas };
}
