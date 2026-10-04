# editorial organs (E4)

`ReviewQueue`, `EditorialTimeline`, `VersionDiff` — FE of the seed editorial workflow
(`noctusai_lib/domain/editorial`, project `seed-editorial-workflow`). Organs depend on the typed
`EditorialDataSource` (types.ts); `createEditorialHttpSource(api, basePath='/api/editorial')` is the
real adapter, `FakeEditorialDataSource` the in-memory one. JSON field names = backend dataclass fields.

## Expected endpoints (E3 router must match, or adjust `dataSource.ts` only)

| Method + path | Request | Response |
|---|---|---|
| `GET {base}/queue` | query `state?`, `awaiting_me?` (bool), `page`, `page_size` | `{items: EditorialItem[], total, counts: {<state>: n}}` — `counts` under the same `awaiting_me` filter, ignoring `state`; `awaiting_me` is server-derived from the caller's grants |
| `GET {base}/items/{id}` | — | `{item, versions: EditorialVersion[], events: EditorialEvent[]}` |
| `POST {base}/items/{id}/versions` | `{content}` | `EditorialVersion` |
| `POST {base}/items/{id}/transition` | `{action, motivo?}` | `{item, event}` |
| `GET {base}/items/{id}/diff` | query `from`, `to` (version numbers) | `{from: EditorialVersion, to: EditorialVersion}` |

Items may carry an optional `title` (else `ref` is shown). Errors: non-2xx surfaces `Error.message`.
The diff itself is computed client-side (`diffContent`) from the two versions' `content`.
