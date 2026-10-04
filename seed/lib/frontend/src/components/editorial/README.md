# editorial organs (E4)

`ReviewQueue`, `EditorialTimeline`, `VersionDiff` — FE of the seed editorial workflow
(`noctusai_lib/domain/editorial`, project `seed-editorial-workflow`). Organs depend on the typed
`EditorialDataSource` (types.ts); `createEditorialHttpSource(api, basePath='/api/editorial')` is the
real adapter, `FakeEditorialDataSource` the in-memory one. JSON field names = backend dataclass fields.

## Backend contract (E3 `editorial_router`, mounted under a consumer prefix)

Responses use the seed `success_response` envelope `{success, data}`; `createEditorialHttpSource(api, basePath)`
unwraps it. Backend = contract of record.

| Method + path | Request | `data` |
|---|---|---|
| `GET {base}` | `state?`, `kind?`, `awaiting_me?`, `page`, `page_size` | `{items, total, counts, page, page_size}` — `counts` per state under the same `kind`/`awaiting_me` filters, ignoring `state`; `awaiting_me` is computed server-side with `decide_transition` over the caller's derived grants |
| `POST {base}` | `{kind, ref, content}` | create item (not used by the organs) |
| `GET {base}/{id}` | — | `{item, versions, events}` |
| `POST {base}/{id}/versions` | `{content}` | `{item, event, version}` |
| `POST {base}/{id}/transitions` | `{action, motivo?}` | `{item, event, version}` |
| `GET {base}/{id}/diff` | `from_n`, `to_n` | `{from_n, to_n, changes}` — the adapter does NOT use it; `VersionDiff` diffs the two versions from `GET {base}/{id}` client-side (`diffContent`) |

Errors: `detail.code` machine codes; non-2xx surfaces `Error.message`.
