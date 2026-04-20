# Frontend Patterns

React + TypeScript + Vite. All products follow the same shape.

## Layer structure

```
pages/ → components/ → hooks/ → store/ → lib/
```

State split:
- **Zustand** — global UI state (sidebar collapsed, theme, etc.).
- **TanStack Query** — server state (all API data).
- Never put server state in Zustand. Never put transient UI state in TanStack Query.

## Mobile-first 3-tier responsive

- Base: mobile (320–639px).
- `sm:` / `md:` — tablet (640–1023px).
- `lg:` / `xl:` — desktop (1024px+).

**Test at 375 / 768 / 1440 px** before marking any UI work complete.

## Toasts

- Use `sonner` only. Never `react-hot-toast`, never custom toast systems.
- Error toasts: concrete message. No "Something went wrong." Say what went wrong.
- Success toasts: confirm the action ("Cliente cadastrado").

## Constants & utils

- Constants: `src/lib/constants.ts` per product. No magic numbers inline.
- Utils: `src/lib/utils.ts` for tiny helpers. Larger domain utils → dedicated file.

## TanStack Query

- `enabled: !!user` — never query before auth resolves.
- `staleTime` — set appropriate (5–60s for most lists; 0 for write-heavy data).
- `invalidateQueries` — invalidate by matching keys after mutations.

## Hooks in dedicated files, always

Every domain entity gets its own hook file:
```
hooks/useContacts.ts
hooks/useCampaigns.ts
hooks/useTemplates.ts
```

Never inline hooks in page components, even for simple products. Products grow — extracted hooks are ready when a second page needs the same data. No refactoring needed.

## Token refresh

Two complementary mechanisms:
- **Proactive**: `useActivityRefresh` — refresh when user interacts near expiry.
- **Reactive**: `onTokenExpired` in api-client — retry on 401 after refresh.

Both live in the seed's shared lib. Products don't implement refresh logic.

## API client

Use `api` from `@noctusai/seed/infra`:
```ts
import { api } from '@noctusai/seed/infra';
const res = await api.get('/api/contacts');
```

Never `fetch()` or `axios` directly. The seed api-client handles auth, correlation IDs, error shapes.

---

See also:
- `../03-SEED-ARCHITECTURE.md` — `createProductApp`, `createProductLayout`, `createProductInfra`
- `../04-SHARED-LIBRARY.md` — shared hooks + components catalog
