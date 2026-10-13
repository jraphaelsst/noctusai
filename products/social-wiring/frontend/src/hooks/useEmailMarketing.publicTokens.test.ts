/**
 * Public token pages (/confirmar-email/:token · /descadastro/:token) — the
 * info queries opt out of the global "Erro ao carregar dados" toast for the
 * statuses the page itself renders as "Link inválido ou expirado".
 *
 * Found in prod 2026-10-13: an expired confirmation link showed the friendly
 * invalid-link state AND a red `[400] …` toast on top — a duplicate that
 * alarms a recipient who is not even logged in. The suppression mechanism
 * itself is covered by the seed's `query-client.test.ts`; this pins which
 * statuses each public hook hands it. Same capture convention as
 * `useImoveis.test.ts` (mock `@tanstack/react-query`, read the options).
 */
import { afterEach, describe, expect, it, vi } from "vitest";

type CapturedOptions = { meta?: { suppressErrorToastStatuses?: number[] } };

async function captureQueryOptions(
  run: (mod: typeof import("./useEmailMarketing")) => void,
): Promise<CapturedOptions> {
  const captured: CapturedOptions[] = [];
  vi.doMock("@/lib/api", () => ({
    api: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), put: vi.fn(), delete: vi.fn() },
  }));
  vi.doMock("@tanstack/react-query", () => ({
    useQuery: (opts: CapturedOptions) => {
      captured.push(opts);
      return { data: undefined, isPending: false, isError: false };
    },
    useMutation: () => ({ mutate: vi.fn(), isPending: false }),
    useQueryClient: () => ({ invalidateQueries: vi.fn() }),
  }));
  vi.resetModules();
  run(await import("./useEmailMarketing"));
  return captured[captured.length - 1];
}

afterEach(() => {
  vi.doUnmock("@/lib/api");
  vi.doUnmock("@tanstack/react-query");
  vi.resetModules();
});

describe("public token pages do not double-report an invalid link", () => {
  it("confirmar-email suppresses the toast for 400 (invalid/expired) and 404 (contact gone)", async () => {
    const { meta } = await captureQueryOptions((m) => m.useEmConfirmEmailInfo("tok"));
    expect(meta?.suppressErrorToastStatuses).toEqual([400, 404]);
  });

  it("descadastro suppresses the toast for 400 (invalid link)", async () => {
    const { meta } = await captureQueryOptions((m) => m.useEmUnsubscribeInfo("tok"));
    expect(meta?.suppressErrorToastStatuses).toEqual([400]);
  });
});
